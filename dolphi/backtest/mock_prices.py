"""Deterministic historical prices for offline backtests."""

from __future__ import annotations

from datetime import datetime


# Anchor prices on month-end dates used by demo_decisions.jsonl backtest window.
_ANCHORS: dict[str, dict[str, float]] = {
    "2024-01-31": {
        "SPY": 480.0,
        "NVDA": 620.0,
        "TSM": 110.0,
        "BND": 72.0,
        "CEG": 150.0,
        "SMH": 220.0,
        "AMD": 165.0,
        "AVGO": 1200.0,
    },
    "2024-04-30": {
        "SPY": 495.0,
        "NVDA": 860.0,
        "TSM": 125.0,
        "BND": 71.5,
        "CEG": 175.0,
        "SMH": 245.0,
        "AMD": 155.0,
        "AVGO": 1280.0,
    },
    "2024-07-31": {
        "SPY": 520.0,
        "NVDA": 980.0,
        "TSM": 135.0,
        "BND": 72.5,
        "CEG": 190.0,
        "SMH": 260.0,
        "AMD": 145.0,
        "AVGO": 1350.0,
    },
    "2024-10-31": {
        "SPY": 540.0,
        "NVDA": 1320.0,
        "TSM": 170.0,
        "BND": 73.0,
        "CEG": 210.0,
        "SMH": 285.0,
        "AMD": 160.0,
        "AVGO": 1500.0,
    },
    "2024-12-31": {
        "SPY": 555.0,
        "NVDA": 1380.0,
        "TSM": 175.0,
        "BND": 73.5,
        "CEG": 215.0,
        "SMH": 295.0,
        "AMD": 125.0,
        "AVGO": 1520.0,
    },
}


def _parse_day(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return None


class MockHistoricalPrices:
    """Linearly interpolates anchor prices between known month-end dates."""

    def __init__(self, anchors: dict[str, dict[str, float]] | None = None):
        self._anchors = anchors or _ANCHORS
        self._sorted_dates = sorted(self._anchors.keys())
        self.calls: list[tuple[str, str | None]] = []

    def get_stock_price(self, symbol: str, date: str | None = None) -> float:
        self.calls.append((symbol, date))
        target = date or self._sorted_dates[-1]
        target_dt = _parse_day(target)
        if target_dt is None:
            raise ValueError(f"Invalid date: {target}")

        sym = symbol.upper()
        if target in self._anchors and sym in self._anchors[target]:
            return float(self._anchors[target][sym])

        # Find bracketing anchor dates
        before = None
        after = None
        for anchor_date in self._sorted_dates:
            anchor_dt = _parse_day(anchor_date)
            if anchor_dt is None:
                continue
            if anchor_dt <= target_dt:
                before = anchor_date
            if anchor_dt >= target_dt and after is None:
                after = anchor_date

        if before is None:
            before = self._sorted_dates[0]
        if after is None:
            after = self._sorted_dates[-1]

        if before == after:
            bucket = self._anchors.get(before, {})
            if sym not in bucket:
                raise ValueError(f"No mock price for {sym} @ {target}")
            return float(bucket[sym])

        start_dt = _parse_day(before)
        end_dt = _parse_day(after)
        if start_dt is None or end_dt is None or end_dt == start_dt:
            raise ValueError(f"Cannot interpolate {sym} @ {target}")

        start_px = self._anchors[before].get(sym)
        end_px = self._anchors[after].get(sym)
        if start_px is None or end_px is None:
            raise ValueError(f"No mock price series for {sym}")

        ratio = (target_dt - start_dt).days / (end_dt - start_dt).days
        return float(start_px + (end_px - start_px) * ratio)
