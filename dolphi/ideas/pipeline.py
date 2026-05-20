from __future__ import annotations

from typing import Any

from ..models import CandidateIdea, DiscoveryResult, ThemeCluster, UniverseSymbol
from ..research.pipeline import discover_research_themes
from ..research.sources.base import ResearchSource
from ..scoring.composite import rank_candidates
from ..themes.expander import expand_themes
from ..universe.symbols import default_universe, find_symbol, symbols_for_profile
from ..universe.validator import allowed_asset_types


def _safe_price(data: Any, symbol: str) -> float | None:
    try:
        return float(data.get_stock_price(symbol))
    except Exception:
        return None


def _safe_financials(data: Any, symbol: str) -> dict[str, Any]:
    try:
        return data.get_financials(symbol)
    except Exception:
        return {}


def _features(symbol: UniverseSymbol, price: float | None, financials: dict[str, Any], theme_strength: float) -> dict[str, float]:
    pe = financials.get("pe_ratio")
    beta = financials.get("beta")
    profit_margins = financials.get("profit_margins")
    momentum = 0.35 if price is not None else 0.1
    if symbol["sector"] == "Technology":
        momentum += 0.15
    valuation = 0.5
    if isinstance(pe, (int, float)):
        valuation = 0.75 if 0 < pe < 35 else 0.35
    liquidity = 0.95 if symbol["asset_type"] == "etf" or symbol["exchange"] in {"NASDAQ", "NYSE"} else 0.65
    quality = 0.0
    if isinstance(profit_margins, (int, float)) and profit_margins > 0.15:
        quality += 0.1
    if isinstance(beta, (int, float)) and beta < 1.5:
        quality += 0.05
    return {
        "market_trend": min(momentum + quality, 1.0),
        "valuation": valuation,
        "liquidity": liquidity,
        "relationship_strength": theme_strength,
    }


def _theme_strength(symbol: str, clusters: list[ThemeCluster]) -> tuple[str, float, list[str], dict[str, float]]:
    for cluster in clusters:
        if cluster["seed_symbol"] == symbol:
            evidence_features = _cluster_features(cluster, 0.9)
            return cluster["theme"], 0.9, [cluster["thesis"]], evidence_features
        for relation in cluster["related_symbols"]:
            if relation["symbol"] == symbol:
                strength = float(relation["confidence"])
                evidence_features = _cluster_features(cluster, strength)
                return cluster["theme"], strength, [relation["evidence"], cluster["thesis"]], evidence_features
    return "General market opportunity", 0.25, ["Passed baseline universe screen."], {
        "narrative_confidence": 0.25,
        "source_diversity": 0.1,
        "source_recency": 0.25,
    }


def _cluster_features(cluster: ThemeCluster, strength: float) -> dict[str, float]:
    return {
        "narrative_confidence": float(cluster.get("narrative_confidence", strength)),
        "source_diversity": float(cluster.get("source_diversity", 0.25)),
        "source_recency": float(cluster.get("freshness", 0.5)),
    }


def _candidate(symbol: UniverseSymbol, data: Any, clusters: list[ThemeCluster]) -> CandidateIdea:
    price = _safe_price(data, symbol["symbol"])
    financials = _safe_financials(data, symbol["symbol"])
    theme, strength, evidence, evidence_features = _theme_strength(symbol["symbol"], clusters)
    risks = []
    if symbol["is_adr"]:
        risks.append("ADR and country-specific risk")
    if symbol["sector"] == "Technology":
        risks.append("Valuation and cyclicality risk")
    elif symbol["asset_type"] == "etf":
        risks.append("Underlying basket risk")
    return {
        "symbol": symbol["symbol"],
        "name": symbol["name"],
        "asset_type": symbol["asset_type"],
        "is_adr": symbol["is_adr"],
        "sector": symbol["sector"],
        "theme": theme,
        "price": price,
        "features": {**_features(symbol, price, financials, strength), **evidence_features},
        "evidence": evidence,
        "risks": risks or ["Market risk"],
    }


def discover_ranked_ideas(
    profile: dict,
    data: Any,
    top_k: int = 5,
    seed_symbols: list[str] | None = None,
    universe: list[UniverseSymbol] | None = None,
    research_sources: list[ResearchSource] | None = None,
    research_queries: list[str] | None = None,
    research_depth: str = "standard",
    newsapi_key: str | None = None,
    brave_api_key: str | None = None,
    searxng_base_url: str | None = None,
    llm: Any | None = None,
) -> DiscoveryResult:
    universe = universe or default_universe()
    seeds = [symbol.strip().upper() for symbol in (seed_symbols or []) if find_symbol(symbol, universe)]
    documents = []
    narratives = []
    clusters: list[ThemeCluster] = []
    if seeds:
        clusters.extend(expand_themes(seeds, universe, profile=profile, llm=llm))
    if not seeds or research_queries or research_sources:
        research = discover_research_themes(
            profile,
            universe,
            research_sources=research_sources,
            research_queries=research_queries,
            research_depth=research_depth,
            newsapi_key=newsapi_key,
            brave_api_key=brave_api_key,
            searxng_base_url=searxng_base_url,
            llm=llm,
        )
        documents = research.documents
        narratives = research.narratives
        clusters.extend(research.theme_clusters)

    candidate_symbols = set() if clusters else set(symbols_for_profile(profile, universe))
    preferred = allowed_asset_types(profile)

    def allows(symbol: str) -> bool:
        entry = find_symbol(symbol, universe)
        return entry is not None and (not preferred or entry["asset_type"] in preferred)

    for cluster in clusters:
        if allows(cluster["seed_symbol"]):
            candidate_symbols.add(cluster["seed_symbol"])
        candidate_symbols.update(
            relation["symbol"]
            for relation in cluster["related_symbols"]
            if allows(relation["symbol"])
        )

    candidates = [
        _candidate(symbol, data, clusters)
        for symbol in universe
        if symbol["symbol"] in candidate_symbols
    ]
    ranked = rank_candidates(candidates, top_k=top_k)
    return DiscoveryResult(
        candidate_symbols=[idea["symbol"] for idea in ranked],
        ranked_ideas=ranked,
        theme_clusters=clusters,
        documents=documents,
        narratives=narratives,
    )
