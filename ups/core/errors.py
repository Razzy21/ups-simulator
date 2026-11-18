"""Errors raised by the simulation core.

Each carries a stable `code`; the API layer maps codes to HTTP statuses.
The core itself knows nothing about HTTP.
"""
from __future__ import annotations


class UPSError(Exception):
    code = "ups_error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ScenarioValidationError(UPSError):
    code = "invalid_scenario"

    def __init__(self, issues, source: str | None = None):
        self.issues = list(issues)
        self.source = source
        head = f"Scenario {source!r} is invalid" if source else "Scenario is invalid"
        lines = "\n".join(f"  - {i['path']}: {i['message']}" for i in self.issues)
        super().__init__(f"{head} ({len(self.issues)} problem(s)):\n{lines}", {"issues": self.issues})


class DecisionPendingError(UPSError):
    code = "decision_pending"


class NoDecisionPendingError(UPSError):
    code = "no_decision_pending"


class DecisionMismatchError(UPSError):
    code = "decision_mismatch"


class InvalidOptionError(UPSError):
    code = "invalid_option"


class InvalidAdvanceError(UPSError):
    code = "invalid_advance"


class RunCompleteError(UPSError):
    code = "run_complete"
