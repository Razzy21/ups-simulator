"""HTTP API: a thin layer over ups.core. All simulation rules live in the core."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from ups.core import Simulation, UPSError, load_scenarios_dir

from .settings import Settings
from .store import RunNotFoundError, RunStore

SLUG = r"^[a-z][a-z0-9-]{0,47}$"
RUN_ID = r"^[0-9a-f]{32}$"
MAX_BODY_BYTES = 10_000
DISCLAIMER = ("Training simulator, not a forecast. Outcomes illustrate trade-offs under each "
              "scenario's stated assumptions; they do not predict real projects.")

STATUS_FOR_CODE = {
    "run_not_found": 404, "scenario_not_found": 404,
    "decision_pending": 409, "no_decision_pending": 409, "decision_mismatch": 409, "run_complete": 409,
    "invalid_option": 400, "invalid_advance": 400,
}

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class CreateRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarioId: str = Field(pattern=SLUG)


class AdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=1, ge=1, le=365)
    untilNextEvent: bool = False


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eventId: str = Field(pattern=SLUG)
    decisionId: str = Field(pattern=SLUG)
    optionId: str = Field(pattern=SLUG)


class RateLimiter:
    """Sliding one-minute window per client address. In memory only."""

    def __init__(self, per_minute: int, clock=time.monotonic):
        self._max = per_minute
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                    del self._hits[k]
            return True


def _error(status: int, code: str, message: str, details: Optional[dict] = None, headers=None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {}}},
                        status_code=status, headers=headers)


def create_app(settings: Optional[Settings] = None, clock=time.monotonic) -> FastAPI:
    settings = settings or Settings.from_env()
    scenarios = load_scenarios_dir(settings.scenarios_dir)  # fails fast with clear errors
    store = RunStore(settings.run_ttl_minutes * 60, settings.max_runs, clock)
    limiter = RateLimiter(settings.rate_limit_per_minute, clock) if settings.rate_limit_per_minute > 0 else None

    app = FastAPI(title="Universal Project Simulator", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.state.store = store

    # ----- guards ----------------------------------------------------------
    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        response: Optional[Response] = None
        if path.startswith("/api/") and path != "/api/health":
            length = request.headers.get("content-length", "")
            if limiter and not limiter.allow(request.client.host if request.client else "unknown"):
                response = _error(429, "rate_limited", "Too many requests. Please slow down.", headers={"Retry-After": "60"})
            elif length.isdigit() and int(length) > MAX_BODY_BYTES:
                response = _error(413, "payload_too_large", "Request body is too large.")
            elif settings.access_token and not hmac.compare_digest(
                    request.headers.get("x-access-token", "").encode(), settings.access_token.encode()):
                response = _error(401, "unauthorized", "A valid access token is required.")
        if response is None:
            response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ----- errors ----------------------------------------------------------
    @app.exception_handler(UPSError)
    async def ups_error(_: Request, exc: UPSError):
        return _error(STATUS_FOR_CODE.get(exc.code, 400), exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError):
        issues = [{"path": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return _error(422, "invalid_request", "The request was not valid.", {"issues": issues})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        return _error(500, "internal_error", "Something went wrong on the server.")

    # ----- helpers ---------------------------------------------------------
    def state(run_id: str, sim: Simulation) -> dict:
        return {"runId": run_id, **sim.snapshot()}

    def scenario_or_404(scenario_id: str):
        sc = scenarios.get(scenario_id)
        if sc is None:
            raise UPSErrorNotFound("Scenario not found.")
        return sc

    class UPSErrorNotFound(UPSError):
        code = "scenario_not_found"

    # ----- routes ----------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta():
        return {
            "disclaimer": DISCLAIMER,
            "retention": {
                "storage": "server memory only; nothing is written to disk",
                "runExpiresAfterMinutes": settings.run_ttl_minutes,
                "maxStoredRuns": settings.max_runs,
                "personalData": "none collected; runs are anonymous",
                "deletion": "a run is deleted on request, after it expires, or when the server restarts",
            },
            "accessTokenRequired": bool(settings.access_token),
        }

    @app.get("/api/scenarios")
    def list_scenarios():
        return {"scenarios": [{"id": s.id, "title": s.title, "description": s.description,
                               "durationDays": s.duration_days} for s in scenarios.values()]}

    @app.get("/api/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str = Path(pattern=SLUG)):
        return scenario_or_404(scenario_id).public_info()

    @app.post("/api/runs", status_code=201)
    def create_run(body: CreateRunIn):
        sim = Simulation(scenario_or_404(body.scenarioId))
        run_id = store.create(sim)
        return state(run_id, sim)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            return state(run_id, rec.sim)

    @app.post("/api/runs/{run_id}/advance")
    def advance(body: AdvanceIn, run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            if body.untilNextEvent:
                rec.sim.advance_to_next_event()
            else:
                rec.sim.advance(body.days)
            return state(run_id, rec.sim)

    @app.post("/api/runs/{run_id}/decisions")
    def submit_decision(body: DecisionIn, run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            rec.sim.submit_decision(body.eventId, body.decisionId, body.optionId)
            return state(run_id, rec.sim)

    @app.get("/api/runs/{run_id}/history")
    def history(run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            return {"runId": run_id, "entries": rec.sim.history}

    @app.get("/api/runs/{run_id}/summary")
    def summary(run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            return {"runId": run_id, **rec.sim.health_summary()}

    @app.get("/api/runs/{run_id}/replay")
    def replay(run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            return {"runId": run_id, "frames": rec.sim.replay_frames()}

    @app.post("/api/runs/{run_id}/reset")
    def reset(run_id: str = Path(pattern=RUN_ID)):
        rec = store.get(run_id)
        with rec.lock:
            rec.sim.reset()
            return state(run_id, rec.sim)

    @app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(run_id: str = Path(pattern=RUN_ID)):
        store.delete(run_id)
        return Response(status_code=204)

    # ----- client ----------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(settings.client_dir / "index.html")

    app.mount("/static", StaticFiles(directory=settings.client_dir), name="static")
    return app
