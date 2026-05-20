from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ResearchDocument:
    title: str
    snippet: str
    source: str
    url: str
    published_at: str
    query: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.snippet}".strip()

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.lower().encode("utf-8")).hexdigest()


class ResearchSource(Protocol):
    name: str

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        ...


def dedupe_documents(documents: list[ResearchDocument]) -> list[ResearchDocument]:
    seen: set[str] = set()
    unique: list[ResearchDocument] = []
    for document in documents:
        key = document.url or document.content_hash
        if key in seen:
            continue
        seen.add(key)
        unique.append(document)
    return unique
