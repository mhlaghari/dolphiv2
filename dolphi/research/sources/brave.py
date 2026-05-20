from __future__ import annotations

import logging

import requests

from .base import ResearchDocument

logger = logging.getLogger(__name__)


class BraveResearchSource:
    name = "brave"
    _SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, timeout: int = 20):
        self._api_key = api_key
        self._timeout = timeout

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        try:
            response = requests.get(
                self._SEARCH_URL,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
                params={
                    "q": query,
                    "count": min(max(limit, 1), 20),
                    "freshness": "pw",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Brave search failed for %s: %s", query, exc)
            return []

        documents: list[ResearchDocument] = []
        for result in response.json().get("web", {}).get("results", [])[:limit]:
            title = result.get("title", "")
            snippet = result.get("description") or result.get("extra_snippets", [""])[0]
            if not title and not snippet:
                continue
            documents.append(
                ResearchDocument(
                    title=title,
                    snippet=snippet,
                    source=f"{self.name}:web",
                    url=result.get("url", ""),
                    published_at=result.get("age") or result.get("page_age") or "",
                    query=query,
                )
            )
        return documents
