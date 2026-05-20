from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from ..models import MarketNarrative
from .sources.base import ResearchDocument


_GROUP_KEYWORDS = {
    "AI Infrastructure And Power": {
        "ai", "accelerator", "accelerators", "chip", "chips", "semiconductor", "semiconductors",
        "foundry", "foundries", "memory", "data", "center", "centers", "power", "grid", "electricity",
    },
    "Defensive Rotation": {"defensive", "healthcare", "staples", "bonds", "utilities", "rotation", "uncertainty"},
    "Financial Conditions": {"bank", "banks", "credit", "loan", "loans", "payment", "payments", "financial", "financials"},
    "Consumer Demand": {"consumer", "retail", "spending", "sales", "ecommerce", "online", "discount", "stores"},
    "Platform Technology": {"cloud", "software", "platform", "advertising", "internet", "search", "mobile"},
}

_SECTOR_KEYWORDS = {
    "Technology": {"ai", "accelerator", "semiconductor", "chip", "foundry", "memory", "software"},
    "Utilities": {"power", "grid", "electricity", "utility", "utilities", "data center"},
    "Industrials": {"infrastructure", "electrical", "equipment", "grid"},
    "Healthcare": {"healthcare", "pharma", "medical"},
    "Fixed Income": {"bond", "bonds", "rates"},
    "Financial Services": {"bank", "banks", "credit", "payment", "payments", "loan", "loans"},
    "Consumer": {"consumer", "retail", "spending", "sales", "discount", "ecommerce"},
    "Communication Services": {"advertising", "internet", "search", "platform"},
}


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _freshness(documents: list[ResearchDocument]) -> float:
    dates = [_parse_date(document.published_at) for document in documents]
    valid_dates = [value for value in dates if value is not None]
    if not valid_dates:
        return 0.5
    newest = max(valid_dates)
    age_days = max((date.today() - newest).days, 0)
    if age_days <= 14:
        return 1.0
    if age_days <= 60:
        return 0.75
    if age_days <= 180:
        return 0.45
    return 0.2


def _group_for(document: ResearchDocument) -> str:
    text = document.text.lower()
    best_group = "General Market Narrative"
    best_score = 0
    for group, keywords in _GROUP_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_group = group
            best_score = score
    return best_group


def _keywords(documents: list[ResearchDocument]) -> list[str]:
    tokens: dict[str, int] = defaultdict(int)
    for document in documents:
        for raw in document.text.lower().replace(",", " ").replace(".", " ").split():
            token = raw.strip(":-()[]")
            if len(token) < 4:
                continue
            tokens[token] += 1
    return [token for token, _ in sorted(tokens.items(), key=lambda item: (-item[1], item[0]))[:12]]


def _related_sectors(keywords: list[str]) -> list[str]:
    keyword_set = set(keywords)
    sectors = []
    for sector, sector_keywords in _SECTOR_KEYWORDS.items():
        if keyword_set.intersection(sector_keywords):
            sectors.append(sector)
    return sectors or ["Broad Market"]


def discover_narratives(documents: list[ResearchDocument]) -> list[MarketNarrative]:
    grouped: dict[str, list[ResearchDocument]] = defaultdict(list)
    for document in documents:
        grouped[_group_for(document)].append(document)

    narratives: list[MarketNarrative] = []
    for title, group_docs in grouped.items():
        keywords = _keywords(group_docs)
        sources = {document.source for document in group_docs}
        freshness = _freshness(group_docs)
        source_diversity = min(len(sources) / 3.0, 1.0)
        source_count = len(group_docs)
        confidence = min(0.35 + source_count * 0.15 + source_diversity * 0.2 + freshness * 0.2, 1.0)
        evidence = [f"{document.title}: {document.snippet}" for document in group_docs[:4]]
        thesis = " ".join(document.snippet for document in group_docs[:2]).strip()
        narratives.append(
            MarketNarrative(
                title=title,
                thesis=thesis,
                evidence=evidence,
                source_count=source_count,
                source_diversity=round(source_diversity, 3),
                freshness=round(freshness, 3),
                confidence=round(confidence, 3),
                related_sectors=_related_sectors(keywords),
                keywords=keywords,
                source_urls=[document.url for document in group_docs if document.url],
            )
        )

    return sorted(narratives, key=lambda narrative: (-narrative.confidence, narrative.title))
