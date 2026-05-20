from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, RiskEvaluation

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a risk assessment agent specializing in aggressive investment profiles. "
    "Evaluate whether the proposed bull case is appropriate for an aggressive investor. "
    "Output ONLY valid JSON with keys: reasoning (str), fits_profile (bool), adjusted_score (float)."
)


def _latest_case(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[-1] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def risk_aggressive(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, list[RiskEvaluation]]:
    logger.info("Risk (aggressive) evaluation running...")

    bull = _latest_case(state.get("bull_case", []))
    bear = _latest_case(state.get("bear_case", []))
    profile = state["user_profile"]

    prompt = (
        f"Bull case conviction: {bull.get('conviction')}\n"
        f"  Thesis: {bull.get('thesis', '')[:500]}\n"
        f"  Reasoning: {bull.get('reasoning', '')[:500]}\n\n"
        f"Bear case conviction: {bear.get('conviction')}\n"
        f"  Thesis: {bear.get('thesis', '')[:500]}\n\n"
        f"User profile: risk={profile['risk_tolerance']}, goal={profile['goal']}\n\n"
        "Evaluate: Does the bull case fit an aggressive risk profile? "
        "An aggressive investor seeks high growth, accepts volatility, and has a long time horizon. "
        "Adjusted score: 0.0 to 1.0 where higher means more suitable for aggressive investing."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        result = {"reasoning": "Risk evaluation unavailable", "fits_profile": True, "adjusted_score": 0.5}

    if state.get("config", {}).get("verbose"):
        logger.info("Risk aggressive eval: fits=%s, score=%s", result.get("fits_profile"), result.get("adjusted_score"))

    return {"risk_aggressive_eval": [RiskEvaluation(
        reasoning=result.get("reasoning", ""),
        fits_profile=bool(result.get("fits_profile", True)),
        adjusted_score=float(result.get("adjusted_score", 0.5)),
    )]}
