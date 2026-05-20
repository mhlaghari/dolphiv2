"""LLM-as-judge for falsifier quality.

Scores each falsifier on four axes (0-1 each). The judge model is **fixed
across the leaderboard** — no model ever judges its own output. This is the
single biggest methodology lever; choose the judge once at the start of the
eval and never swap it mid-run.

Default judge: Anthropic Claude Sonnet 4.6 (set via ``--judge`` on the eval
CLI). Local-Ollama judging is supported for reproducibility but the rubric
was calibrated on Sonnet 4.6 outputs.

Bias mitigation:
- Single-judge mode is the default. A secondary judge can be run on a sample
  via ``--secondary-judge``; the report includes the Spearman correlation
  between primary and secondary scores.
- The judge prompt names the four axes explicitly so it cannot conflate them.
- Scores are clamped to [0, 1] and rounded server-side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..agents._common import safe_float
from ..llm.json_mixin import JsonGeneratingClient
from ..models import BullAssumption, Falsifier

logger = logging.getLogger(__name__)


_JUDGE_SYSTEM_PROMPT = (
    "You are a research-quality judge grading falsifiers in an investment "
    "pre-mortem. A falsifier is a specific, dated, observable event that "
    "would break a named load-bearing assumption of a bull thesis.\n\n"
    "Score each falsifier on four axes, each in [0.0, 1.0]:\n"
    "  - horizon_observability: 1.0 if the predicted event is verifiable "
    "    within the stated horizon and the horizon is ≤ 12 months. 0.0 if "
    "    the event is vague, unverifiable, or beyond 12 months.\n"
    "  - assumption_coherence: 1.0 if the falsifier, if it occurred, would "
    "    actually break the named assumption. 0.0 if it is orthogonal, a "
    "    strawman, or breaks a different claim.\n"
    "  - indicator_specificity: 1.0 if the leading indicator is a concrete "
    "    measurable quantity a researcher could check at least weekly with "
    "    named source. 0.0 if vague ('watch the market').\n"
    "  - probability_calibration: 1.0 if the stated probability is "
    "    defensible for the horizon and event. 0.0 if obviously over- or "
    "    under-stated (e.g., 0.9 probability for a 30-day specific catalyst).\n\n"
    "Return ONLY valid JSON, no markdown:\n"
    "{\n"
    '  "horizon_observability": float in [0,1],\n'
    '  "assumption_coherence": float in [0,1],\n'
    '  "indicator_specificity": float in [0,1],\n'
    '  "probability_calibration": float in [0,1],\n'
    '  "comment": str (one sentence)\n'
    "}\n"
    "Do not hedge with 0.5 unless the falsifier is genuinely ambiguous."
)


@dataclass(frozen=True)
class FalsifierScore:
    horizon_observability: float
    assumption_coherence: float
    indicator_specificity: float
    probability_calibration: float
    comment: str = ""

    @property
    def aggregate(self) -> float:
        return (
            self.horizon_observability
            + self.assumption_coherence
            + self.indicator_specificity
            + self.probability_calibration
        ) / 4.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "horizon_observability": round(self.horizon_observability, 3),
            "assumption_coherence": round(self.assumption_coherence, 3),
            "indicator_specificity": round(self.indicator_specificity, 3),
            "probability_calibration": round(self.probability_calibration, 3),
            "aggregate": round(self.aggregate, 3),
            "comment": self.comment,
        }


_ZERO_SCORE = FalsifierScore(0.0, 0.0, 0.0, 0.0, comment="judge_error")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class FalsifierJudge:
    """Score one falsifier at a time against its target assumption + thesis."""

    def __init__(self, llm: JsonGeneratingClient) -> None:
        self._llm = llm

    def score(
        self,
        *,
        falsifier: Falsifier,
        targeted_assumption: BullAssumption | str,
        thesis: str,
    ) -> FalsifierScore:
        assumption_text = (
            targeted_assumption["text"]
            if isinstance(targeted_assumption, dict)
            else str(targeted_assumption)
        )
        prompt = (
            f"=== BULL THESIS ===\n{thesis.strip()[:800]}\n\n"
            f"=== ASSUMPTION THE FALSIFIER CLAIMS TO BREAK ===\n"
            f"{assumption_text.strip()[:400]}\n\n"
            f"=== FALSIFIER UNDER REVIEW ===\n"
            f"failure_mode: {falsifier['failure_mode']}\n"
            f"probability: {falsifier['probability']}\n"
            f"horizon: {falsifier['horizon']}\n"
            f"leading_indicator: {falsifier['leading_indicator']}\n"
            f"breaks_assumption (model's own claim): {falsifier['breaks_assumption']}\n\n"
            "Score on the four axes."
        )
        raw = self._llm.generate_json(prompt, system=_JUDGE_SYSTEM_PROMPT, temperature=0.1)
        if "error" in raw:
            logger.warning("Judge failed: %s", raw.get("error"))
            return _ZERO_SCORE
        try:
            return FalsifierScore(
                horizon_observability=_clamp(safe_float(raw.get("horizon_observability"), 0.0)),
                assumption_coherence=_clamp(safe_float(raw.get("assumption_coherence"), 0.0)),
                indicator_specificity=_clamp(safe_float(raw.get("indicator_specificity"), 0.0)),
                probability_calibration=_clamp(safe_float(raw.get("probability_calibration"), 0.0)),
                comment=str(raw.get("comment", "")).strip()[:300],
            )
        except Exception as exc:  # noqa: BLE001 — judge must never crash the harness
            logger.warning("Judge response coercion failed: %s", exc)
            return _ZERO_SCORE


@dataclass
class ScoredFalsifier:
    """A falsifier + its FalsifierScore + the fixture/model context."""

    model: str
    fixture_slug: str
    falsifier: Falsifier
    targeted_assumption: str
    score: FalsifierScore
    latency_seconds: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)
