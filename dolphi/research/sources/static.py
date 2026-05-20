from __future__ import annotations

from dataclasses import replace

from .base import ResearchDocument


_DEFAULT_DOCUMENTS = [
    ResearchDocument(
        title="AI data centers drive demand for power and grid equipment",
        snippet="Utilities, independent power producers, and electrical infrastructure suppliers are cited as beneficiaries of data center load growth.",
        source="static",
        url="static://ai-power-demand",
        published_at="2026-05-01",
        query="AI infrastructure",
    ),
    ResearchDocument(
        title="Advanced chip supply chain expands for AI accelerators",
        snippet="Foundries, memory makers, semiconductor equipment vendors, and broad chip ETFs are exposed to AI accelerator demand.",
        source="static",
        url="static://ai-semiconductor-chain",
        published_at="2026-05-01",
        query="AI infrastructure",
    ),
    ResearchDocument(
        title="Defensive sectors attract capital during earnings uncertainty",
        snippet="Healthcare, staples, bonds, and utilities can attract flows when growth expectations become volatile.",
        source="static",
        url="static://defensive-rotation",
        published_at="2026-04-20",
        query="market rotation",
    ),
]


class StaticResearchSource:
    name = "static"

    def __init__(self, documents: list[ResearchDocument] | None = None):
        self._documents = documents or list(_DEFAULT_DOCUMENTS)

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        query_terms = {term for term in query.lower().replace(",", " ").split() if len(term) > 2}
        scored: list[tuple[int, ResearchDocument]] = []
        for document in self._documents:
            text = f"{document.query} {document.title} {document.snippet}".lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0 or not query_terms:
                scored.append((score, document))
        scored.sort(key=lambda item: (-item[0], item[1].title))
        return [replace(document, source=self.name) for _, document in scored[:limit]]
