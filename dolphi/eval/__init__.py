"""Falsifier-quality eval harness.

Grades the pre-mortem falsifiers produced by different LLM models against a
fixed set of curated bull-case fixtures, using a fixed-judge LLM-as-judge to
score each falsifier on four axes:

- horizon_observability  — is the predicted event verifiable inside ≤12 months?
- assumption_coherence   — does it actually break the assumption it names?
- indicator_specificity  — is the leading indicator concretely checkable weekly?
- probability_calibration — is the estimate defensible for the stated horizon?

Public API:

    from dolphi.eval import BullCaseFixture, FalsifierJudge, ModelSpec, run_eval
    from dolphi.eval.fixtures import all_fixtures
    from dolphi.eval.report import write_reports

The CLI entry point is ``python -m dolphi.eval``; see ``dolphi/eval/cli.py``.
"""

from __future__ import annotations

from .fixtures import BullCaseFixture, all_fixtures
from .harness import EvalReport, ModelResult, ModelSpec, run_eval
from .judge import FalsifierJudge, FalsifierScore

__all__ = [
    "BullCaseFixture",
    "EvalReport",
    "FalsifierJudge",
    "FalsifierScore",
    "ModelResult",
    "ModelSpec",
    "all_fixtures",
    "run_eval",
]
