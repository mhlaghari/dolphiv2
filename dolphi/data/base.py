from __future__ import annotations

import logging
from typing import Any, Optional

from . import alpha_vantage, newsapi_wrapper, yfinance_wrapper
from .cache import SQLiteCache

logger = logging.getLogger(__name__)


class MockDataFetcher:
    def get_stock_price(self, symbol: str, date: Optional[str] = None) -> float:
        prices = {
            "AAPL": 198.50, "MSFT": 425.30, "GOOGL": 175.20,
            "AMZN": 185.40, "NVDA": 880.10, "META": 510.60,
            "BND": 72.30, "AGG": 98.50, "SPY": 525.00,
            "VTI": 260.40, "QQQ": 440.20, "DIA": 390.80,
            "XLK": 210.50, "XLF": 38.20, "XLV": 145.30,
            "BTC-USD": 65000.0, "ETH-USD": 3400.0,
        }
        return prices.get(symbol.upper(), 100.0)

    def get_financials(self, symbol: str) -> dict[str, Any]:
        return {
            "pe_ratio": 25.0,
            "forward_pe": 22.0,
            "earnings_growth": 0.12,
            "revenue_growth": 0.15,
            "debt_to_equity": 0.5,
            "current_ratio": 2.0,
            "profit_margins": 0.20,
            "return_on_equity": 0.30,
            "market_cap": 2_000_000_000_000,
            "dividend_yield": 0.005,
            "sector": "Technology",
            "industry": "Software",
            "beta": 1.2,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 130.0,
        }

    def get_market_summary(self) -> dict[str, Any]:
        return {"spx_level": 5300.0, "vix_level": 14.5}

    def get_sector_performance(self) -> dict[str, float]:
        return {"XLK": 1.5, "XLF": 0.8, "XLV": -0.3, "XLE": 2.1}

    def get_headlines(self, query: str, days_back: int = 7) -> list[dict[str, str]]:
        return [
            {"title": f"{query} reports strong quarterly earnings", "description": "Revenue beat estimates by 5%", "source": "Mock News"},
            {"title": f"Analysts upgrade {query} rating", "description": "Price target increased", "source": "Mock News"},
        ]


class DataFetcher:
    def __init__(
        self,
        cache: SQLiteCache | None,
        skip_cache: bool = False,
        mock: bool = False,
        *,
        newsapi_key: str | None = None,
        alpha_vantage_key: str | None = None,
    ):
        self._skip_cache = skip_cache
        self._mock = mock

        if mock:
            self._mock_fetcher = MockDataFetcher()
            return

        if newsapi_key:
            newsapi_wrapper.set_api_key(newsapi_key)
        if alpha_vantage_key:
            alpha_vantage.set_api_key(alpha_vantage_key)

        if cache is None:
            return

        yfinance_wrapper.set_persistent_cache(cache)
        if alpha_vantage.is_available():
            alpha_vantage.set_persistent_cache(cache)
        if newsapi_wrapper.is_available():
            newsapi_wrapper.set_persistent_cache(cache)

    def get_stock_price(self, symbol: str, date: Optional[str] = None) -> float:
        if self._mock:
            return self._mock_fetcher.get_stock_price(symbol, date)
        try:
            return yfinance_wrapper.get_stock_price(symbol, date, skip_cache=self._skip_cache)
        except Exception as e:
            logger.warning("yfinance failed for %s: %s, trying Alpha Vantage", symbol, e)
            if alpha_vantage.is_available():
                return alpha_vantage.get_stock_price(symbol, date, skip_cache=self._skip_cache)
            raise

    def get_financials(self, symbol: str) -> dict[str, Any]:
        if self._mock:
            return self._mock_fetcher.get_financials(symbol)
        try:
            return yfinance_wrapper.get_financials(symbol, skip_cache=self._skip_cache)
        except Exception as e:
            logger.warning("yfinance financials failed for %s: %s, trying Alpha Vantage", symbol, e)
            if alpha_vantage.is_available():
                return alpha_vantage.get_financials(symbol, skip_cache=self._skip_cache)
            raise

    def get_market_summary(self) -> dict[str, Any]:
        if self._mock:
            return self._mock_fetcher.get_market_summary()
        return yfinance_wrapper.get_market_summary(skip_cache=self._skip_cache)

    def get_sector_performance(self) -> dict[str, float]:
        if self._mock:
            return self._mock_fetcher.get_sector_performance()
        return yfinance_wrapper.get_sector_performance(skip_cache=self._skip_cache)

    def get_headlines(self, query: str, days_back: int = 7) -> list[dict[str, str]]:
        if self._mock:
            return self._mock_fetcher.get_headlines(query, days_back)
        if newsapi_wrapper.is_available():
            try:
                return newsapi_wrapper.get_headlines(query, days_back, skip_cache=self._skip_cache)
            except Exception as e:
                logger.warning("NewsAPI failed: %s", e)
        logger.warning("No news source available for %s", query)
        return []
