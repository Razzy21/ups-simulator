import copy

import pytest

from ups.core import Simulation, parse_scenario

TINY = {
    "schemaVersion": "1.0.0", "id": "tiny", "title": "Tiny", "description": "Small test scenario.",
    "durationDays": 5, "assumptions": ["Test only."],
    "measures": [
        {"id": "schedule", "label": "Schedule", "initial": 50, "min": 0, "max": 100, "dailyDrift": -1},
        {"id": "budget", "label": "Budget", "initial": 50, "min": 0, "max": 100},
        {"id": "quality", "label": "Quality", "initial": 50, "min": 0, "max": 100},
        {"id": "morale", "label": "Morale", "initial": 95, "min": 0, "max": 100},
    ],
    "milestones": [{"id": "mid", "label": "Midpoint", "day": 3}],
    "events": [
        {"id": "e1", "day": 2, "title": "Problem", "description": "Something broke.",
         "effects": [{"measure": "quality", "delta": -10}], "bottleneck": "Broken thing", "decisionId": "d1"},
        {"id": "e2", "day": 4, "title": "Good news", "description": "A win.",
         "effects": [{"measure": "morale", "delta": 20}]},
    ],
    "decisions": [{"id": "d1", "prompt": "What now?", "options": [
        {"id": "fix", "label": "Fix", "tradeoff": "Slow.", "effects": [{"measure": "quality", "delta": 15}, {"measure": "schedule", "delta": -5}], "resolves": ["e1"]},
        {"id": "ignore", "label": "Ignore", "tradeoff": "Fast.", "effects": [{"measure": "schedule", "delta": 2}]},
    ]}],
}


def tiny_data():
    return copy.deepcopy(TINY)


@pytest.fixture
def tiny():
    return parse_scenario(tiny_data())


@pytest.fixture
def sim(tiny):
    return Simulation(tiny)
