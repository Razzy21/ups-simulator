# Universal Project Simulator (UPS)

ECE Team G5.1

A simulator that loads a project scenario, advances virtual time, applies events and decisions, and reports measures.

## Layout

```
ups/core/      Simulation core. Pure Python, NO web imports.
ups/api/       HTTP API. Thin layer that calls into ups.core.
client/        Minimal web client.
schema/        Scenario data contract (JSON Schema).
scenarios/     Scenario files, validated against schema/.
tests/         Unit tests (core first, then API).
scripts/       Helper scripts.
```

Rule: `ups/core` must never import from `ups/api` or any web framework.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests

```bash
pytest
```

## Run the app

```bash
uvicorn ups.api.main:app --reload
```

Open http://127.0.0.1:8000 for the client, or http://127.0.0.1:8000/api/docs for the API.

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `UPS_RUN_TTL_MINUTES` | 120 | Delete a run after this long without activity |
| `UPS_MAX_RUNS` | 500 | Most runs kept in memory |
| `UPS_RATE_LIMIT_PER_MINUTE` | 120 | Requests per client address; 0 disables |
| `UPS_ACCESS_TOKEN` | unset | If set, `/api/*` needs header `X-Access-Token` |

## API

`POST /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/advance`, `POST /api/runs/{id}/decisions`, `GET /api/runs/{id}/history`, `GET /api/runs/{id}/summary`, `GET /api/runs/{id}/replay`, `POST /api/runs/{id}/reset`, `DELETE /api/runs/{id}`, plus `GET /api/scenarios` and `GET /api/meta`.

## Docs

[Scenario authoring](docs/SCENARIO_AUTHORING.md) | [Security review](docs/SECURITY.md) | [Data retention](docs/DATA_RETENTION.md) | [Demo script](docs/DEMO.md) | [User walkthrough kit](docs/WALKTHROUGH.md)

## Workflow

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

- [x] 13. Repo, branches, README
- [x] 14. Simulation core + unit tests
- [x] 15. API
- [x] 16. Minimal client
- [ ] 17. Internal demo (script ready: docs/DEMO.md)
- [x] 18-22. Dashboard, decision prompts, run log, final summary, replay and reset
- [ ] 23. User walkthrough (kit ready: docs/WALKTHROUGH.md)
- [x] 24. Scenarios 2 and 3 as data files only
- [x] 25-26. Schema validation, error handling and edge cases
- [ ] 27. Access controls: optional token implemented; team decides if needed
- [x] 28-30. Disclaimer and assumptions in UI, security review, data retention
