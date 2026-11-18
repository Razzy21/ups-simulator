# Adding a scenario (data only)

1. Copy a file in `scenarios/` and edit it. Validate against `schema/scenario.schema.json`.
2. Save it as `scenarios/<id>.json`, where `id` matches the file's `"id"`.
3. Run `pytest`. `tests/test_bundled_scenarios.py` plays every file in the folder on the unchanged engine.
4. Restart the server. The scenario appears in the list.

No engine code should ever need to change. If it does, that is a bug in the engine.

## Rules the validator enforces
- Exactly **four measures**. Each has `initial`, `min`, `max`, and optional `higherIsBetter` and `dailyDrift`.
- Events happen on a day from 1 to `durationDays`. An event can apply `effects`, open a `bottleneck`, and trigger a `decisionId`.
- Every decision needs **2-5 options**, and each option must have a **different** set of effects.
- An option can list event ids in `resolves` to close that event's bottleneck.
- Every decision must be triggered by an event. Every `measure`, `decisionId` and `resolves` reference must exist.
- `assumptions` is required: the UI shows it to players.

Errors list every problem with its path, for example `decisions[1].options[2]: has the same effects as option 'x'`.
