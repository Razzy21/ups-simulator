# Universal Project Simulator (UPS)

ECE Team G5.1

UPS is a training simulator for project management. You pick a project scenario, move time forward, face events, and make decisions. Four measures change as you go: **Schedule, Budget, Quality and Team morale**. At the end you get a health score and a log that explains why.

> It is a training simulator, not a forecast. The numbers are simplified examples, not real data.

## Quick start

You need Python 3.11 or newer.

```bash
# 1. Create and activate a virtual environment (once)
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Mac / Linux

# 2. Install the packages (once)
pip install -r requirements.txt

# 3. Run the tests (should say "82 passed")
pytest

# 4. Start the app
uvicorn ups.api.main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser. Press `Ctrl+C` in the terminal to stop.

Each time you come back, you only need to activate the environment and run step 4.

## How to use it

1. Choose a scenario and click **Start**.
2. Click **Next event** (or advance 1 or 7 days).
3. When a decision appears, read the options and click **Choose this**.
4. Watch the four measures change. Keep going until the scenario ends.
5. On the final screen, open **Explain outcomes** for the full log, or use **Replay** and **Reset**.

## How it works

The code has three layers. Think of a restaurant:

| Layer | Restaurant | Folder | Job |
|---|---|---|---|
| Rules engine | The kitchen | `ups/core/` | Holds all the rules and works out every result. No web code in it. |
| Server (API) | The waiter | `ups/api/` | Carries requests between the screen and the engine. No rules in it. |
| Screen | The dining room | `client/` | The web page players see and click. |

Scenarios are the recipes: plain text files in `scenarios/`.

**The most important rule:** `ups/core` must never import from `ups/api` or any web framework. A test checks this.

## Technology

- **Language:** Python (rules and server). JavaScript, HTML and CSS (the web page).
- **Server:** FastAPI, started with uvicorn.
- **Database:** none. Runs are kept in memory and deleted after 120 minutes of inactivity or when the server restarts.
- **Scenarios:** JSON files.
- **Tests:** pytest.

## What is in each folder

```
ups/core/
  engine.py        The simulation: time, events, decisions, measures, history, replay
  scenario.py      Loads and reads scenario files
  validation.py    Checks scenario files and reports every problem
  errors.py        The error types the core can raise
ups/api/
  app.py           The web requests the server understands
  store.py         Keeps runs in memory and expires old ones
  settings.py      Settings read from environment variables
  main.py          Entry point used by uvicorn
client/
  index.html       The page
  app.js           Dashboard, decisions, run log, summary, replay
  style.css        Appearance
scenarios/         One JSON file per scenario
schema/            The rulebook scenario files must follow
tests/             Automated tests
docs/              Extra guides (see the list below)
```

## Scenarios

There are three, each one a plain JSON file:

| Scenario | File | Length |
|---|---|---|
| Website redesign | `scenarios/website-redesign.json` | 28 days |
| Customer data migration | `scenarios/data-migration.json` | 24 days |
| Mobile app release | `scenarios/mobile-app-release.json` | 21 days |

### Add a new one (no code changes)

1. Copy a file in `scenarios/` and rename it.
2. Edit the id, title, assumptions, events and decisions.
3. Run `pytest`. If something is wrong, the error names the exact problem.
4. Restart the server. The scenario appears in the list.

Rules: exactly four measures; every decision has 2 to 5 options; every option has a different effect. Details are in [docs/SCENARIO_AUTHORING.md](docs/SCENARIO_AUTHORING.md).

## The API

Open **http://127.0.0.1:8000/api/docs** while the app is running to try these in the browser.

| Request | What it does |
|---|---|
| `GET /api/scenarios` | List scenarios |
| `POST /api/runs` | Start a run |
| `GET /api/runs/{id}` | Get the current state |
| `POST /api/runs/{id}/advance` | Move time forward |
| `POST /api/runs/{id}/decisions` | Submit a decision |
| `GET /api/runs/{id}/history` | The run log |
| `GET /api/runs/{id}/summary` | The final health summary |
| `GET /api/runs/{id}/replay` | Replay frames |
| `POST /api/runs/{id}/reset` | Start the run over |
| `DELETE /api/runs/{id}` | Delete a run |

## Settings (optional)

| Variable | Default | Meaning |
|---|---|---|
| `UPS_RUN_TTL_MINUTES` | 120 | Delete a run after this long without activity |
| `UPS_MAX_RUNS` | 500 | Most runs kept in memory |
| `UPS_RATE_LIMIT_PER_MINUTE` | 120 | Requests per client address; 0 turns it off |
| `UPS_ACCESS_TOKEN` | not set | If set, requests need an `X-Access-Token` header |

## Limits

- Effects are simplified training models, not statistics.
- Runs live in one server's memory, so nothing is saved between restarts and it is built for a single server process.
- No user accounts.

## More guides

- [Scenario authoring](docs/SCENARIO_AUTHORING.md)
- [Security review](docs/SECURITY.md)
- [Data retention](docs/DATA_RETENTION.md)
- [Demo script](docs/DEMO.md)
- [User walkthrough kit](docs/WALKTHROUGH.md)
- [How the team works with branches and pull requests](CONTRIBUTING.md)

## Project status

Built: simulation core, API, dashboard, decision prompts, run log, final summary, replay and reset, three scenarios, validation and security checks, and 82 automated tests.

Still to do: rehearse the demo, test with outside users, choose where to host it, and decide whether access controls are needed.
