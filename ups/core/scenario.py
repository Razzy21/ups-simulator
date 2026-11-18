"""Scenario model and loading. Scenarios are JSON data only; nothing in them is ever executed."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ScenarioValidationError
from .validation import validate_scenario_data

MAX_SCENARIO_BYTES = 256 * 1024


@dataclass(frozen=True)
class Effect:
    measure: str
    delta: float


@dataclass(frozen=True)
class Measure:
    id: str
    label: str
    initial: float
    min: float
    max: float
    unit: str = ""
    higher_is_better: bool = True
    daily_drift: float = 0.0


@dataclass(frozen=True)
class Milestone:
    id: str
    label: str
    day: int


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    tradeoff: str
    effects: tuple[Effect, ...]
    resolves: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    id: str
    prompt: str
    options: tuple[Option, ...]


@dataclass(frozen=True)
class Event:
    id: str
    day: int
    title: str
    description: str
    effects: tuple[Effect, ...] = ()
    bottleneck: str | None = None
    decision_id: str | None = None


def _effects(items) -> tuple[Effect, ...]:
    return tuple(Effect(e["measure"], float(e["delta"])) for e in items)


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    duration_days: int
    assumptions: tuple[str, ...]
    measures: tuple[Measure, ...]
    milestones: tuple[Milestone, ...]
    events: tuple[Event, ...]
    decisions: tuple[Decision, ...]
    _events: dict = field(init=False, repr=False)
    _decisions: dict = field(init=False, repr=False)
    _measures: dict = field(init=False, repr=False)

    def __post_init__(self):
        self._events = {e.id: e for e in self.events}
        self._decisions = {d.id: d for d in self.decisions}
        self._measures = {m.id: m for m in self.measures}

    def event(self, event_id: str) -> Event:
        return self._events[event_id]

    def decision(self, decision_id: str) -> Decision:
        return self._decisions[decision_id]

    def measure(self, measure_id: str) -> Measure:
        return self._measures[measure_id]

    def events_on(self, day: int) -> list[Event]:
        return [e for e in self.events if e.day == day]  # file order is kept

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        """Build from data that has ALREADY passed validation."""
        return cls(
            id=d["id"],
            title=d["title"],
            description=d["description"],
            duration_days=d["durationDays"],
            assumptions=tuple(d["assumptions"]),
            measures=tuple(
                Measure(
                    id=m["id"], label=m["label"], initial=float(m["initial"]), min=float(m["min"]),
                    max=float(m["max"]), unit=m.get("unit", ""),
                    higher_is_better=m.get("higherIsBetter", True), daily_drift=float(m.get("dailyDrift", 0)),
                )
                for m in d["measures"]
            ),
            milestones=tuple(Milestone(m["id"], m["label"], m["day"]) for m in d["milestones"]),
            events=tuple(
                Event(
                    id=e["id"], day=e["day"], title=e["title"], description=e["description"],
                    effects=_effects(e.get("effects", [])), bottleneck=e.get("bottleneck"),
                    decision_id=e.get("decisionId"),
                )
                for e in d["events"]
            ),
            decisions=tuple(
                Decision(
                    id=dec["id"], prompt=dec["prompt"],
                    options=tuple(
                        Option(
                            id=o["id"], label=o["label"], tradeoff=o["tradeoff"],
                            effects=_effects(o["effects"]), resolves=tuple(o.get("resolves", [])),
                        )
                        for o in dec["options"]
                    ),
                )
                for dec in d["decisions"]
            ),
        )

    def public_info(self) -> dict:
        """What a player may see before starting: no events or decisions (no spoilers)."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "durationDays": self.duration_days,
            "assumptions": list(self.assumptions),
            "measures": [
                {"id": m.id, "label": m.label, "unit": m.unit, "min": m.min, "max": m.max,
                 "initial": m.initial, "higherIsBetter": m.higher_is_better}
                for m in self.measures
            ],
            "milestones": [{"id": m.id, "label": m.label, "day": m.day} for m in self.milestones],
        }


def parse_scenario(data) -> Scenario:
    issues = validate_scenario_data(data)
    if issues:
        raise ScenarioValidationError(issues)
    return Scenario.from_dict(data)


def _reject_constant(name):
    raise ValueError(f"{name} is not allowed in JSON")


def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key '{k}'")
        out[k] = v
    return out


def load_scenario_file(path) -> Scenario:
    path = Path(path)
    name = path.name
    if path.stat().st_size > MAX_SCENARIO_BYTES:
        raise ScenarioValidationError(
            [{"path": "(file)", "message": f"file is larger than {MAX_SCENARIO_BYTES // 1024} KB"}], source=name)
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_keys,
        )
    except json.JSONDecodeError as e:
        raise ScenarioValidationError(
            [{"path": "(file)", "message": f"not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}"}],
            source=name) from None
    except (ValueError, RecursionError, UnicodeDecodeError) as e:
        raise ScenarioValidationError([{"path": "(file)", "message": f"cannot be read: {e}"}], source=name) from None
    try:
        return parse_scenario(data)
    except ScenarioValidationError as e:
        raise ScenarioValidationError(e.issues, source=name) from None


def load_scenarios_dir(directory) -> dict[str, Scenario]:
    """Load every *.json file in a directory. Reports problems from all files together."""
    directory = Path(directory)
    scenarios: dict[str, Scenario] = {}
    issues: list[dict] = []
    for p in sorted(directory.glob("*.json")):
        try:
            sc = load_scenario_file(p)
        except ScenarioValidationError as e:
            issues += [{"path": f"{p.name}: {i['path']}", "message": i["message"]} for i in e.issues]
            continue
        if sc.id in scenarios:
            issues.append({"path": f"{p.name}: id", "message": f"scenario id '{sc.id}' is already used by another file"})
        else:
            scenarios[sc.id] = sc
    if not scenarios and not issues:
        issues.append({"path": str(directory), "message": "no scenario files (*.json) found"})
    if issues:
        raise ScenarioValidationError(issues)
    return scenarios
