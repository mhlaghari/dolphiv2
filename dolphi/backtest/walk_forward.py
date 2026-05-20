"""Walk-forward backtester — monthly cadence, portfolio vs SPY buy-and-hold.

Reads rebalance events from the decision-log JSONL sidecar (or a bundled
demo fixture in mock mode), forward-fills allocations at each month-end,
and compounds hold-period returns between rebalance dates.

Cash allocations earn 0% over the hold period. Symbols that cannot be
priced at either boundary of a period are dropped and weights are
renormalised; if nothing remains priced, the period contributes 0%.

This is a *sanity-check* backtest of past Dolphi recommendations — not
a claim of achievable alpha. See PLAN.md Phase 2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from ..memory.reflection import load_past_decisions

logger = logging.getLogger(__name__)

_BENCHMARK = "SPY"
_FIXTURE = Path(__file__).with_name("fixtures") / "demo_decisions.jsonl"


class _DataLike(Protocol):
    def get_stock_price(self, symbol: str, date: str | None = ...) -> float:
        ...


@dataclass
class WalkForwardResult:
    start_date: str
    end_date: str
    rebalance_dates: list[str]
    portfolio_equity: list[float]
    spy_equity: list[float]
    period_returns_portfolio: list[float]
    period_returns_spy: list[float]
    total_return_portfolio_pct: float
    total_return_spy_pct: float
    alpha_pct: float
    max_drawdown_portfolio_pct: float
    periods: int
    source: str = "decision_log"
    notes: list[str] = field(default_factory=list)


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _month_ends(start: datetime, end: datetime) -> list[datetime]:
    """Return month-end dates from start through end (inclusive), ascending."""
    if start > end:
        return []
    points: list[datetime] = []
    year, month = start.year, start.month
    while True:
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        month_end = next_month.replace(day=1) - timedelta(days=1)
        month_end = month_end.replace(tzinfo=timezone.utc)
        if month_end >= start and month_end <= end:
            points.append(month_end)
        if month_end >= end:
            break
        year, month = next_month.year, next_month.month
    if not points or points[-1] < end:
        if end not in points:
            points.append(end)
    return sorted(set(points))


def _load_demo_decisions() -> list[dict[str, Any]]:
    if not _FIXTURE.exists():
        return []
    return load_past_decisions(_FIXTURE)


def _decisions_to_schedule(records: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Convert JSONL records to (date, allocations) sorted ascending."""
    schedule: list[tuple[str, list[dict[str, Any]]]] = []
    for record in records:
        raw = record.get("decision_date") or (record.get("timestamp") or "")[:10]
        if not raw:
            continue
        allocations = record.get("allocations") or []
        if not allocations:
            continue
        schedule.append((raw[:10], allocations))
    schedule.sort(key=lambda item: item[0])
    return schedule


def _allocations_at(schedule: list[tuple[str, list[dict[str, Any]]]], as_of: str) -> list[dict[str, Any]] | None:
    chosen: list[dict[str, Any]] | None = None
    for date, allocations in schedule:
        if date <= as_of:
            chosen = allocations
        else:
            break
    return chosen


def _safe_price(data: _DataLike, symbol: str, date: str) -> float | None:
    try:
        price = float(data.get_stock_price(symbol, date))
        return price if price > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Backtest price fetch failed for %s @ %s: %s", symbol, date, exc)
        return None


