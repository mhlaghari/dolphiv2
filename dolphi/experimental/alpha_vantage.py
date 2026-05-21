from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .cache import LRUCache, SQLiteCache
from .rate_limiter import RateLimitError, exponential_backoff

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"

_memory_cache = LRUCache()
_persistent_cache: Optional[SQLiteCache] = None
_api_key: Optional[str] = None


def set_persistent_cache(cache: SQLiteCache) -> None:
    global _persistent_cache
    _persistent_cache = cache


def set_api_key(key: str) -> None:
    global _api_key
    _api_key = key


def is_available() -> bool:
    return _api_key is not None


def _cache_key(prefix: str, *args: str) -> str:
    return f"av:{prefix}:" + ":".join(str(a) for a in args)


def _from_cache_or_fetch(key: str, fetcher, skip_cache: bool = False):
    if not skip_cache:
        val = _memory_cache.get(key)
        if val is not None:
            logger.debug("LRU cache hit: %s", key)
            return val
        if _persistent_cache is not None:
            val = _persistent_cache.get(key)
            if val is not None:
                _memory_cache.set(key, val)
                return val
    result = fetcher()
    _memory_cache.set(key, result)
    if _persistent_cache is not None:
        _persistent_cache.set(key, result)
    return result


@exponential_backoff()
def _call_av(params: dict[str, str]) -> dict[str, Any]:
    if not _api_key:
        raise RuntimeError("Alpha Vantage API key not configured")
    params["apikey"] = _api_key
    resp = requests.get(BASE_URL, params=params, timeout=60)
    if resp.status_code == 429:
        raise RateLimitError("Alpha Vantage rate limit hit")
    resp.raise_for_status()
    data = resp.json()
    if "Error Message" in data:
        raise ValueError(data["Error Message"])
    if "Note" in data:
        raise RateLimitError(data["Note"])
    return data


def get_financials(symbol: str, skip_cache: bool = False) -> dict[str, Any]:
    key = _cache_key("financials", symbol)

    def _fetch() -> dict[str, Any]:
        data = _call_av({"function": "OVERVIEW", "symbol": symbol})
        return {
            "pe_ratio": _safe_float(data.get("PERatio")),
            "forward_pe": _safe_float(data.get("ForwardPE")),
            "earnings_growth": _safe_float(data.get("EarningsGrowth")),
            "revenue_growth": _safe_float(data.get("RevenueGrowth")),
            "debt_to_equity": _safe_float(data.get("DebtToEquity")),
            "current_ratio": _safe_float(data.get("CurrentRatio")),
            "profit_margins": _safe_float(data.get("ProfitMargin")),
            "return_on_equity": _safe_float(data.get("ReturnOnEquity")),
            "market_cap": _safe_float(data.get("MarketCapitalization")),
            "dividend_yield": _safe_float(data.get("DividendYield")),
            "sector": data.get("Sector"),
            "industry": data.get("Industry"),
            "beta": _safe_float(data.get("Beta")),
            "fifty_two_week_high": _safe_float(data.get("52WeekHigh")),
            "fifty_two_week_low": _safe_float(data.get("52WeekLow")),
        }

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)


def get_stock_price(symbol: str, date: Optional[str] = None, skip_cache: bool = False) -> float:
    key = _cache_key("price", symbol, date or "latest")

    def _fetch() -> float:
        if date:
            data = _call_av({"function": "TIME_SERIES_DAILY", "symbol": symbol})
            series = data.get("Time Series (Daily)", {})
            if date in series:
                return float(series[date]["4. close"])
            raise ValueError(f"No data for {symbol} on {date}")
        else:
            data = _call_av({"function": "GLOBAL_QUOTE", "symbol": symbol})
            price_str = data.get("Global Quote", {}).get("05. price")
            if price_str is None:
                raise ValueError(f"No price for {symbol}")
            return float(price_str)

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
