"""Scenarios are data. Every file in scenarios/ must run on the unchanged engine."""
from pathlib import Path

import pytest

from ups.core import Simulation, load_scenarios_dir

SCENARIOS = load_scenarios_dir(Path(__file__).resolve().parents[1] / "scenarios")


def play(sc, pick):
    sim = Simulation(sc)
    while sim.status != "complete":
        if sim.status == "awaitingDecision":
            pd = sim.pending_decision()
            sim.submit_decision(pd["eventId"], pd["decisionId"], pd["options"][pick]["id"])
        else:
            sim.advance_to_next_event()
    return sim


def test_at_least_three_scenarios():
    assert len(SCENARIOS) >= 3


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_scenario_plays_to_completion(sid):
    sc = SCENARIOS[sid]
    for pick in (0, -1):
        sim = play(sc, pick)
        assert sim.day == sc.duration_days
        assert sim.decisions_made == len(sc.decisions)
        assert all(sc.measure(m).min <= v <= sc.measure(m).max for m, v in sim.values.items())


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_choices_matter(sid):
    sc = SCENARIOS[sid]
    outcomes = {tuple(sorted(play(sc, p).values.items())) for p in (0, 1, -1)}
    assert len(outcomes) > 1


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_every_decision_has_multiple_distinct_options(sid):
    for dec in SCENARIOS[sid].decisions:
        sigs = {tuple(sorted((e.measure, e.delta) for e in o.effects)) for o in dec.options}
        assert len(dec.options) >= 2 and len(sigs) == len(dec.options)
