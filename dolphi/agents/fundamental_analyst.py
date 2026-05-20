from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, AnalystOutput
from ._common import aggregate_overall, default_symbols, normalise_per_ticker

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional fundamental analyst. For EACH symbol provided, evaluate valuation, "
    "growth, profitability, balance sheet, and quality. "
    "Return ONLY valid JSON, no markdown. Required shape:\n"
    "{\n"
    '  "per_ticker": {\n'
    '     "<SYMBOL>": {"reasoning": str, "score": float in [-1, 1], "details": {"pe": str, "growth": str, "balance_sheet": str}},\n'
    "     ...\n"
    "  },\n"
    '  "overall_reasoning": str,\n'
    '  "overall_score": float in [-1, 1]\n'
    "}"
)


def fundamental_analyst(state: AgentState, llm: OllamaClient, data: Any) -> dict[str, Any]:
    logger.info("Fundamental analyst running...")

    symbols = state.get("candidate_symbols") or default_symbols(state["user_profile"])

    financials: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        try:
            financials[sym] = data.get_financials(sym)
        except Exception as exc:
            logger.warning("Could not fetch financials for %s: %s", sym, exc)
            financials[sym] = {}

    fundamentals_block = []
    for sym, fin in financials.items():
        fundamentals_block.append(
            f"  - {sym}: P/E={fin.get('pe_ratio')}, Fwd P/E={fin.get('forward_pe')}, "
            f"EarnGrowth={fin.get('earnings_growth')}, RevGrowth={fin.get('revenue_growth')}, "
            f"D/E={fin.get('debt_to_equity')}, ProfitMargin={fin.get('profit_margins')}, "
            f"ROE={fin.get('return_on_equity')}, DivYield={fin.get('dividend_yield')}, "
            f"Beta={fin.get('beta')}, Sector={fin.get('sector')}"
        )

    prompt = (
        "Fundamental data for each symbol:\n"
        + "\n".join(fundamentals_block)
        + f"\n\nUser risk tolerance: {state['user_profile']['risk_tolerance']}\n"
        + f"Goal: {state['user_profile']['goal']}\n\n"
        "Score > 0 = undervalued or quality-with-growth, < 0 = overvalued or weakening. "
        "Be specific: mention the metric driving the read. "
        "Overall_reasoning is a one-paragraph view on the COHORT, not a recap of every ticker."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        per_ticker = {
            sym: AnalystOutput(reasoning="Fundamental analysis unavailable", score=0.0, details={"error": result["error"]})
            for sym in symbols
        }
        overall = AnalystOutput(
            reasoning="Fundamental analysis unavailable",
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
        logger.info("Fundamental analyst overall:\n%s", overall["reasoning"][:500])

    return {
        "per_ticker_fundamental": per_ticker,
        "fundamental_analysis": overall,
    }
