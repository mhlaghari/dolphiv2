from __future__ import annotations

import logging
import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self, persist_path: Path):
        self._path = persist_path
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="portfolio_memories",
            metadata={"hnsw:space": "cosine"},
        )

    def recall(self, query: dict[str, Any], n: int = 3) -> list[dict[str, Any]]:
        count = self._collection.count()
        if count == 0:
            return []
        text = (
            f"risk={query.get('risk_tolerance', '')} "
            f"goal={query.get('goal', '')} "
            f"assets={','.join(query.get('preferred_asset_classes', []))}"
        )
        results = self._collection.query(
            query_texts=[text],
            n_results=min(n, count),
        )
        hits = []
        if results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                hits.append({"text": doc, "metadata": meta, "similarity": 1.0 - float(dist)})
        return hits

    def remember(
        self,
        profile: dict[str, Any],
        market_summary: dict[str, Any],
        recommendation: dict[str, Any],
        snippets: list[str],
    ) -> str:
        today = date.today().isoformat()
        doc_text = (
            f"Profile: risk={profile.get('risk_tolerance')}, goal={profile.get('goal')}, "
            f"assets={','.join(profile.get('preferred_asset_classes', []))}. "
            f"Date: {today}. "
            f"Market: SPX={market_summary.get('spx_level')}, VIX={market_summary.get('vix_level')}. "
            f"Rec: {recommendation.get('notes', '')}. "
            f"Snippets: {'; '.join(snippets[:3])}"
        )
        doc_hash = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()[:12]
        doc_id = f"run_{today}_{doc_hash}"
        metadata = {
            "risk": str(profile.get("risk_tolerance", "")),
            "goal": str(profile.get("goal", "")),
            "date": today,
            "spx": str(market_summary.get("spx_level", "")),
        }
        self._collection.add(documents=[doc_text], ids=[doc_id], metadatas=[metadata])
        logger.debug("Stored memory record %s", doc_id)
        return doc_id
