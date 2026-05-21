"""Dolphi — multi-agent investment researcher that proves itself wrong before recommending."""

from .api import (
    Allocation,
    CheckResult,
    DebateJudgment,
    EvaluateResult,
    Falsifier,
    RankedIdea,
    UserProfile,
    check_falsifiers,
    evaluate,
    get_decision_log,
    list_falsifiers,
)

__version__ = "0.3.0"

__all__ = [
    "Allocation",
    "CheckResult",
    "DebateJudgment",
    "EvaluateResult",
    "Falsifier",
    "RankedIdea",
    "UserProfile",
    "check_falsifiers",
    "evaluate",
    "get_decision_log",
    "list_falsifiers",
]
