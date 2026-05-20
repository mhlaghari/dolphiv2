from __future__ import annotations

from dataclasses import dataclass

from ...data import newsapi_wrapper
from .base import ResearchDocument, ResearchSource, dedupe_documents
from .brave import BraveResearchSource
from .searxng import SearXNGResearchSource
from .static import StaticResearchSource


class NewsAPIResearchSource:
    name = "newsapi"

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        articles = newsapi_wrapper.get_headlines(query, days_back=7)[:limit]
        return [
            ResearchDocument(
                title=article.get("title", ""),
                snippet=article.get("description", ""),
                source=article.get("source", self.name),
                url=article.get("url", f"newsapi://{query}/{i}"),
                published_at=article.get("published_at", ""),
                query=query,
            )
            for i, article in enumerate(articles)
        ]


@dataclass
class ResearchSourceRegistry:
    sources: list[ResearchSource]

    def fetch_all(self, queries: list[str], limit_per_source: int = 10) -> list[ResearchDocument]:
        documents: list[ResearchDocument] = []
        for query in queries:
            for source in self.sources:
                documents.extend(source.fetch(query, limit=limit_per_source))
        return dedupe_documents(documents)


def build_source_registry(
    static_documents: list[ResearchDocument] | None = None,
    newsapi_key: str | None = None,
    searxng_base_url: str | None = None,
    brave_api_key: str | None = None,
) -> ResearchSourceRegistry:
    sources: list[ResearchSource] = [StaticResearchSource(static_documents)]
    if brave_api_key:
        sources.append(BraveResearchSource(brave_api_key))
    if searxng_base_url:
        sources.append(SearXNGResearchSource(searxng_base_url))
    if newsapi_key:
        newsapi_wrapper.set_api_key(newsapi_key)
        sources.append(NewsAPIResearchSource())
    return ResearchSourceRegistry(sources)
