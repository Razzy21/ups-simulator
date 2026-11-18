"""Scenario validation: JSON Schema first, then cross-reference checks.

Returns a list of issues (`{"path", "message"}`) instead of raising, so a scenario
author sees every problem at once.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "scenario.schema.json"
_validator: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _validator = Draft202012Validator(schema)
    return _validator


def _fmt_path(parts) -> str:
    out = ""
    for p in parts:
        if isinstance(p, int):
            out += f"[{p}]"
        else:
            out += f".{p}" if out else str(p)
    return out or "(root)"


def _truncate(text: str, n: int = 200) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def _schema_issues(data) -> list[dict]:
    issues = []
    errors = sorted(_get_validator().iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    for e in errors:
        if e.validator == "minItems":
            msg = f"must contain at least {e.validator_value} item(s)"
        elif e.validator == "maxItems":
            msg = f"must contain at most {e.validator_value} item(s)"
        elif e.validator == "required":
            msg = f"missing required field: {e.message.split(' is a required')[0]}"
        else:
            msg = _truncate(e.message)
        issues.append({"path": _fmt_path(e.absolute_path), "message": msg})
    return issues


def _semantic_issues(d: dict) -> list[dict]:
    issues: list[dict] = []

    def add(path: str, msg: str) -> None:
        issues.append({"path": path, "message": msg})

    def check_unique(items, field_path):
        seen: dict[str, int] = {}
        for i, item in enumerate(items):
            k = item["id"]
            if k in seen:
                add(f"{field_path}[{i}].id", f"duplicate id '{k}' (first used at {field_path}[{seen[k]}])")
            else:
                seen[k] = i

    for name in ("measures", "milestones", "events", "decisions"):
        check_unique(d[name], name)

    duration = d["durationDays"]
    measure_ids = {m["id"] for m in d["measures"]}

    for i, m in enumerate(d["measures"]):
        if m["min"] >= m["max"]:
            add(f"measures[{i}]", "min must be lower than max")
        elif not (m["min"] <= m["initial"] <= m["max"]):
            add(f"measures[{i}].initial", f"initial value {m['initial']} is outside min..max")

    for i, ms in enumerate(d["milestones"]):
        if ms["day"] > duration:
            add(f"milestones[{i}].day", f"day {ms['day']} is after the scenario ends (durationDays={duration})")

    def check_effects(effects, path):
        for j, eff in enumerate(effects):
            if eff["measure"] not in measure_ids:
                add(f"{path}[{j}].measure", f"unknown measure '{eff['measure']}' (known: {', '.join(sorted(measure_ids))})")

    decision_ids = {dec["id"] for dec in d["decisions"]}
    event_ids = {e["id"] for e in d["events"]}
    bottleneck_events = {e["id"] for e in d["events"] if e.get("bottleneck")}
    triggered: set[str] = set()

    for i, e in enumerate(d["events"]):
        if e["day"] > duration:
            add(f"events[{i}].day", f"day {e['day']} is after the scenario ends (durationDays={duration})")
        check_effects(e.get("effects", []), f"events[{i}].effects")
        did = e.get("decisionId")
        if did is not None:
            if did not in decision_ids:
                add(f"events[{i}].decisionId", f"unknown decision '{did}'")
            else:
                triggered.add(did)

    for i, dec in enumerate(d["decisions"]):
        if dec["id"] not in triggered:
            add(f"decisions[{i}].id", f"decision '{dec['id']}' is never triggered by any event")
        check_unique(dec["options"], f"decisions[{i}].options")
        signatures: dict[tuple, str] = {}
        for j, opt in enumerate(dec["options"]):
            path = f"decisions[{i}].options[{j}]"
            check_effects(opt["effects"], f"{path}.effects")
            for k, ref in enumerate(opt.get("resolves", [])):
                if ref not in event_ids:
                    add(f"{path}.resolves[{k}]", f"unknown event '{ref}'")
                elif ref not in bottleneck_events:
                    add(f"{path}.resolves[{k}]", f"event '{ref}' has no bottleneck to resolve")
            sig = tuple(sorted((x["measure"], x["delta"]) for x in opt["effects"]))
            if sig in signatures:
                add(path, f"has the same effects as option '{signatures[sig]}'; each option needs a different modeled effect")
            else:
                signatures[sig] = opt["id"]
    return issues


def validate_scenario_data(data) -> list[dict]:
    """Return a list of problems; an empty list means the scenario is valid."""
    if not isinstance(data, dict):
        return [{"path": "(root)", "message": "scenario must be a JSON object"}]
    issues = _schema_issues(data)
    if issues:
        return issues  # cross-reference checks need a structurally valid document
    return _semantic_issues(data)
