from __future__ import annotations

from ..models import CandidateIdea, RankedIdea


_WEIGHTS = {
    "narrative_confidence": 0.24,
    "source_diversity": 0.12,
    "source_recency": 0.10,
    "relationship_strength": 0.20,
    "market_trend": 0.14,
    "valuation": 0.10,
    "liquidity": 0.10,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _score(candidate: CandidateIdea) -> float:
    features = candidate.get("features", {})
    raw = 0.0
    for key, weight in _WEIGHTS.items():
        fallback_key = {"market_trend": "momentum", "relationship_strength": "theme_strength"}.get(key)
        value = features.get(key, features.get(fallback_key, 0.0) if fallback_key else 0.0)
        raw += _clamp(float(value)) * weight
    raw -= _clamp(float(features.get("risk_penalty", 0.0))) * 0.1
    if candidate.get("is_adr"):
        raw -= 0.03
    return round(_clamp(raw), 4)


def rank_candidates(candidates: list[CandidateIdea], top_k: int = 5) -> list[RankedIdea]:
    scored = sorted(
        ((candidate, _score(candidate)) for candidate in candidates),
        key=lambda item: (-item[1], item[0]["symbol"]),
    )

    selected: list[tuple[CandidateIdea, float]] = []
    sector_counts: dict[str, int] = {}
    for candidate, score in scored:
        if len(selected) >= max(top_k, 0):
            break
        sector = candidate.get("sector", "")
        if sector_counts.get(sector, 0) >= 1 and any(sector_counts.get(other, 0) == 0 for other in {item[0].get("sector", "") for item in scored}):
            continue
        selected.append((candidate, score))
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    if len(selected) < max(top_k, 0):
        selected_symbols = {candidate["symbol"] for candidate, _ in selected}
        for candidate, score in scored:
            if candidate["symbol"] in selected_symbols:
                continue
            selected.append((candidate, score))
            if len(selected) >= max(top_k, 0):
                break

    ranked: list[RankedIdea] = []
    for rank, (candidate, score) in enumerate(selected, 1):
        confidence = round(_clamp(score * 0.85 + len(candidate.get("evidence", [])) * 0.03), 3)
        evidence = candidate.get("evidence", [])
        thesis = evidence[0] if evidence else f"{candidate['symbol']} passed the discovery screen."
        ranked.append(
            {
                "rank": rank,
                "symbol": candidate["symbol"],
                "name": candidate["name"],
                "asset_type": candidate["asset_type"],
                "is_adr": candidate["is_adr"],
                "sector": candidate["sector"],
                "theme": candidate["theme"],
                "score": score,
                "confidence": confidence,
                "thesis": thesis,
                "evidence": evidence,
                "risks": candidate.get("risks", []),
                "score_breakdown": {
                    key: _clamp(float(candidate.get("features", {}).get(key, 0.0)))
                    for key in [*_WEIGHTS.keys(), "risk_penalty"]
                },
            }
        )
    return ranked
