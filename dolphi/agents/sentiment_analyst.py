from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, AnalystOutput
from ._common import aggregate_overall, default_symbols, normalise_per_ticker

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional sentiment analyst. For EACH symbol, read the supplied news headlines and "
    "estimate near-term investor mood. Return ONLY valid JSON, no markdown. Required shape:\n"
    "{\n"
    '  "per_ticker": {\n'
    '     "<SYMBOL>": {"reasoning": str, "score": float in [-1, 1], "details": {"key_headline": str, "tone": str}},\n'
    "     ...\n"
    "  },\n"
    '  "overall_reasoning": str,\n'
    '  "overall_score": float in [-1, 1]\n'
    "}"
)


def sentiment_analyst(state: AgentState, llm: OllamaClient, data: Any) -> dict[str, Any]:
    logger.info("Sentiment analyst running...")

    symbols = state.get("candidate_symbols") or default_symbols(state["user_profile"])

    headlines_by_symbol: dict[str, list[dict[str, str]]] = {}
    for sym in symbols:
        try:
            headlines_by_symbol[sym] = data.get_headlines(sym, days_back=7)[:5]
        except Exception as exc:
            logger.warning("Could not fetch headlines for %s: %s", sym, exc)
            headlines_by_symbol[sym] = []

    try:
        market_headlines = data.get_headlines("stock market", days_back=3)[:5]
    except Exception:
        market_headlines = []

    headlines_block = []
    for sym in symbols:
        items = headlines_by_symbol.get(sym, [])
        if not items:
            headlines_block.append(f"  - {sym}: no headlines available")
            continue
        rendered = "; ".join(f"[{h.get('source', '?')}] {h.get('title', '')}" for h in items)
        headlines_block.append(f"  - {sym}: {rendered}")

    market_text = (
        "\n".join(f"  - [{h.get('source', '?')}] {h.get('title', '')}" for h in market_headlines)
        or "  - none"
    )

    prompt = (
        "Per-symbol news headlines (last 7 days):\n"
        + "\n".join(headlines_block)
        + "\n\nBroad market headlines (last 3 days):\n"
        + market_text
        + f"\n\nUser risk tolerance: {state['user_profile']['risk_tolerance']}\n"
        + f"Goal: {state['user_profile']['goal']}\n\n"
        "Score > 0 = bullish tone, < 0 = bearish tone. Cite the specific headline that drives the read. "
        "Overall_reasoning is a one-paragraph view on the BROADER mood, not a recap of every ticker."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        per_ticker = {
            sym: AnalystOutput(reasoning="Sentiment analysis unavailable", score=0.0, details={"error": result["error"]})
            for sym in symbols
        }
        overall = AnalystOutput(
            reasoning="Sentiment analysis unavailable",
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
        logger.info("Sentiment analyst overall:\n%s", overall["reasoning"][:500])

    return {
        "per_ticker_sentiment": per_ticker,
        "sentiment_analysis": overall,
    }
