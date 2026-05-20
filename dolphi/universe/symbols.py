from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ..models import UniverseSymbol


_DEFAULT_UNIVERSE: list[UniverseSymbol] = [
    {"symbol": "AAPL", "name": "Apple", "asset_type": "stock", "sector": "Technology", "industry": "Consumer Electronics", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "MSFT", "name": "Microsoft", "asset_type": "stock", "sector": "Technology", "industry": "Software", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "META", "name": "Meta Platforms", "asset_type": "stock", "sector": "Communication Services", "industry": "Internet Content", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "AMZN", "name": "Amazon", "asset_type": "stock", "sector": "Consumer Cyclical", "industry": "Internet Retail", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "GOOGL", "name": "Alphabet", "asset_type": "stock", "sector": "Communication Services", "industry": "Internet Content", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "NVDA", "name": "NVIDIA", "asset_type": "stock", "sector": "Technology", "industry": "Semiconductors", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "asset_type": "stock", "sector": "Technology", "industry": "Semiconductors", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "AVGO", "name": "Broadcom", "asset_type": "stock", "sector": "Technology", "industry": "Semiconductors", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "TSM", "name": "Taiwan Semiconductor Manufacturing", "asset_type": "stock", "sector": "Technology", "industry": "Semiconductors", "exchange": "NYSE", "is_adr": True},
    {"symbol": "ASML", "name": "ASML Holding", "asset_type": "stock", "sector": "Technology", "industry": "Semiconductor Equipment", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "MU", "name": "Micron Technology", "asset_type": "stock", "sector": "Technology", "industry": "Memory", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "CEG", "name": "Constellation Energy", "asset_type": "stock", "sector": "Utilities", "industry": "Electric Utilities", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "VST", "name": "Vistra", "asset_type": "stock", "sector": "Utilities", "industry": "Electric Utilities", "exchange": "NYSE", "is_adr": False},
    {"symbol": "NEE", "name": "NextEra Energy", "asset_type": "stock", "sector": "Utilities", "industry": "Renewable Utilities", "exchange": "NYSE", "is_adr": False},
    {"symbol": "ETN", "name": "Eaton", "asset_type": "stock", "sector": "Industrials", "industry": "Electrical Equipment", "exchange": "NYSE", "is_adr": False},
    {"symbol": "JPM", "name": "JPMorgan Chase", "asset_type": "stock", "sector": "Financial Services", "industry": "Banks", "exchange": "NYSE", "is_adr": False},
    {"symbol": "V", "name": "Visa", "asset_type": "stock", "sector": "Financial Services", "industry": "Credit Services", "exchange": "NYSE", "is_adr": False},
    {"symbol": "WMT", "name": "Walmart", "asset_type": "stock", "sector": "Consumer Defensive", "industry": "Discount Stores", "exchange": "NYSE", "is_adr": False},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "asset_type": "etf", "sector": "Broad Market", "industry": "Large Cap ETF", "exchange": "NYSEARCA", "is_adr": False},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "asset_type": "etf", "sector": "Broad Market", "industry": "Growth ETF", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "asset_type": "etf", "sector": "Broad Market", "industry": "Total Market ETF", "exchange": "NYSEARCA", "is_adr": False},
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "asset_type": "etf", "sector": "Fixed Income", "industry": "Bond ETF", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "asset_type": "etf", "sector": "Fixed Income", "industry": "Bond ETF", "exchange": "NYSEARCA", "is_adr": False},
    {"symbol": "SMH", "name": "VanEck Semiconductor ETF", "asset_type": "etf", "sector": "Technology", "industry": "Semiconductor ETF", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "SOXX", "name": "iShares Semiconductor ETF", "asset_type": "etf", "sector": "Technology", "industry": "Semiconductor ETF", "exchange": "NASDAQ", "is_adr": False},
    {"symbol": "XLU", "name": "Utilities Select Sector SPDR Fund", "asset_type": "etf", "sector": "Utilities", "industry": "Utilities ETF", "exchange": "NYSEARCA", "is_adr": False},
]


def default_universe() -> list[UniverseSymbol]:
    return [item.copy() for item in _DEFAULT_UNIVERSE]


def _normalize(symbol: str) -> str:
    return symbol.strip().upper()


def find_symbol(symbol: str, universe: Iterable[UniverseSymbol] | None = None) -> UniverseSymbol | None:
    target = _normalize(symbol)
    for item in universe or _DEFAULT_UNIVERSE:
        if item["symbol"] == target:
            return item.copy()
    return None


def symbols_for_profile(profile: dict, universe: Iterable[UniverseSymbol] | None = None) -> list[str]:
    preferred = {asset.strip().lower() for asset in profile.get("preferred_asset_classes", [])}
    include_stocks = not preferred or "stocks" in preferred
    include_etfs = not preferred or "etfs" in preferred
    selected: list[str] = []
    for item in universe or _DEFAULT_UNIVERSE:
        if item["asset_type"] == "stock" and include_stocks:
            selected.append(item["symbol"])
        elif item["asset_type"] == "etf" and include_etfs:
            selected.append(item["symbol"])
    return selected


def load_universe(path: str | Path | None = None) -> list[UniverseSymbol]:
    if path is None:
        return default_universe()

    rows: list[UniverseSymbol] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "symbol": _normalize(row["symbol"]),
                    "name": row.get("name", ""),
                    "asset_type": row.get("asset_type", "stock").lower(),
                    "sector": row.get("sector", ""),
                    "industry": row.get("industry", ""),
                    "exchange": row.get("exchange", ""),
                    "is_adr": row.get("is_adr", "").lower() in {"1", "true", "yes"},
                }
            )
    return rows
