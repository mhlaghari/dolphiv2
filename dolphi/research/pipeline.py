from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import MarketNarrative, ThemeCluster, UniverseSymbol
from .beneficiaries import map_beneficiaries
from .narratives import discover_narratives
from .sources.base import ResearchDocument, ResearchSource
from .sources.registry import build_source_registry


DEFAULT_RESEARCH_QUERIES = [
    "stock market themes sector rotation earnings revisions",
    "market breadth leaders laggards stocks ETFs",
    "macro rates inflation credit conditions equities",
    "consumer spending retail payments earnings trends",
    "technology cloud software semiconductor capex",
    "energy power grid infrastructure demand",
    "healthcare utilities bonds defensive rotation",
]

DEEP_RESEARCH_QUERIES = [
    *DEFAULT_RESEARCH_QUERIES,
    "beginner friendly explanation of current market narratives stocks ETFs",
    "professional investor market narrative valuation catalysts risks",
    "investment banking sector themes capital expenditure margins demand",
    "earnings calls guidance upgrades downgrades sector winners losers",
    "cross asset narratives equities bonds rates dollar commodities",
    "undervalued overvalued sectors relative valuation market leadership",
    "global ADR market opportunities supply chain beneficiaries",
]


@dataclass
class ResearchThemeResult:
    documents: list[ResearchDocument]
    narratives: list[MarketNarrative]
    theme_clusters: list[ThemeCluster]


def discover_research_themes(
    profile: dict,
    universe: list[UniverseSymbol],
    research_sources: list[ResearchSource] | None = None,
    research_queries: list[str] | None = None,
    research_depth: str = "standard",
    newsapi_key: str | None = None,
    brave_api_key: str | None = None,
    searxng_base_url: str | None = None,
    llm: Any | None = None,
) -> ResearchThemeResult:
    is_deep = research_depth.lower() == "deep"
    queries = research_queries or (DEEP_RESEARCH_QUERIES if is_deep else DEFAULT_RESEARCH_QUERIES)
    limit_per_source = 15 if is_deep else 10
    if research_sources is None:
        documents = build_source_registry(
            newsapi_key=newsapi_key,
            brave_api_key=brave_api_key,
            searxng_base_url=searxng_base_url,
        ).fetch_all(queries, limit_per_source=limit_per_source)
    else:
        documents = []
        for query in queries:
            for source in research_sources:
                documents.extend(source.fetch(query, limit=limit_per_source))

    narratives = discover_narratives(documents)
    clusters = map_beneficiaries(narratives, universe, profile, llm=llm)
    return ResearchThemeResult(documents=documents, narratives=narratives, theme_clusters=clusters)
