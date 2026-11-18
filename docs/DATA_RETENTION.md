# Data retention (step 30)

| What | Where | How long |
|---|---|---|
| Run state, history and decisions | Server memory only | Deleted after **120 minutes** without activity (`UPS_RUN_TTL_MINUTES`), on `DELETE /api/runs/{id}`, or when the server restarts |
| Stored runs overall | Server memory | At most **500** (`UPS_MAX_RUNS`); least recently used runs are evicted first |
| Client address (for rate limiting) | Server memory | About one minute (sliding window) |
| Access token, if enabled | Environment variable on the server | Not stored by the app; the browser keeps it in `sessionStorage` until the tab closes |
| Scenario files | `scenarios/` in the repo | Part of the code |

- Nothing is written to disk. There is no database and no log of player choices.
- No accounts, names or emails are collected. Runs are anonymous and identified only by a random 128-bit id.
- The same text is served to the UI from `GET /api/meta`, so the screen and this document cannot drift apart.
- Web-server or hosting-provider logs are outside the app's control. When hosting is chosen, check what request logs that platform keeps and add it here.

If the team later adds a database or analytics, update this document first.
