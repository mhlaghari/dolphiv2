from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, ResearcherOutput

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a bullish equity researcher. Given technical, fundamental, and sentiment analysis, "
    "construct a compelling bullish case for the market and specific assets. "
    "Output ONLY valid JSON with keys: reasoning (str), thesis (str), conviction (float 0-1)."
)


def bull_researcher(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, list[ResearcherOutput]]:
    logger.info("Bull researcher running...")

    tech = state.get("technical_analysis", {})
    fund = state.get("fundamental_analysis", {})
    sent = state.get("sentiment_analysis", {})

    prompt = (
        f"Technical analysis score: {tech.get('score')}\n"
        f"  Reasoning: {tech.get('reasoning', '')[:500]}\n\n"
        f"Fundamental analysis score: {fund.get('score')}\n"
        f"  Reasoning: {fund.get('reasoning', '')[:500]}\n\n"
        f"Sentiment analysis score: {sent.get('score')}\n"
        f"  Reasoning: {sent.get('reasoning', '')[:500]}\n\n"
        f"User risk tolerance: {state['user_profile']['risk_tolerance']}\n"
        f"Goal: {state['user_profile']['goal']}\n\n"
        "Build the strongest bullish case given this data. "
        "Focus on sectors/assets that look most promising. "
        "Set conviction based on how strongly the data supports a bullish view (0.0 = no conviction, 1.0 = maximum)."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.4)
    if "error" in result:
        result = {"reasoning": "Bull case unavailable", "thesis": "Neutral", "conviction": 0.5}

    if state.get("config", {}).get("verbose"):
        logger.info("Bull researcher thesis:\n%s", result.get("thesis", "")[:500])

    return {"bull_case": [ResearcherOutput(
        reasoning=result.get("reasoning", ""),
        thesis=result.get("thesis", ""),
        conviction=float(result.get("conviction", 0.5)),
    )]}
