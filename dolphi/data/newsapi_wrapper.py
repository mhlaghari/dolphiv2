from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from .cache import LRUCache, SQLiteCache
from .rate_limiter import RateLimitError, exponential_backoff

logger = logging.getLogger(__name__)

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
    return f"na:{prefix}:" + ":".join(str(a) for a in args)


@exponential_backoff()
def get_headlines(query: str, days_back: int = 7, skip_cache: bool = False) -> list[dict[str, str]]:
    if not _api_key:
        raise RuntimeError("NewsAPI key not configured")

    key = _cache_key("headlines", query, str(days_back))

    if not skip_cache:
        cached = _memory_cache.get(key)
        if cached is not None:
            return cached
        if _persistent_cache is not None:
            cached = _persistent_cache.get(key)
            if cached is not None:
                _memory_cache.set(key, cached)
                return cached

    from_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 10,
        "apiKey": _api_key,
    }
    resp = requests.get("https://newsapi.org/v2/everything", params=params, timeout=60)
    if resp.status_code == 429:
        raise RateLimitError("NewsAPI rate limit hit")
    resp.raise_for_status()
    data = resp.json()
    articles = [
        {
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "source": a.get("source", {}).get("name", ""),
            "url": a.get("url", ""),
            "published_at": a.get("publishedAt", ""),
        }
        for a in data.get("articles", [])
    ]
    _memory_cache.set(key, articles)
    if _persistent_cache is not None:
        _persistent_cache.set(key, articles)
    return articles
