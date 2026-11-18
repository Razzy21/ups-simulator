"""API settings, read from environment variables (all optional)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    scenarios_dir: Path = ROOT / "scenarios"
    client_dir: Path = ROOT / "client"
    run_ttl_minutes: int = 120          # a run is deleted after this long without activity
    max_runs: int = 500                 # oldest-idle runs are evicted beyond this
    rate_limit_per_minute: int = 120    # per client address; 0 disables
    access_token: Optional[str] = None  # if set, /api/* requires header X-Access-Token

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            run_ttl_minutes=_int("UPS_RUN_TTL_MINUTES", 120),
            max_runs=_int("UPS_MAX_RUNS", 500),
            rate_limit_per_minute=_int("UPS_RATE_LIMIT_PER_MINUTE", 120),
            access_token=os.environ.get("UPS_ACCESS_TOKEN") or None,
        )
