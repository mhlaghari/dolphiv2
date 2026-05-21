"""Tests for ``dolphi.api`` — the public library facade.

All tests are mock-mode and offline: no network, no API keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dolphi import (
    CheckResult,
    EvaluateResult,
    Falsifier,
    check_falsifiers,
    evaluate,
    get_decision_log,
    list_falsifiers,
)


# ---------- evaluate ----------------------------------------------------------


def test_evaluate_runs_in_mock_mode():
    result = evaluate(symbols=["NVDA"], mock=True, top_k=3)
    assert isinstance(result, EvaluateResult)
    assert result.decision_id  # ISO timestamp string
    assert len(result.ranked_ideas) > 0
    # NVDA should appear somewhere in the ranked discovery output
    ranked_symbols = {idea.symbol for idea in result.ranked_ideas}
    assert "NVDA" in ranked_symbols
    # Mock portfolio_manager allocates to NVDA + BND
    alloc_symbols = {a.symbol for a in result.allocations}
    assert alloc_symbols  # non-empty


def test_evaluate_with_dict_profile():
    profile_dict = {
        "total_savings": 50000,
        "monthly_salary": 5000,
        "currency": "USD",
        "goal": "growth",
        "risk_tolerance": "Aggressive",
        "preferred_asset_classes": ["stocks", "etfs"],
        "investment_percentage": 80.0,
    }
    result = evaluate(symbols=["NVDA"], profile=profile_dict, mock=True, top_k=2)
    assert isinstance(result, EvaluateResult)
    assert result.decision_id
    assert len(result.ranked_ideas) > 0


# ---------- check_falsifiers --------------------------------------------------


def _decision_fixture(timestamp: str = "2026-05-20T10:00:00+00:00") -> dict:
    return {
        "timestamp": timestamp,
        "decision_date": timestamp[:10],
        "profile_risk": "Moderate",
        "profile_goal": "growth",
        "allocations": [
            {"symbol": "NVDA", "allocation_pct": 20.0},
            {"symbol": "CEG", "allocation_pct": 15.0},
        ],
        "pre_mortem_findings": [
            {
                "symbol": "NVDA",
                "overall_fragility": 0.32,
                "falsifiers": [
                    {
                        "failure_mode": "Hyperscaler capex pause",
                        "probability": 0.30,
                        "leading_indicator": "Hyperscaler quarterly guides",
                        "breaks_assumption": "AI capex grows >30% YoY",
                        "horizon": "6 months",
                    },
                    {
                        "failure_mode": "Custom silicon takes share",
                        "probability": 0.25,
                        "leading_indicator": "MTIA volume disclosures",
                        "breaks_assumption": "Pricing power is durable",
                        "horizon": "12 months",
                    },
                ],
            },
            {
                "symbol": "CEG",
                "overall_fragility": 0.23,
                "falsifiers": [
                    {
                        "failure_mode": "Rates compress utility multiples",
                        "probability": 0.30,
                        "leading_indicator": "10y UST weekly",
                        "breaks_assumption": "Forward P/E supports 15% growth",
                        "horizon": "6 months",
                    },
                ],
            },
        ],
    }


def test_check_falsifiers_with_feedback(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    log.write_text(json.dumps(_decision_fixture()) + "\n", encoding="utf-8")

    result = check_falsifiers(
        feedback={"NVDA-0": "triggered"},
        jsonl_path=log,
    )
    assert isinstance(result, CheckResult)
    assert result.position_adjustments["NVDA"] == pytest.approx(-0.30)
    # The triggered falsifier should be surfaced in the result
    assert len(result.triggered_falsifiers) == 1
    assert result.triggered_falsifiers[0]["symbol"] == "NVDA"
    assert result.triggered_falsifiers[0]["index"] == 0
    # No CEG feedback → no CEG adjustment
    assert "CEG" not in result.position_adjustments


def test_check_falsifiers_combines_triggered_and_unsure(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    log.write_text(json.dumps(_decision_fixture()) + "\n", encoding="utf-8")

    result = check_falsifiers(
        feedback={"NVDA-0": "triggered", "NVDA-1": "unsure", "CEG-0": "safe"},
        jsonl_path=log,
    )
    # 1 triggered (-0.30) + 1 unsure (-0.10) = -0.40
    assert result.position_adjustments["NVDA"] == pytest.approx(-0.40)
    assert "CEG" not in result.position_adjustments  # safe ⇒ no adjustment


def test_check_falsifiers_caps_at_negative_ninety(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    # Synthesize a record with many triggered falsifiers on one symbol
    decision = _decision_fixture()
    decision["pre_mortem_findings"][0]["falsifiers"] = [
        {"failure_mode": f"mode {i}", "probability": 0.1, "leading_indicator": "",
         "breaks_assumption": "", "horizon": ""}
        for i in range(5)
    ]
    log.write_text(json.dumps(decision) + "\n", encoding="utf-8")
    feedback = {f"NVDA-{i}": "triggered" for i in range(5)}  # 5 * 0.30 = 1.50

    result = check_falsifiers(feedback=feedback, jsonl_path=log)
    assert result.position_adjustments["NVDA"] == pytest.approx(-0.90)


# ---------- list_falsifiers ---------------------------------------------------


def test_list_falsifiers_keyed_by_symbol(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    log.write_text(json.dumps(_decision_fixture()) + "\n", encoding="utf-8")

    out = list_falsifiers(jsonl_path=log)
    assert isinstance(out, dict)
    assert set(out.keys()) == {"NVDA", "CEG"}
    assert len(out["NVDA"]) == 2
    assert len(out["CEG"]) == 1
    assert all(isinstance(f, Falsifier) for f in out["NVDA"])
    assert out["NVDA"][0].failure_mode == "Hyperscaler capex pause"


# ---------- get_decision_log --------------------------------------------------


def test_get_decision_log_returns_records(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    records = [
        _decision_fixture(timestamp=f"2026-05-{20 + i:02d}T10:00:00+00:00")
        for i in range(3)
    ]
    with log.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    out = get_decision_log(jsonl_path=log, limit=2)
    assert len(out) == 2
    # Should return the last 2 (newest)
    assert out[0]["timestamp"] == records[1]["timestamp"]
    assert out[1]["timestamp"] == records[2]["timestamp"]


def test_get_decision_log_missing_file_returns_empty(tmp_path: Path):
    out = get_decision_log(jsonl_path=tmp_path / "nope.jsonl", limit=5)
    assert out == []
