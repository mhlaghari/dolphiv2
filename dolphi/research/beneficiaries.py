"""Map market narratives to candidate beneficiary tickers.

Two paths:

1. **LLM-driven** (Phase 1.2, preferred) — pass an LLM client and we ask
   the model to propose US-listed tickers most directly exposed to each
   narrative. Output is then validated against the open universe and
   filtered by the user's asset preferences. The LLM never bypasses the
   universe — anything it hallucinates is dropped.

2. **Keyword** (legacy fallback) — a small static table keyed on
   ``_RELATION_KEYWORDS``. Used when no LLM is provided (e.g. unit tests,
   offline mode, or when the LLM call fails entirely).

The cluster shape returned is the same in both paths.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..models import MarketNarrative, ThemeCluster, ThemeRelation, UniverseSymbol
from ..universe.validator import validate_symbol

logger = logging.getLogger(__name__)


class _LLMLike(Protocol):
    def generate_json(self, prompt: str, system: str | None = ..., temperature: float = ...) -> dict[str, Any]:
        ...


_RELATION_KEYWORDS: list[tuple[set[str], list[tuple[str, str]]]] = [
    (
        {"ai", "accelerator", "accelerators", "chip", "chips", "semiconductor", "semiconductors", "foundry", "memory"},
        [
            ("NVDA", "AI accelerator leader"),
            ("TSM", "advanced foundry capacity"),
            ("ASML", "semiconductor equipment"),
            ("AMD", "AI accelerator competitor"),
            ("MU", "AI memory supplier"),
            ("SMH", "semiconductor ETF proxy"),
            ("SOXX", "semiconductor ETF proxy"),
        ],
    ),
    (
        {"power", "grid", "electricity", "data", "center", "centers", "infrastructure"},
        [
            ("CEG", "data center power supplier"),
            ("VST", "power producer"),
            ("NEE", "renewable utility"),
            ("ETN", "electrical infrastructure"),
            ("XLU", "utilities ETF proxy"),
        ],
    ),
    (
        {"defensive", "rotation", "uncertainty", "bonds", "healthcare"},
        [
            ("BND", "bond ballast"),
            ("AGG", "aggregate bond ETF proxy"),
            ("XLU", "defensive utilities exposure"),
        ],
    ),
    (
        {"bank", "banks", "credit", "loan", "loans", "payment", "payments", "financial", "financials"},
        [
            ("JPM", "large-cap bank exposure"),
            ("V", "payment network exposure"),
            ("SPY", "broad financial conditions proxy"),
        ],
    ),
    (
        {"consumer", "retail", "spending", "sales", "ecommerce", "online", "discount", "stores"},
        [
            ("WMT", "defensive retail spending exposure"),
            ("AMZN", "online retail and cloud-linked consumer exposure"),
            ("V", "consumer payments exposure"),
        ],
    ),
    (
        {"cloud", "software", "platform", "advertising", "internet", "search", "mobile"},
        [
            ("MSFT", "cloud and software platform exposure"),
            ("GOOGL", "search advertising and cloud platform exposure"),
            ("META", "digital advertising platform exposure"),
            ("AAPL", "consumer device ecosystem exposure"),
            ("QQQ", "large-cap growth ETF proxy"),
        ],
    ),
]


_BENEFICIARIES_SYSTEM_PROMPT = (
    "You are a buyside research analyst. Given a market narrative with thesis and supporting "
    "evidence, propose the US-listed tickers most directly exposed to it. "
    "Prefer concrete businesses (single-name equities) over ETFs, but include 1-2 ETF proxies "
    "if they are the cleanest way to express the theme. ONLY propose tickers that genuinely "
    "exist on NASDAQ or NYSE. Each relationship must be specific (e.g. 'AI accelerator pricing "
    "power' beats 'AI exposure'). Return ONLY valid JSON, no markdown, no commentary:\n"
    "{\n"
    '  "beneficiaries": [\n'
    "    {\n"
    '      "symbol": str (uppercase ticker),\n'
    '      "relationship": str (one short phrase),\n'
    '      "evidence": str (one sentence tying ticker to the thesis),\n'
    '      "confidence": float in [0, 1]\n'
    "    }, ... (5-8 distinct entries)\n"
    "  ]\n"
    "}"
)


def _evidence_for(narrative: MarketNarrative, symbol: str, relationship: str) -> str:
    snippet = narrative.evidence[0] if narrative.evidence else narrative.thesis
    return f"{relationship}: {snippet[:220]}"


def _cluster_from(narrative: MarketNarrative, related: list[ThemeRelation]) -> ThemeCluster:
    return {
        "seed_symbol": narrative.title,
        "theme": narrative.title,
        "thesis": narrative.thesis,
        "related_symbols": related,
        "source_urls": narrative.source_urls,
        "narrative_confidence": narrative.confidence,
        "source_count": narrative.source_count,
        "source_diversity": narrative.source_diversity,
        "freshness": narrative.freshness,
    }


def _keyword_relations(
    narrative: MarketNarrative,
    universe: list[UniverseSymbol],
    profile: dict,
) -> list[ThemeRelation]:
    keyword_set = set(narrative.keywords)
    related: list[ThemeRelation] = []
    seen: set[str] = set()
    for keywords, candidates in _RELATION_KEYWORDS:
        if not keyword_set.intersection(keywords):
            continue
        for symbol, relationship in candidates:
            entry = validate_symbol(symbol, universe, profile)
            if entry is None or symbol in seen:
                continue
            seen.add(symbol)
            related.append(
                {
                    "symbol": symbol,
                    "relationship": relationship,
                    "evidence": _evidence_for(narrative, symbol, relationship),
                    "confidence": round(min(narrative.confidence * 0.9, 1.0), 3),
                }
            )
    return related


def _llm_relations(
    narrative: MarketNarrative,
    universe: list[UniverseSymbol],
    profile: dict,
    llm: _LLMLike,
    max_relations: int = 8,
) -> list[ThemeRelation]:
    evidence_block = "\n".join(f"  - {item[:280]}" for item in narrative.evidence[:5])
    prompt = (
        f"Narrative title: {narrative.title}\n"
        f"Thesis: {narrative.thesis[:1200]}\n"
        f"Supporting evidence:\n{evidence_block or '  (none provided)'}\n\n"
        f"User asset preferences: {profile.get('preferred_asset_classes', ['stocks', 'etfs'])}\n"
        f"Risk tolerance: {profile.get('risk_tolerance', 'Moderate')}\n\n"
        "Propose 5-8 US-listed beneficiary tickers exposed to this narrative."
    )
    result = llm.generate_json(prompt, system=_BENEFICIARIES_SYSTEM_PROMPT, temperature=0.3)
    if not isinstance(result, dict) or "error" in result:
        if isinstance(result, dict) and "error" in result:
            logger.warning("Beneficiary mapper LLM failed for '%s': %s", narrative.title, result.get("error"))
        return []

    raw_items = result.get("beneficiaries")
    if not isinstance(raw_items, list):
        return []

    relations: list[ThemeRelation] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        entry = validate_symbol(symbol, universe, profile)
        if entry is None:
            logger.debug("Beneficiary mapper dropped unknown/disallowed symbol: %s", symbol)
            continue
        seen.add(symbol)
        relationship = str(raw.get("relationship", "exposed to narrative")).strip() or "exposed to narrative"
        evidence_text = str(raw.get("evidence", "")).strip()
        try:
            llm_confidence = float(raw.get("confidence", narrative.confidence))
        except (TypeError, ValueError):
            llm_confidence = narrative.confidence
        confidence = round(min(max(llm_confidence, 0.0), 1.0) * min(narrative.confidence + 0.2, 1.0), 3)
        evidence = (
            f"{relationship}: {evidence_text[:220]}"
            if evidence_text
            else _evidence_for(narrative, symbol, relationship)
        )
        relations.append(
            {
                "symbol": symbol,
                "relationship": relationship,
                "evidence": evidence,
                "confidence": confidence,
            }
        )
        if len(relations) >= max_relations:
            break
    return relations


def map_beneficiaries(
    narratives: list[MarketNarrative],
    universe: list[UniverseSymbol],
    profile: dict,
    llm: _LLMLike | None = None,
) -> list[ThemeCluster]:
    clusters: list[ThemeCluster] = []
    for narrative in narratives:
        relations: list[ThemeRelation] = []
        if llm is not None:
            relations = _llm_relations(narrative, universe, profile, llm)
        if not relations:
            relations = _keyword_relations(narrative, universe, profile)
        if not relations:
            continue
        clusters.append(_cluster_from(narrative, relations))
    return clusters
