from __future__ import annotations

from dolphi.allocation.optimizer import allocate_ranked_ideas


def _idea(symbol: str, sector: str, score: float, theme: str = "AI infrastructure") -> dict:
    return {
        "rank": 1,
        "symbol": symbol,
        "name": symbol,
        "asset_type": "stock",
        "is_adr": False,
        "sector": sector,
        "theme": theme,
        "score": score,
        "confidence": score,
        "thesis": f"{symbol} thesis",
        "evidence": ["evidence"],
        "risks": [],
        "score_breakdown": {},
    }


def _profile(risk="Moderate"):
    return {"risk_tolerance": risk, "goal": "growth", "preferred_asset_classes": ["stocks", "etfs"]}


def test_high_fragility_reduces_weight_relative_to_low_fragility():
    ideas = [
        _idea("NVDA", "Technology", 0.85),
        _idea("CEG", "Utilities", 0.85),
    ]
    findings = [
        {"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.9},
        {"symbol": "CEG", "falsifiers": [], "overall_fragility": 0.0},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), pre_mortem_findings=findings)

    weights = {item["symbol"]: item["allocation_pct"] for item in rec["allocations"]}
    assert weights["CEG"] > weights["NVDA"], weights
    # Per-position caps prevent perfect proportionality, but the fragile
    # idea should be meaningfully smaller than the resilient one.
    assert weights["CEG"] >= 1.5 * weights["NVDA"], weights


def test_no_pre_mortem_findings_preserves_legacy_behavior():
    ideas = [
        _idea("NVDA", "Technology", 0.85),
        _idea("CEG", "Utilities", 0.85),
    ]

    without_findings = allocate_ranked_ideas(ideas, _profile())
    with_neutral_findings = allocate_ranked_ideas(
        ideas,
        _profile(),
        pre_mortem_findings=[
            {"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.0},
            {"symbol": "CEG", "falsifiers": [], "overall_fragility": 0.0},
        ],
    )

    legacy = {item["symbol"]: item["allocation_pct"] for item in without_findings["allocations"]}
    neutral = {item["symbol"]: item["allocation_pct"] for item in with_neutral_findings["allocations"]}
    assert legacy == neutral


def test_fragility_annotations_appear_in_rationale_when_significant():
    ideas = [_idea("NVDA", "Technology", 0.85)]
    findings = [
        {"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.8},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), pre_mortem_findings=findings)

    rationales = {item["symbol"]: item["rationale"] for item in rec["allocations"]}
    assert "fragility" in rationales["NVDA"].lower()


def test_pre_mortem_aware_allocator_still_sums_to_100():
    ideas = [
        _idea("NVDA", "Technology", 0.85),
        _idea("TSM", "Technology", 0.7),
        _idea("CEG", "Utilities", 0.6),
    ]
    findings = [
        {"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.5},
        {"symbol": "TSM", "falsifiers": [], "overall_fragility": 0.3},
        {"symbol": "CEG", "falsifiers": [], "overall_fragility": 0.1},
    ]

    rec = allocate_ranked_ideas(ideas, _profile(), pre_mortem_findings=findings)
    total = round(sum(item["allocation_pct"] for item in rec["allocations"]), 1)

    assert total == 100.0
