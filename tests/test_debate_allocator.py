"""Allocator-level tests for debate conviction deltas."""

from __future__ import annotations

from dolphi.allocation.optimizer import allocate_ranked_ideas


def _idea(symbol: str, sector: str, score: float) -> dict:
    return {
        "rank": 1,
        "symbol": symbol,
        "name": symbol,
        "asset_type": "stock",
        "is_adr": False,
        "sector": sector,
        "theme": "AI infrastructure",
        "score": score,
        "confidence": score,
        "thesis": f"{symbol} thesis",
        "evidence": ["evidence"],
        "risks": [],
        "score_breakdown": {},
    }


def _profile(risk: str = "Moderate") -> dict:
    return {"risk_tolerance": risk, "goal": "growth", "preferred_asset_classes": ["stocks", "etfs"]}


def test_positive_debate_delta_lifts_weight_relative_to_negative_delta():
    ideas = [_idea("NVDA", "Technology", 0.7), _idea("CEG", "Utilities", 0.7)]
    judgments = [
        {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.25, "rationale": "bull won"},
        {"symbol": "CEG", "winner": "bear", "conviction_delta": -0.25, "rationale": "bear won"},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), debate_judgments=judgments)
    weights = {item["symbol"]: item["allocation_pct"] for item in rec["allocations"]}

    assert weights["NVDA"] > weights["CEG"], weights


def test_no_debate_judgments_preserves_legacy_behavior():
    ideas = [_idea("NVDA", "Technology", 0.7), _idea("CEG", "Utilities", 0.7)]

    legacy = allocate_ranked_ideas(ideas, _profile())
    with_empty = allocate_ranked_ideas(ideas, _profile(), debate_judgments=[])

    legacy_map = {item["symbol"]: item["allocation_pct"] for item in legacy["allocations"]}
    empty_map = {item["symbol"]: item["allocation_pct"] for item in with_empty["allocations"]}
    assert legacy_map == empty_map


def test_debate_delta_combines_with_fragility():
    """Positive debate delta should partially offset modest fragility,
    but high fragility should still dominate."""
    ideas = [_idea("NVDA", "Technology", 0.7), _idea("CEG", "Utilities", 0.7)]

    rec = allocate_ranked_ideas(
        ideas,
        _profile(),
        pre_mortem_findings=[
            {"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.9},
            {"symbol": "CEG", "falsifiers": [], "overall_fragility": 0.0},
        ],
        debate_judgments=[
            {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.3, "rationale": "x"},
            {"symbol": "CEG", "winner": "tie", "conviction_delta": 0.0, "rationale": "x"},
        ],
    )
    weights = {item["symbol"]: item["allocation_pct"] for item in rec["allocations"]}
    assert weights["CEG"] > weights["NVDA"], weights


def test_debate_rationale_annotates_winner_when_meaningful():
    ideas = [_idea("NVDA", "Technology", 0.7)]
    judgments = [
        {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.2, "rationale": "bull won decisively"},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), debate_judgments=judgments)
    rationale = next(item["rationale"] for item in rec["allocations"] if item["symbol"] == "NVDA")
    assert "Debate" in rationale
    assert "bull" in rationale.lower()


def test_debate_aware_allocator_still_sums_to_100():
    ideas = [
        _idea("NVDA", "Technology", 0.85),
        _idea("TSM", "Technology", 0.7),
        _idea("CEG", "Utilities", 0.6),
    ]
    judgments = [
        {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.2, "rationale": "x"},
        {"symbol": "TSM", "winner": "tie", "conviction_delta": 0.0, "rationale": "x"},
        {"symbol": "CEG", "winner": "bear", "conviction_delta": -0.15, "rationale": "x"},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), debate_judgments=judgments)
    total = round(sum(item["allocation_pct"] for item in rec["allocations"]), 1)
    assert total == 100.0
