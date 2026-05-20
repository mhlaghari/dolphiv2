from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, RiskEvaluation

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a risk assessment agent specializing in conservative investment profiles. "
    "Evaluate whether the proposed bear case risks are appropriate for a conservative investor. "
    "Output ONLY valid JSON with keys: reasoning (str), fits_profile (bool), adjusted_score (float)."
)


def _latest_case(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[-1] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def risk_conservative(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, list[RiskEvaluation]]:
    logger.info("Risk (conservative) evaluation running...")

    bull = _latest_case(state.get("bull_case", []))
    bear = _latest_case(state.get("bear_case", []))
    profile = state["user_profile"]

    prompt = (
        f"Bull case conviction: {bull.get('conviction')}\n"
        f"  Thesis: {bull.get('thesis', '')[:500]}\n\n"
        f"Bear case conviction: {bear.get('conviction')}\n"
        f"  Thesis: {bear.get('thesis', '')[:500]}\n"
        f"  Reasoning: {bear.get('reasoning', '')[:500]}\n\n"
        f"User profile: risk={profile['risk_tolerance']}, goal={profile['goal']}\n\n"
        "Evaluate: Do the bear case risks need to be hedged for a conservative profile? "
        "A conservative investor prioritizes capital preservation, seeks stable income, "
        "and has low risk tolerance. "
        "Adjusted score: 0.0 to 1.0 where higher means the bear case risks strongly suggest "
        "a conservative/defensive allocation."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        result = {"reasoning": "Risk evaluation unavailable", "fits_profile": True, "adjusted_score": 0.5}

    if state.get("config", {}).get("verbose"):
        logger.info("Risk conservative eval: fits=%s, score=%s", result.get("fits_profile"), result.get("adjusted_score"))

    return {"risk_conservative_eval": [RiskEvaluation(
        reasoning=result.get("reasoning", ""),
        fits_profile=bool(result.get("fits_profile", True)),
        adjusted_score=float(result.get("adjusted_score", 0.5)),
    )]}
