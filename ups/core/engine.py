"""The simulation engine. Pure Python, deterministic, no web dependencies.

A run is: load a scenario -> advance virtual time day by day -> events fire and may
pause the run for a decision -> decisions apply modeled effects -> measures update.
There is no randomness, so the same actions always give the same result (see `replay`).
"""
from __future__ import annotations

from .errors import (
    DecisionMismatchError, DecisionPendingError, InvalidAdvanceError, InvalidOptionError,
    NoDecisionPendingError, RunCompleteError,
)
from .scenario import Effect, Scenario

MAX_ADVANCE_DAYS = 365
OK_AT = 0.60        # health at or above this is "ok"
WARN_AT = 0.35      # below OK_AT but at or above this is "warning"; below is "critical"
RATING_BANDS = ((75, "Healthy"), (50, "At risk"), (0, "Critical"))


def _level(health: float) -> str:
    return "ok" if health >= OK_AT else "warning" if health >= WARN_AT else "critical"


def _rating(score: int) -> str:
    for threshold, label in RATING_BANDS:
        if score >= threshold:
            return label
    return RATING_BANDS[-1][1]


class Simulation:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.reset_count = 0
        self._init_state()

    # ----- state -----------------------------------------------------------
    def _init_state(self) -> None:
        self.day = 0
        self.values = {m.id: float(m.initial) for m in self.scenario.measures}
        self._start_values = dict(self.values)
        self._pending: list[str] = []                 # event ids waiting for a decision (FIFO)
        self._bottlenecks: dict[str, tuple[str, int]] = {}  # event id -> (label, day opened)
        self.history: list[dict] = []
        self.series: list[dict] = [self._series_point()]
        self.actions: list[dict] = []
        self.decisions_made = 0
        self.events_fired = 0

    def reset(self) -> None:
        self._init_state()
        self.reset_count += 1

    @property
    def status(self) -> str:
        if self._pending:
            return "awaitingDecision"
        if self.day >= self.scenario.duration_days:
            return "complete"
        return "running"

    # ----- time ------------------------------------------------------------
    def _require_not_blocked(self) -> None:
        if self._pending:
            raise DecisionPendingError("A decision is waiting. Make it before advancing time.")
        if self.day >= self.scenario.duration_days:
            raise RunCompleteError("This run is complete. Reset it to play again.")

    def advance(self, days: int = 1) -> int:
        """Advance up to `days` days; stops early if an event needs a decision. Returns days advanced."""
        self._require_not_blocked()
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_ADVANCE_DAYS:
            raise InvalidAdvanceError(f"days must be a whole number from 1 to {MAX_ADVANCE_DAYS}")
        n = 0
        while n < days and not self._pending and self.day < self.scenario.duration_days:
            self._tick()
            n += 1
        self.actions.append({"type": "advance", "days": n})
        return n

    def advance_to_next_event(self) -> int:
        """Advance until something happens (an event fires) or the scenario ends."""
        self._require_not_blocked()
        start, n = len(self.history), 0
        while not self._pending and self.day < self.scenario.duration_days:
            self._tick()
            n += 1
            if len(self.history) > start:
                break
        self.actions.append({"type": "advance", "days": n})
        return n

    def _tick(self) -> None:
        self.day += 1
        for m in self.scenario.measures:
            if m.daily_drift:
                self._set(m.id, self.values[m.id] + m.daily_drift)
        for ev in self.scenario.events_on(self.day):
            self._fire(ev)
        self.series.append(self._series_point())

    def _fire(self, ev) -> None:
        before = dict(self.values)
        applied = self._apply(ev.effects)
        if ev.bottleneck:
            self._bottlenecks[ev.id] = (ev.bottleneck, self.day)
        if ev.decision_id:
            self._pending.append(ev.id)
        self.events_fired += 1
        self._log({
            "type": "event", "day": self.day, "eventId": ev.id, "title": ev.title,
            "description": ev.description, "effects": applied, "bottleneck": ev.bottleneck,
            "decisionRequired": ev.decision_id is not None,
            "measuresBefore": before, "measuresAfter": dict(self.values),
        })

    # ----- decisions -------------------------------------------------------
    def pending_decision(self) -> dict | None:
        if not self._pending:
            return None
        ev = self.scenario.event(self._pending[0])
        dec = self.scenario.decision(ev.decision_id)
        return {
            "eventId": ev.id, "eventTitle": ev.title, "eventDescription": ev.description,
            "decisionId": dec.id, "prompt": dec.prompt,
            "options": [{"id": o.id, "label": o.label, "tradeoff": o.tradeoff} for o in dec.options],
            "queued": len(self._pending) - 1,
        }

    def submit_decision(self, event_id: str, decision_id: str, option_id: str) -> None:
        if not self._pending:
            raise NoDecisionPendingError("There is no decision to make right now (it may already have been submitted).")
        ev = self.scenario.event(self._pending[0])
        if event_id != ev.id or decision_id != ev.decision_id:
            raise DecisionMismatchError("That decision is not the one currently waiting.")
        dec = self.scenario.decision(ev.decision_id)
        option = next((o for o in dec.options if o.id == option_id), None)
        if option is None:
            raise InvalidOptionError(f"'{option_id}' is not an option for this decision.")
        before = dict(self.values)
        applied = self._apply(option.effects)
        resolved = []
        for ref in option.resolves:
            if ref in self._bottlenecks:
                resolved.append(self._bottlenecks.pop(ref)[0])
        self._pending.pop(0)
        self.decisions_made += 1
        self.series[-1] = self._series_point()  # same day as the event: refresh its point
        self.actions.append({"type": "decision", "eventId": event_id, "decisionId": decision_id, "optionId": option_id})
        self._log({
            "type": "decision", "day": self.day, "eventId": ev.id, "eventTitle": ev.title,
            "decisionId": dec.id, "prompt": dec.prompt, "optionId": option.id,
            "optionLabel": option.label, "tradeoff": option.tradeoff, "effects": applied,
            "resolvedBottlenecks": resolved, "measuresBefore": before, "measuresAfter": dict(self.values),
        })

    # ----- measures --------------------------------------------------------
    def _set(self, measure_id: str, value: float) -> None:
        m = self.scenario.measure(measure_id)
        self.values[measure_id] = round(min(m.max, max(m.min, value)), 4)

    def _apply(self, effects: tuple[Effect, ...]) -> list[dict]:
        out = []
        for e in effects:
            old = self.values[e.measure]
            self._set(e.measure, old + e.delta)
            out.append({
                "measure": e.measure, "label": self.scenario.measure(e.measure).label,
                "delta": e.delta, "applied": round(self.values[e.measure] - old, 2),
            })
        return out

    def _health(self, m, value: float) -> float:
        frac = (value - m.min) / (m.max - m.min)
        return frac if m.higher_is_better else 1 - frac

    def measure_views(self, values: dict | None = None) -> list[dict]:
        values = values or self.values
        out = []
        for m in self.scenario.measures:
            h = self._health(m, values[m.id])
            out.append({
                "id": m.id, "label": m.label, "unit": m.unit, "value": round(values[m.id], 2),
                "min": m.min, "max": m.max, "higherIsBetter": m.higher_is_better,
                "health": round(h, 3), "level": _level(h),
            })
        return out

    def _series_point(self) -> dict:
        return {"day": self.day, "values": {k: round(v, 2) for k, v in self.values.items()}}

    def _log(self, entry: dict) -> None:
        entry["seq"] = len(self.history) + 1
        self.history.append(entry)

    # ----- views -----------------------------------------------------------
    def bottlenecks(self) -> list[dict]:
        items = [{"source": "event", "eventId": eid, "label": label, "sinceDay": since}
                 for eid, (label, since) in self._bottlenecks.items()]
        for view in self.measure_views():
            if view["level"] == "critical":
                items.append({"source": "measure", "measureId": view["id"],
                              "label": f"{view['label']} is in a critical state", "sinceDay": None})
        return items

    def health_summary(self) -> dict:
        views = self.measure_views()
        score = round(100 * sum(v["health"] for v in views) / len(views))
        best = max(views, key=lambda v: v["health"])
        worst = min(views, key=lambda v: v["health"])
        for v in views:
            v["startValue"] = round(self._start_values[v["id"]], 2)
        return {
            "final": self.status == "complete", "overallScore": score, "rating": _rating(score),
            "measures": views, "best": best["label"], "worst": worst["label"],
            "daysElapsed": self.day, "decisionsMade": self.decisions_made,
            "eventsFired": self.events_fired,
            "openBottlenecks": len(self._bottlenecks),
        }

    def snapshot(self) -> dict:
        summary = self.health_summary()
        return {
            "scenarioId": self.scenario.id, "title": self.scenario.title, "day": self.day,
            "durationDays": self.scenario.duration_days, "status": self.status,
            "resetCount": self.reset_count,
            "projectStatus": {"score": summary["overallScore"], "rating": summary["rating"]},
            "measures": self.measure_views(), "pendingDecision": self.pending_decision(),
            "bottlenecks": self.bottlenecks(),
            "milestones": [{"id": m.id, "label": m.label, "day": m.day, "reached": self.day >= m.day}
                           for m in self.scenario.milestones],
            "series": self.series, "feed": list(reversed(self.history[-8:])),
            "historyLength": len(self.history),
        }

    # ----- replay ----------------------------------------------------------
    def replay_frames(self) -> list[dict]:
        frames = [{"step": 0, "day": 0, "label": "Start of project", "measures": dict(self._start_values), "entry": None}]
        for e in self.history:
            label = e["title"] if e["type"] == "event" else f"Decision: {e['optionLabel']}"
            frames.append({"step": e["seq"], "day": e["day"], "label": label,
                           "measures": e["measuresAfter"], "entry": e})
        return frames

    @classmethod
    def replay(cls, scenario: Scenario, actions: list[dict]) -> "Simulation":
        """Rebuild a run from its recorded actions. Deterministic: same actions, same result."""
        sim = cls(scenario)
        for a in actions:
            if a["type"] == "advance":
                sim.advance(a["days"])
            else:
                sim.submit_decision(a["eventId"], a["decisionId"], a["optionId"])
        return sim