def _period_return(
    data: _DataLike,
    allocations: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> tuple[float, list[str]]:
    notes: list[str] = []
    priced: list[tuple[float, float]] = []  # (weight, return_pct)
    for item in allocations:
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol or symbol == "CASH":
            continue
        weight = float(item.get("allocation_pct", 0.0))
        if weight <= 0:
            continue
        start_px = _safe_price(data, symbol, start_date)
        end_px = _safe_price(data, symbol, end_date)
        if start_px is None or end_px is None:
            notes.append(f"Dropped {symbol} for {start_date}→{end_date} (missing price)")
            continue
        ret = (end_px - start_px) / start_px * 100.0
        priced.append((weight, ret))

    if not priced:
        return 0.0, notes

    total_weight = sum(weight for weight, _ in priced)
    if total_weight <= 0:
        return 0.0, notes

    portfolio_ret = sum(weight * ret for weight, ret in priced) / total_weight
    return portfolio_ret, notes


def _spy_return(data: _DataLike, start_date: str, end_date: str) -> float:
    start_px = _safe_price(data, _BENCHMARK, start_date)
    end_px = _safe_price(data, _BENCHMARK, end_date)
    if start_px is None or end_px is None:
        return 0.0
    return (end_px - start_px) / start_px * 100.0


def _compound(equity: float, period_return_pct: float) -> float:
    return equity * (1.0 + period_return_pct / 100.0)


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak * 100.0
            max_dd = max(max_dd, dd)
    return round(max_dd, 2)


def run_walk_forward_backtest(
    data: _DataLike,
    *,
    jsonl_path: Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    cadence_days: int = 30,
    use_demo_fixture: bool = False,
) -> WalkForwardResult:
    """Run a walk-forward backtest over decision-log allocations vs SPY.

    Parameters
    ----------
    data:
        Price fetcher (DataFetcher or test double).
    jsonl_path:
        Path to decision log JSONL sidecar. Ignored when ``use_demo_fixture``.
    start_date / end_date:
        ISO dates bounding the backtest window. Defaults: earliest decision
        → today (UTC).
    cadence_days:
        Approximate rebalance spacing. Values near 30 produce monthly
        month-end marks; other values step forward by that many days.
    use_demo_fixture:
        When True, load bundled demo decisions (for ``--mock-data``).
    """
    notes: list[str] = []
    if use_demo_fixture:
        records = _load_demo_decisions()
        source = "demo_fixture"
    elif jsonl_path is not None:
        records = load_past_decisions(jsonl_path)
        source = "decision_log"
    else:
        records = []
        source = "empty"

    schedule = _decisions_to_schedule(records)
    if not schedule:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return WalkForwardResult(
            start_date=start_date or today,
            end_date=end_date or today,
            rebalance_dates=[],
            portfolio_equity=[100.0],
            spy_equity=[100.0],
            period_returns_portfolio=[],
            period_returns_spy=[],
            total_return_portfolio_pct=0.0,
            total_return_spy_pct=0.0,
            alpha_pct=0.0,
            max_drawdown_portfolio_pct=0.0,
            periods=0,
            source=source,
            notes=["No rebalance events found — run `dolphi` a few times or use --mock-data."],
        )

    parsed_start = _parse_date(start_date) if start_date else _parse_date(schedule[0][0])
    parsed_end = _parse_date(end_date) if end_date else datetime.now(timezone.utc)
    if parsed_start is None or parsed_end is None:
        raise ValueError("Invalid start_date or end_date")

    if cadence_days >= 28:
        rebalance_points = _month_ends(parsed_start, parsed_end)
    else:
        rebalance_points = []
        cursor = parsed_start
        step = timedelta(days=cadence_days)
        while cursor <= parsed_end:
            rebalance_points.append(cursor)
            cursor = cursor + step
        if rebalance_points[-1] != parsed_end:
            rebalance_points.append(parsed_end)

    rebalance_dates = [point.strftime("%Y-%m-%d") for point in rebalance_points]
    if len(rebalance_dates) < 2:
        notes.append("Window too short for at least one hold period.")
        return WalkForwardResult(
            start_date=rebalance_dates[0] if rebalance_dates else parsed_start.strftime("%Y-%m-%d"),
            end_date=rebalance_dates[-1] if rebalance_dates else parsed_end.strftime("%Y-%m-%d"),
            rebalance_dates=rebalance_dates,
            portfolio_equity=[100.0],
            spy_equity=[100.0],
            period_returns_portfolio=[],
            period_returns_spy=[],
            total_return_portfolio_pct=0.0,
            total_return_spy_pct=0.0,
            alpha_pct=0.0,
            max_drawdown_portfolio_pct=0.0,
            periods=0,
            source=source,
            notes=notes,
        )

    portfolio_equity = [100.0]
    spy_equity = [100.0]
    period_returns_portfolio: list[float] = []
    period_returns_spy: list[float] = []

    for idx in range(len(rebalance_dates) - 1):
        period_start = rebalance_dates[idx]
        period_end = rebalance_dates[idx + 1]
        allocations = _allocations_at(schedule, period_start)
        if allocations is None:
            notes.append(f"No allocation before {period_start}; period skipped.")
            period_returns_portfolio.append(0.0)
            period_returns_spy.append(0.0)
            portfolio_equity.append(portfolio_equity[-1])
            spy_equity.append(spy_equity[-1])
            continue

        port_ret, period_notes = _period_return(data, allocations, period_start, period_end)
        notes.extend(period_notes)
        spy_ret = _spy_return(data, period_start, period_end)

        period_returns_portfolio.append(round(port_ret, 3))
        period_returns_spy.append(round(spy_ret, 3))
        portfolio_equity.append(round(_compound(portfolio_equity[-1], port_ret), 3))
        spy_equity.append(round(_compound(spy_equity[-1], spy_ret), 3))

    total_port = portfolio_equity[-1] - 100.0
    total_spy = spy_equity[-1] - 100.0

    return WalkForwardResult(
        start_date=rebalance_dates[0],
        end_date=rebalance_dates[-1],
        rebalance_dates=rebalance_dates,
        portfolio_equity=portfolio_equity,
        spy_equity=spy_equity,
        period_returns_portfolio=period_returns_portfolio,
        period_returns_spy=period_returns_spy,
        total_return_portfolio_pct=round(total_port, 2),
        total_return_spy_pct=round(total_spy, 2),
        alpha_pct=round(total_port - total_spy, 2),
        max_drawdown_portfolio_pct=_max_drawdown(portfolio_equity),
        periods=len(period_returns_portfolio),
        source=source,
        notes=notes,
    )
