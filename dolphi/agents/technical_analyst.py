from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, AnalystOutput
from ._common import aggregate_overall, default_symbols, normalise_per_ticker

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional technical analyst specialising in equity markets. "
    "For EACH of the symbols provided you must produce a short, candid technical read. "
    "Return ONLY valid JSON, no markdown. Required shape:\n"
    "{\n"
    '  "per_ticker": {\n'
    '     "<SYMBOL>": {"reasoning": str, "score": float in [-1, 1], "details": {"trend": str, "support": str, "resistance": str}},\n'
    "     ...\n"
    "  },\n"
    '  "overall_reasoning": str,\n'
    '  "overall_score": float in [-1, 1]\n'
    "}"
)


def technical_analyst(state: AgentState, llm: OllamaClient, data: Any) -> dict[str, Any]:
    logger.info("Technical analyst running...")

    symbols = state.get("candidate_symbols") or default_symbols(state["user_profile"])
    market = data.get_market_summary()
    sectors = data.get_sector_performance()

    price_data: dict[str, float] = {}
    for sym in symbols:
        try:
            price_data[sym] = data.get_stock_price(sym)
        except Exception as exc:
            logger.warning("Could not fetch price for %s: %s", sym, exc)

    bullet_list = "\n".join(
        f"  - {sym}: last={price_data.get(sym, 'n/a')}" for sym in symbols
    )

    prompt = (
        f"Market context:\n"
        f"  SPX: {market.get('spx_level')}, VIX: {market.get('vix_level')}\n"
        f"  Sector 1d performance (%): {sectors}\n\n"
        f"Symbols to assess (one short read each):\n{bullet_list}\n\n"
        f"User risk tolerance: {state['user_profile']['risk_tolerance']}\n"
        f"Goal: {state['user_profile']['goal']}\n\n"
        "Score > 0 = bullish technicals, < 0 = bearish. Cite trend, support, and resistance briefly. "
        "Overall_reasoning is a one-paragraph summary of the market backdrop, NOT a recap of every ticker."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        per_ticker = {
            sym: AnalystOutput(reasoning="Technical analysis unavailable", score=0.0, details={"error": result["error"]})
            for sym in symbols
        }
        overall = AnalystOutput(
            reasoning="Technical analysis unavailable",
            score=0.0,
            details={"error": result["error"], "per_ticker_count": len(per_ticker)},
        )
    else:
        per_ticker = normalise_per_ticker(result.get("per_ticker"), symbols)
        overall = aggregate_overall(
            per_ticker,
            explicit_score=result.get("overall_score"),
            explicit_reasoning=result.get("overall_reasoning"),
        )

    if state.get("config", {}).get("verbose"):
        logger.info("Technical analyst overall:\n%s", overall["reasoning"][:500])

    return {
        "per_ticker_technical": per_ticker,
        "technical_analysis": overall,
    }
