import json

import pytest

from conftest import tiny_data
from ups.core import ScenarioValidationError, load_scenario_file, load_scenarios_dir, parse_scenario, validate_scenario_data


def issues_for(mutate):
    d = tiny_data()
    mutate(d)
    return validate_scenario_data(d)


def has(issues, path_part, msg_part):
    return any(path_part in i["path"] and msg_part in i["message"] for i in issues)


def test_valid_scenario_has_no_issues():
    assert validate_scenario_data(tiny_data()) == []


def test_missing_field_is_named():
    assert has(issues_for(lambda d: d.pop("title")), "(root)", "missing required field: 'title'")


def test_must_have_exactly_four_measures():
    assert has(issues_for(lambda d: d["measures"].pop()), "measures", "at least 4")


def test_empty_events_rejected():
    assert has(issues_for(lambda d: d.update(events=[])), "events", "at least 1")


def test_unknown_field_rejected():
    assert has(issues_for(lambda d: d.update(script="os.system('x')")), "(root)", "script")


def test_unknown_measure_reference():
    def m(d): d["events"][0]["effects"][0]["measure"] = "nope"
    assert has(issues_for(m), "events[0].effects[0].measure", "unknown measure 'nope'")


def test_unknown_decision_reference():
    def m(d): d["events"][0]["decisionId"] = "ghost"
    assert has(issues_for(m), "events[0].decisionId", "unknown decision")


def test_decision_never_triggered():
    def m(d): del d["events"][0]["decisionId"]
    assert has(issues_for(m), "decisions[0].id", "never triggered")


def test_options_must_differ():
    def m(d): d["decisions"][0]["options"][1]["effects"] = list(d["decisions"][0]["options"][0]["effects"])
    assert has(issues_for(m), "options[1]", "same effects")


def test_event_after_end():
    def m(d): d["events"][1]["day"] = 9
    assert has(issues_for(m), "events[1].day", "after the scenario ends")


def test_duplicate_ids():
    def m(d): d["events"][1]["id"] = "e1"
    assert has(issues_for(m), "events[1].id", "duplicate id")


def test_initial_outside_range():
    def m(d): d["measures"][0]["initial"] = 500
    assert has(issues_for(m), "measures[0].initial", "outside")


def test_resolves_needs_bottleneck_event():
    def m(d): d["decisions"][0]["options"][0]["resolves"] = ["e2"]
    assert has(issues_for(m), "resolves[0]", "no bottleneck")


def test_all_problems_reported_together():
    def m(d):
        d.pop("title"); d["durationDays"] = 0
    assert len(issues_for(m)) >= 2


def test_not_an_object():
    assert validate_scenario_data([1, 2]) == [{"path": "(root)", "message": "scenario must be a JSON object"}]


def test_parse_raises_readable_error():
    d = tiny_data(); d.pop("id")
    with pytest.raises(ScenarioValidationError) as e:
        parse_scenario(d)
    assert "missing required field" in str(e.value)


def test_file_invalid_json(tmp_path):
    p = tmp_path / "bad.json"; p.write_text("{not json")
    with pytest.raises(ScenarioValidationError) as e:
        load_scenario_file(p)
    assert "not valid JSON" in str(e.value) and "bad.json" in str(e.value)


def test_file_rejects_nan_and_duplicate_keys(tmp_path):
    p = tmp_path / "nan.json"; p.write_text('{"a": NaN}')
    with pytest.raises(ScenarioValidationError):
        load_scenario_file(p)
    p2 = tmp_path / "dup.json"; p2.write_text('{"a": 1, "a": 2}')
    with pytest.raises(ScenarioValidationError):
        load_scenario_file(p2)


def test_file_too_large(tmp_path):
    p = tmp_path / "big.json"; p.write_text(" " * (300 * 1024))
    with pytest.raises(ScenarioValidationError) as e:
        load_scenario_file(p)
    assert "larger than" in str(e.value)


def test_empty_directory_rejected(tmp_path):
    with pytest.raises(ScenarioValidationError) as e:
        load_scenarios_dir(tmp_path)
    assert "no scenario files" in str(e.value)


def test_directory_reports_every_bad_file(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("[]")
    with pytest.raises(ScenarioValidationError) as e:
        load_scenarios_dir(tmp_path)
    assert "a.json" in str(e.value) and "b.json" in str(e.value)


def test_duplicate_scenario_ids_across_files(tmp_path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.json").write_text(json.dumps(tiny_data()))
    with pytest.raises(ScenarioValidationError) as e:
        load_scenarios_dir(tmp_path)
    assert "already used" in str(e.value)
