from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import yfinance as yf

from .cache import LRUCache, SQLiteCache
from .rate_limiter import exponential_backoff

logger = logging.getLogger(__name__)

_memory_cache = LRUCache()
_persistent_cache: Optional[SQLiteCache] = None


def set_persistent_cache(cache: SQLiteCache) -> None:
    global _persistent_cache
    _persistent_cache = cache


def _cache_key(prefix: str, *args: str) -> str:
    return f"yf:{prefix}:" + ":".join(str(a) for a in args)


def _from_cache_or_fetch(key: str, fetcher, skip_cache: bool = False):
    if not skip_cache:
        val = _memory_cache.get(key)
        if val is not None:
            logger.debug("LRU cache hit: %s", key)
            return val
        if _persistent_cache is not None:
            persistent_key = f"{key}"
            val = _persistent_cache.get(persistent_key)
            if val is not None:
                _memory_cache.set(key, val)
                return val
    result = fetcher()
    _memory_cache.set(key, result)
    if _persistent_cache is not None:
        _persistent_cache.set(key, result)
    return result


def _get_earliest_valid_date() -> str:
    return (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")


@exponential_backoff()
def get_stock_price(symbol: str, date: Optional[str] = None, skip_cache: bool = False) -> float:
    key = _cache_key("price", symbol, date or "latest")

    def _fetch() -> float:
        ticker = yf.Ticker(symbol)
        if date:
            end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            hist = ticker.history(start=date, end=end_date)
        else:
            hist = ticker.history(period="1d")
        if hist.empty:
            raise ValueError(f"No price data for {symbol} on {date or 'latest'}")
        return float(hist["Close"].iloc[-1])

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)


def get_financials(symbol: str, skip_cache: bool = False) -> dict[str, Any]:
    key = _cache_key("financials", symbol)

    def _fetch() -> dict[str, Any]:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "profit_margins": info.get("profitMargins"),
            "return_on_equity": info.get("returnOnEquity"),
            "market_cap": info.get("marketCap"),
            "dividend_yield": info.get("dividendYield"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "long_business_summary": info.get("longBusinessSummary", ""),
            "price_to_book": info.get("priceToBook"),
            "beta": info.get("beta"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)


def get_market_summary(skip_cache: bool = False) -> dict[str, Any]:
    key = _cache_key("market_summary")

    def _fetch() -> dict[str, Any]:
        spx = yf.Ticker("^GSPC")
        vix = yf.Ticker("^VIX")
        spx_hist = spx.history(period="1d")
        vix_hist = vix.history(period="1d")
        return {
            "spx_level": float(spx_hist["Close"].iloc[-1]) if not spx_hist.empty else None,
            "vix_level": float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else None,
        }

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)


def get_sector_performance(skip_cache: bool = False) -> dict[str, float]:
    key = _cache_key("sectors")

    def _fetch() -> dict[str, float]:
        sectors = [
            "XLF", "XLK", "XLV", "XLI", "XLP",
            "XLE", "XLB", "XLU", "XLRE", "XLY",
        ]
        result = {}
        for sym in sectors:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    close = float(hist["Close"].iloc[-1])
                    open_ = float(hist["Open"].iloc[0])
                    result[sym] = round((close - open_) / open_ * 100, 2)
            except Exception:
                pass
        return result

    return _from_cache_or_fetch(key, _fetch, skip_cache=skip_cache)
