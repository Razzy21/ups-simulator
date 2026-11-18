# Security review (step 29)

Review of the implemented code against the charter's exclusion of executable scenarios.

## No unsafe scenario execution
- Scenarios are **JSON data only**. They are parsed with `json.loads`, never `eval`, `exec`, `pickle` or templating.
- `schema/scenario.schema.json` uses `additionalProperties: false` everywhere, so unknown fields (for example a `script` field) are rejected. Covered by `test_unknown_field_rejected`.
- Effects are plain numbers applied by fixed engine code. There are no expressions, formulas or references to code.
- Scenarios are loaded only from the server's `scenarios/` folder at startup. **There is no upload endpoint** and no user-supplied path is ever opened.
- Files are capped at 256 KB; `NaN`/`Infinity` and duplicate JSON keys are rejected.

## Input validation
- Every request body is a strict Pydantic model (`extra="forbid"`, ranges, id patterns). Run ids must be 32 hex characters; scenario and option ids must match the slug pattern.
- Bodies over 10 KB are rejected when `Content-Length` says so. A reverse proxy should also enforce a body limit for chunked requests.
- Errors never leak stack traces: unexpected exceptions return a generic 500.

## Browser side
- A strict Content-Security-Policy (`default-src 'self'`, no inline script or style), plus `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.
- The client writes all server text with `textContent` (never `innerHTML`), so scenario text cannot inject markup.
- API responses are `Cache-Control: no-store`.

## Rate limiting and access
- Per-address sliding window, 120 requests a minute by default (`UPS_RATE_LIMIT_PER_MINUTE`, `0` disables). Failed token attempts count against it.
- Behind a reverse proxy every request may appear to come from the proxy's address. Configure the proxy (or extend the limiter) to use the real client address before relying on this.
- Optional shared token: set `UPS_ACCESS_TOKEN` and every `/api/*` call except `/api/health` needs the `X-Access-Token` header (compared in constant time). It is a gate for a private demo, not user accounts.

## Known limits (decide as a team)
- Run state lives in one process's memory, so multiple server workers would each have their own runs. Run a single worker or add shared storage.
- No HTTPS in the app itself; terminate TLS at the host or proxy.
- Run ids act as secrets: anyone who has one can read or change that run.
