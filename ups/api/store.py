"""In-memory run store with expiry. Nothing is written to disk."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from ups.core import Simulation, UPSError


class RunNotFoundError(UPSError):
    code = "run_not_found"


@dataclass
class RunRecord:
    run_id: str
    sim: Simulation
    last_active: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class RunStore:
    def __init__(self, ttl_seconds: float, max_runs: int, clock=time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_runs
        self._clock = clock
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = self._clock()
        for rid in [r for r, rec in self._runs.items() if now - rec.last_active > self._ttl]:
            del self._runs[rid]

    def create(self, sim: Simulation) -> str:
        with self._lock:
            self._purge()
            while len(self._runs) >= self._max:  # evict the least recently used
                oldest = min(self._runs.values(), key=lambda r: r.last_active)
                del self._runs[oldest.run_id]
            run_id = uuid.uuid4().hex
            self._runs[run_id] = RunRecord(run_id, sim, self._clock())
            return run_id

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            self._purge()
            rec = self._runs.get(run_id)
            if rec is None:
                raise RunNotFoundError("Run not found. It may have expired or been deleted.")
            rec.last_active = self._clock()
            return rec

    def delete(self, run_id: str) -> None:
        with self._lock:
            if self._runs.pop(run_id, None) is None:
                raise RunNotFoundError("Run not found. It may have expired or been deleted.")

    def count(self) -> int:
        with self._lock:
            self._purge()
            return len(self._runs)
