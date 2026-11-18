import pytest

from ups.core import (
    DecisionMismatchError, DecisionPendingError, InvalidAdvanceError, InvalidOptionError,
    NoDecisionPendingError, RunCompleteError, Simulation,
)


def test_initial_state(sim):
    assert sim.day == 0 and sim.status == "running"
    assert {m["id"]: m["value"] for m in sim.measure_views()}["quality"] == 50


def test_advance_applies_daily_drift(sim):
    assert sim.advance(1) == 1
    assert sim.values["schedule"] == 49


def test_event_pauses_run_and_applies_effects(sim):
    assert sim.advance(5) == 2          # stops on day 2, when e1 fires
    assert sim.status == "awaitingDecision"
    assert sim.values["quality"] == 40
    assert sim.pending_decision()["decisionId"] == "d1"
    assert [b["label"] for b in sim.bottlenecks()] == ["Broken thing"]


def test_cannot_advance_while_decision_pending(sim):
    sim.advance(5)
    with pytest.raises(DecisionPendingError):
        sim.advance(1)


def test_decision_applies_effects_and_resolves_bottleneck(sim):
    sim.advance(5)
    sim.submit_decision("e1", "d1", "fix")
    assert sim.values["quality"] == 55 and sim.values["schedule"] == 43
    assert sim.bottlenecks() == []
    assert sim.status == "running"


def test_unresolved_bottleneck_stays_open(sim):
    sim.advance(5)
    sim.submit_decision("e1", "d1", "ignore")
    assert len(sim.bottlenecks()) == 1


def test_double_submit_rejected(sim):
    sim.advance(5)
    sim.submit_decision("e1", "d1", "fix")
    with pytest.raises(NoDecisionPendingError):
        sim.submit_decision("e1", "d1", "fix")
    assert sim.decisions_made == 1


def test_wrong_decision_and_bad_option_rejected(sim):
    sim.advance(5)
    with pytest.raises(DecisionMismatchError):
        sim.submit_decision("e2", "d1", "fix")
    with pytest.raises(InvalidOptionError):
        sim.submit_decision("e1", "d1", "nonsense")
    assert sim.status == "awaitingDecision"   # failed attempts change nothing


def test_decision_without_pending_rejected(sim):
    with pytest.raises(NoDecisionPendingError):
        sim.submit_decision("e1", "d1", "fix")


@pytest.mark.parametrize("bad", [0, -1, 400, 1.5, "3", True, None])
def test_invalid_advance_values(sim, bad):
    with pytest.raises(InvalidAdvanceError):
        sim.advance(bad)


def test_values_are_clamped(sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "fix")
    sim.advance(5)                       # e2 gives morale +20 on a 95 base -> clamp at 100
    assert sim.values["morale"] == 100
    entry = [e for e in sim.history if e["eventId"] == "e2"][0]
    assert entry["effects"][0]["delta"] == 20 and entry["effects"][0]["applied"] < 20


def test_run_completes_and_blocks_further_advance(sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "ignore"); sim.advance(10)
    assert sim.day == 5 and sim.status == "complete"
    with pytest.raises(RunCompleteError):
        sim.advance(1)


def test_advance_to_next_event(sim):
    assert sim.advance_to_next_event() == 2 and sim.status == "awaitingDecision"
    sim.submit_decision("e1", "d1", "fix")
    assert sim.advance_to_next_event() == 2 and sim.day == 4     # e2 has no decision
    assert sim.status == "running"
    assert sim.advance_to_next_event() == 1 and sim.status == "complete"


def test_reset_mid_run_restores_everything(sim):
    sim.advance(5); sim.reset()
    assert (sim.day, sim.status, sim.history, sim.reset_count) == (0, "running", [], 1)
    assert sim.values["quality"] == 50 and sim.pending_decision() is None and sim.bottlenecks() == []
    sim.advance(5)                       # still playable after reset
    assert sim.status == "awaitingDecision"


def test_history_explains_outcomes(sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "fix")
    ev, dec = sim.history
    assert ev["type"] == "event" and ev["measuresBefore"]["quality"] == 50 and ev["measuresAfter"]["quality"] == 40
    assert dec["type"] == "decision" and dec["optionLabel"] == "Fix" and dec["resolvedBottlenecks"] == ["Broken thing"]
    assert [e["seq"] for e in sim.history] == [1, 2]


def test_replay_is_deterministic(tiny, sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "fix"); sim.advance(10)
    copy = Simulation.replay(tiny, sim.actions)
    assert copy.snapshot() == sim.snapshot()


def test_replay_frames(sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "fix")
    frames = sim.replay_frames()
    assert [f["step"] for f in frames] == [0, 1, 2]
    assert frames[0]["measures"]["quality"] == 50 and frames[2]["measures"]["quality"] == 55


def test_health_summary(sim):
    sim.advance(5); sim.submit_decision("e1", "d1", "fix"); sim.advance(10)
    s = sim.health_summary()
    assert s["final"] and 0 <= s["overallScore"] <= 100 and s["rating"] in ("Healthy", "At risk", "Critical")
    assert s["decisionsMade"] == 1 and s["eventsFired"] == 2
    assert all("startValue" in m for m in s["measures"])


def test_inverted_measure_health():
    from conftest import tiny_data
    from ups.core import parse_scenario
    d = tiny_data(); d["measures"][1]["higherIsBetter"] = False; d["measures"][1]["initial"] = 90
    s = Simulation(parse_scenario(d))
    view = [m for m in s.measure_views() if m["id"] == "budget"][0]
    assert view["level"] == "critical"
