"""Shared helpers for per-ticker analyst agents."""

from __future__ import annotations

from typing import Any

from ..models import AnalystOutput


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN check
        return default
    return max(-1.0, min(1.0, result))


def normalise_per_ticker(
    raw: Any,
    symbols: list[str],
) -> dict[str, AnalystOutput]:
    """Coerce a free-form LLM response into ``{SYM: AnalystOutput}``.

    Accepts a few shapes:
    - ``{"NVDA": {...}, "TSM": {...}}`` (preferred)
    - ``[{"symbol": "NVDA", ...}, ...]`` (fallback)
    Missing symbols get a neutral entry so downstream code stays simple.
    """
    by_symbol: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                by_symbol[str(key).upper()] = value
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            sym = str(entry.get("symbol", "")).upper()
            if sym:
                by_symbol[sym] = entry

    cleaned: dict[str, AnalystOutput] = {}
    for symbol in symbols:
        entry = by_symbol.get(symbol.upper(), {})
        cleaned[symbol] = AnalystOutput(
            reasoning=str(entry.get("reasoning", "")).strip(),
            score=safe_float(entry.get("score", 0.0)),
            details=entry.get("details", {}) if isinstance(entry.get("details"), dict) else {},
        )
    return cleaned


def aggregate_overall(
    per_ticker: dict[str, AnalystOutput],
    fallback_reasoning: str = "",
    explicit_score: Any = None,
    explicit_reasoning: Any = None,
) -> AnalystOutput:
    scored = [entry["score"] for entry in per_ticker.values() if entry.get("score") is not None]
    mean_score = sum(scored) / len(scored) if scored else 0.0
    score = safe_float(explicit_score, mean_score) if explicit_score is not None else mean_score
    reasoning = str(explicit_reasoning).strip() if explicit_reasoning else fallback_reasoning
    return AnalystOutput(
        reasoning=reasoning,
        score=score,
        details={
            "per_ticker_count": len(per_ticker),
            "mean_score": round(mean_score, 4),
        },
    )


def default_symbols(profile: dict, fallback: list[str] | None = None) -> list[str]:
    """Best-effort default when no candidates have been discovered yet."""
    preferred = {asset.strip().lower() for asset in profile.get("preferred_asset_classes", [])}
    symbols: list[str] = []
    if not preferred or "stocks" in preferred:
        symbols.extend(["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "JPM", "V"])
    if not preferred or "etfs" in preferred:
        symbols.extend(["SPY", "QQQ", "VTI", "BND", "AGG"])
    if "bonds" in preferred:
        symbols.extend(["BND", "AGG", "TLT", "SHY"])
    if "crypto" in preferred:
        symbols.extend(["BTC-USD", "ETH-USD"])
    return symbols or (fallback or ["SPY", "BND"])
