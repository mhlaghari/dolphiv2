from __future__ import annotations

import logging

import requests

from .base import ResearchDocument

logger = logging.getLogger(__name__)


class SearXNGResearchSource:
    name = "searxng"

    def __init__(self, base_url: str, timeout: int = 20):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        try:
            response = requests.get(
                f"{self._base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "news,general",
                    "language": "en",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("SearXNG search failed for %s: %s", query, exc)
            return []

        documents: list[ResearchDocument] = []
        for result in response.json().get("results", [])[:limit]:
            title = result.get("title", "")
            snippet = result.get("content") or result.get("snippet") or ""
            if not title and not snippet:
                continue
            engine = result.get("engine") or result.get("source") or "result"
            documents.append(
                ResearchDocument(
                    title=title,
                    snippet=snippet,
                    source=f"{self.name}:{engine}",
                    url=result.get("url", ""),
                    published_at=result.get("publishedDate") or result.get("published_at") or "",
                    query=query,
                )
            )
        return documents
