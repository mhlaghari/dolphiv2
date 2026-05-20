"""Closed-loop reflection: realised returns vs SPY for prior allocations.

The decision log's ``.jsonl`` sidecar records every prior recommendation in
machine-readable form. This module reads those records, fetches realised
prices for each allocated symbol from the decision date to today, and
computes alpha vs SPY.

The resulting summary is injected into the portfolio manager's prompt
so the agent can be honest about which past bets paid off and which
didn't — closing the loop between Dolphi's recommendations and what
actually happened in the market.

Safety / cost properties:
- Skips decisions younger than ``min_age_days`` (no meaningful return).
- Skips decisions older than ``max_age_days`` (too stale to be informative).
- Limits to the most recent ``max_decisions`` entries (bounded LLM cost).
- Drops any symbol that can't be priced (graceful per-symbol failure).
- All price fetches go through the cached DataFetcher.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _DataLike(Protocol):
    def get_stock_price(self, symbol: str, date: str | None = ...) -> float:
        ...


_BENCHMARK = "SPY"


def load_past_decisions(jsonl_path: Path) -> list[dict[str, Any]]:
    """Read all decision records from the sidecar JSONL log.

    Returns an empty list if the file doesn't exist.
    Silently skips lines that fail to parse.
    """
    if not jsonl_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping unparseable decision log line: %s", line[:80])
    return records


def _parse_decision_date(record: dict[str, Any]) -> datetime | None:
    raw = record.get("decision_date") or (record.get("timestamp") or "")[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _days_since(decision_date: datetime, now: datetime) -> int:
    return max((now - decision_date).days, 0)


def _safe_price(data: _DataLike, symbol: str, date: str | None) -> float | None:
    try:
        price = float(data.get_stock_price(symbol, date))
        return price if price > 0 else None
    except Exception as exc:  # noqa: BLE001 — we want to swallow ANY fetch error
        logger.debug("Reflection price fetch failed for %s @ %s: %s", symbol, date, exc)
        return None


def _return_pct(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start * 100.0


def _reflect_one(record: dict[str, Any], data: _DataLike, now: datetime) -> dict[str, Any] | None:
    decision_date = _parse_decision_date(record)
    if decision_date is None:
        return None

    days_held = _days_since(decision_date, now)
    date_str = decision_date.strftime("%Y-%m-%d")

    spy_start = _safe_price(data, _BENCHMARK, date_str)
    spy_end = _safe_price(data, _BENCHMARK, None)
    if spy_start is None or spy_end is None:
        return None
    spy_return = _return_pct(spy_start, spy_end)

    per_symbol: list[dict[str, Any]] = []
    for allocation in record.get("allocations", []):
        symbol = allocation.get("symbol")
        if not symbol or symbol in {"CASH"}:
            continue
        start = _safe_price(data, symbol, date_str)
        end = _safe_price(data, symbol, None)
        if start is None or end is None:
            continue
        symbol_return = _return_pct(start, end)
        per_symbol.append(
            {
                "symbol": symbol,
                "allocation_pct": float(allocation.get("allocation_pct", 0.0)),
                "symbol_return_pct": round(symbol_return, 2),
                "alpha_pct": round(symbol_return - spy_return, 2),
            }
        )

    if not per_symbol:
        return None

    portfolio_return = sum(
        item["allocation_pct"] / 100.0 * item["symbol_return_pct"] for item in per_symbol
    )
    return {
        "decision_date": date_str,
        "days_held": days_held,
        "spy_return_pct": round(spy_return, 2),
        "portfolio_return_pct": round(portfolio_return, 2),
        "portfolio_alpha_pct": round(portfolio_return - spy_return, 2),
        "per_symbol": per_symbol,
    }


def _summarise_text(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    lines = [
        f"{len(entries)} prior recommendation(s) graded against SPY:",
    ]
    for entry in entries:
        lines.append(
            f"  - {entry['decision_date']} ({entry['days_held']}d held): "
            f"portfolio {entry['portfolio_return_pct']:+.2f}% vs SPY {entry['spy_return_pct']:+.2f}% "
            f"→ alpha {entry['portfolio_alpha_pct']:+.2f}%"
        )
        for item in sorted(entry["per_symbol"], key=lambda i: -i["alpha_pct"])[:3]:
            lines.append(
                f"      best  {item['symbol']}: {item['symbol_return_pct']:+.2f}% "
                f"(alpha {item['alpha_pct']:+.2f}%)"
            )
        for item in sorted(entry["per_symbol"], key=lambda i: i["alpha_pct"])[:1]:
            lines.append(
                f"      worst {item['symbol']}: {item['symbol_return_pct']:+.2f}% "
                f"(alpha {item['alpha_pct']:+.2f}%)"
            )
    return "\n".join(lines)


def compute_reflection(
    jsonl_path: Path,
    data: _DataLike,
    *,
    min_age_days: int = 14,
    max_age_days: int = 540,
    max_decisions: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute realised alpha for prior allocations.

    Returns a dict with shape:
        {
            "entries_count": int,
            "average_alpha_pct": float | None,
            "best_alpha_symbol": str | None,
            "worst_alpha_symbol": str | None,
            "summary_text": str,
            "entries": list[dict],   # detailed per-decision entries
        }
    Returns an empty-ish dict when no eligible decisions exist.
    """
    now = now or datetime.now(timezone.utc)
    records = load_past_decisions(jsonl_path)
    if not records:
        return {"entries_count": 0, "summary_text": "", "entries": []}

    eligible: list[dict[str, Any]] = []
    for record in reversed(records):
        decision_date = _parse_decision_date(record)
        if decision_date is None:
            continue
        days = _days_since(decision_date, now)
        if days < min_age_days or days > max_age_days:
            continue
        eligible.append(record)
        if len(eligible) >= max_decisions:
            break

    if not eligible:
        return {"entries_count": 0, "summary_text": "", "entries": []}

    detailed: list[dict[str, Any]] = []
    for record in eligible:
        entry = _reflect_one(record, data, now)
        if entry is not None:
            detailed.append(entry)

    if not detailed:
        return {"entries_count": 0, "summary_text": "", "entries": []}

    all_symbol_alphas: list[tuple[str, float]] = []
    for entry in detailed:
        for item in entry["per_symbol"]:
            all_symbol_alphas.append((item["symbol"], item["alpha_pct"]))

    if all_symbol_alphas:
        best = max(all_symbol_alphas, key=lambda item: item[1])
        worst = min(all_symbol_alphas, key=lambda item: item[1])
        best_symbol = best[0]
        worst_symbol = worst[0]
    else:
        best_symbol = None
        worst_symbol = None

    portfolio_alphas = [entry["portfolio_alpha_pct"] for entry in detailed]
    average_alpha = round(sum(portfolio_alphas) / len(portfolio_alphas), 2) if portfolio_alphas else None

    return {
        "entries_count": len(detailed),
        "average_alpha_pct": average_alpha,
        "best_alpha_symbol": best_symbol,
        "worst_alpha_symbol": worst_symbol,
        "summary_text": _summarise_text(detailed),
        "entries": detailed,
    }
