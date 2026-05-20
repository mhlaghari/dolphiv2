from __future__ import annotations

from typing import Any

from ..models import MarketNarrative, ThemeCluster, UniverseSymbol
from ..research.beneficiaries import map_beneficiaries
from ..universe.symbols import default_universe, find_symbol


def _seed_narrative(symbol: str, name: str, sector: str, industry: str) -> MarketNarrative:
    text = (
        f"{name} sits in {industry} within {sector}. "
        "Research related supply chains, customers, infrastructure, power demand, and ETF proxies."
    )
    if "semiconductor" in industry.lower():
        text += " AI accelerators, foundries, memory, semiconductor equipment, and data center power demand are relevant."
    return MarketNarrative(
        title=f"{name} Related Opportunity Chain",
        thesis=text,
        evidence=[text],
        source_count=1,
        source_diversity=0.33,
        freshness=0.5,
        confidence=0.55,
        related_sectors=[sector],
        keywords=text.lower().replace(",", " ").replace(".", " ").split(),
        source_urls=[],
    )


def expand_themes(
    seed_symbols: list[str],
    universe: list[UniverseSymbol] | None = None,
    profile: dict | None = None,
    llm: Any | None = None,
) -> list[ThemeCluster]:
    universe = universe or default_universe()
    profile = profile or {"preferred_asset_classes": ["stocks", "etfs"]}
    clusters: list[ThemeCluster] = []
    seen_seeds: set[str] = set()

    for raw_symbol in seed_symbols:
        symbol = raw_symbol.strip().upper()
        seed = find_symbol(symbol, universe)
        if seed is None or symbol in seen_seeds:
            continue
        seen_seeds.add(symbol)

        narrative = _seed_narrative(symbol, seed["name"], seed["sector"], seed["industry"])
        for cluster in map_beneficiaries([narrative], universe, profile, llm=llm):
            cluster["seed_symbol"] = symbol
            clusters.append(cluster)

    return clusters
