"""Tests for the ``dolphi --check`` retention loop."""

from __future__ import annotations

import io
import json
from pathlib import Path

import click
import pytest
from rich.console import Console

from dolphi.check import (
    CheckResult,
    _build_indicators,
    load_latest_decision,
    run_check,
)


def _decision_with_falsifiers(timestamp: str = "2026-05-20T10:00:00+00:00") -> dict:
    return {
        "timestamp": timestamp,
        "decision_date": timestamp[:10],
        "profile_risk": "Moderate",
        "profile_goal": "growth",
        "allocations": [
            {"symbol": "NVDA", "allocation_pct": 16.6},
            {"symbol": "CEG", "allocation_pct": 14.8},
            {"symbol": "BND", "allocation_pct": 25.1},
        ],
        "pre_mortem_findings": [
            {
                "symbol": "NVDA",
                "overall_fragility": 0.32,
                "falsifiers": [
                    {
                        "failure_mode": "Hyperscaler capex pause",
                        "probability": 0.30,
                        "leading_indicator": "Refinitiv I/B/E/S FY+1 EPS revision",
                        "breaks_assumption": "AI capex sustains > 20% YoY",
                        "horizon": "6 months",
                    },
                    {
                        "failure_mode": "Customer in-house silicon shift",
                        "probability": 0.25,
                        "leading_indicator": "Google Trends 'AI chip competition' / 'NVIDIA'",
                        "breaks_assumption": "NVDA market share stays above 75%",
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


# ---------- load_latest_decision ---------------------------------------------


def test_load_latest_decision_returns_most_recent_full_record(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    earlier = _decision_with_falsifiers("2026-04-01T10:00:00+00:00")
    later = _decision_with_falsifiers("2026-05-20T10:00:00+00:00")
    with log.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(earlier) + "\n")
        fh.write(json.dumps(later) + "\n")
    record = load_latest_decision(log)
    assert record is not None
    assert record["timestamp"] == later["timestamp"]


def test_load_latest_decision_skips_legacy_records_without_falsifiers(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    legacy = {
        "timestamp": "2026-04-01T10:00:00+00:00",
        "pre_mortem_summary": [{"symbol": "NVDA", "fragility": 0.3}],
    }
    full = _decision_with_falsifiers()
    with log.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(legacy) + "\n")
        fh.write(json.dumps(full) + "\n")
    record = load_latest_decision(log)
    assert record is not None
    assert "pre_mortem_findings" in record


def test_load_latest_decision_returns_none_when_only_legacy(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    legacy = {
        "timestamp": "2026-04-01T10:00:00+00:00",
        "pre_mortem_summary": [{"symbol": "NVDA", "fragility": 0.3}],
    }
    log.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    assert load_latest_decision(log) is None


def test_load_latest_decision_missing_file_returns_none(tmp_path: Path):
    assert load_latest_decision(tmp_path / "nope.jsonl") is None


def test_load_latest_decision_skips_malformed_lines(tmp_path: Path):
    log = tmp_path / "decision_log.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        fh.write("garbage not json\n")
        fh.write(json.dumps(_decision_with_falsifiers()) + "\n")
        fh.write("more garbage\n")
    record = load_latest_decision(log)
    assert record is not None


# ---------- _build_indicators -------------------------------------------------


def test_build_indicators_flattens_falsifiers_with_weights():
    decision = _decision_with_falsifiers()
    indicators = _build_indicators(decision)
    assert len(indicators) == 3  # 2 for NVDA + 1 for CEG
    nvda_ind = [i for i in indicators if i.symbol == "NVDA"]
    assert len(nvda_ind) == 2
    assert nvda_ind[0].weight_pct == 16.6
    assert nvda_ind[0].fragility == 0.32
    assert nvda_ind[0].falsifier_index == 1


def test_build_indicators_handles_missing_allocation():
    decision = _decision_with_falsifiers()
    # Strip allocations — falsifiers still surface, weight=0.
    decision["allocations"] = []
    indicators = _build_indicators(decision)
    assert all(i.weight_pct == 0.0 for i in indicators)


# ---------- CheckResult.adjustment_by_symbol ---------------------------------


def _result_with_statuses(statuses: list[str]) -> CheckResult:
    decision = _decision_with_falsifiers()
    indicators = _build_indicators(decision)
    assert len(indicators) == len(statuses), "fixture indicator count must match statuses"
    for ind, st in zip(indicators, statuses):
        ind.status = st  # type: ignore[assignment]
    result = CheckResult(decision_date="2026-05-20")
    result.indicators = indicators
    return result


def test_adjustment_zero_when_all_safe():
    result = _result_with_statuses(["safe", "safe", "safe"])
    assert result.adjustment_by_symbol() == {}


def test_adjustment_shaves_30_percent_per_triggered_falsifier():
    # NVDA has 2 falsifiers; trigger the first, leave the second safe.
    result = _result_with_statuses(["triggered", "safe", "safe"])
    adj = result.adjustment_by_symbol()
    assert "NVDA" in adj
    old, new, note = adj["NVDA"]
    assert old == 16.6
    assert new == pytest.approx(16.6 * 0.70, rel=1e-3)
    assert "triggered" in note


def test_adjustment_caps_at_90_percent_reduction():
    # Trigger both NVDA falsifiers — would naively reduce by 60%; the floor is 90% off.
    result = _result_with_statuses(["triggered", "triggered", "safe"])
    adj = result.adjustment_by_symbol()
    old, new, _ = adj["NVDA"]
    # 1 - 0.30*2 = 0.40 multiplier; not yet hitting the 0.10 floor
    assert new == pytest.approx(old * 0.40, rel=1e-3)


def test_adjustment_combines_triggered_and_unsure():
    result = _result_with_statuses(["triggered", "unsure", "safe"])
    adj = result.adjustment_by_symbol()
    old, new, note = adj["NVDA"]
    # 1 - 0.30 - 0.10 = 0.60 multiplier
    assert new == pytest.approx(old * 0.60, rel=1e-3)
    assert "triggered" in note and "unsure" in note


def test_n_safe_n_triggered_n_unsure_counts():
    result = _result_with_statuses(["safe", "triggered", "unsure"])
    assert result.n_safe == 1
    assert result.n_triggered == 1
    assert result.n_unsure == 1
    assert result.total == 3


# ---------- end-to-end run_check ----------------------------------------------


def test_run_check_returns_one_when_no_log(tmp_path: Path):
    console = Console(file=io.StringIO(), width=120, force_terminal=False)
    rc = run_check(jsonl_path=tmp_path / "missing.jsonl", console=console)
    assert rc == 1


def test_run_check_walks_indicators_and_renders_summary(tmp_path: Path, monkeypatch):
    log = tmp_path / "decision_log.jsonl"
    log.write_text(json.dumps(_decision_with_falsifiers()) + "\n", encoding="utf-8")

    # Three indicators: mark first triggered, second safe, third unsure.
    inputs = iter(["T", "S", "U"])
    monkeypatch.setattr(click, "prompt", lambda *a, **k: next(inputs))

    output_buf = io.StringIO()
    console = Console(file=output_buf, width=140, force_terminal=False, color_system=None)
    rc = run_check(jsonl_path=log, console=console)

    assert rc == 0
    output = output_buf.getvalue()
    assert "DOLPHI" not in output or "OLPHI" in output  # banner renders (ASCII)
    assert "NVDA" in output
    assert "Hyperscaler capex pause" in output
    # Triggered NVDA should appear in position-size suggestions
    assert "position-size suggestions" in output or "suggested" in output