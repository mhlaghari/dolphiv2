"""Tests for Rich TUI render helpers."""

from __future__ import annotations

from dolphi.tui.live import render_workflow_state, _stage_label


def test_stage_label_detects_pre_mortem():
    state = {"pre_mortem_findings": [{"symbol": "NVDA", "falsifiers": [], "overall_fragility": 0.3}]}
    assert "pre_mortem" in _stage_label(state)


def test_stage_label_detects_portfolio_complete():
    state = {
        "pre_mortem_findings": [],
        "portfolio_recommendation": {"allocations": [{"symbol": "SPY", "allocation_pct": 100}]},
    }
    assert "portfolio_manager" in _stage_label(state)


def test_render_workflow_state_returns_renderable():
    state = {
        "ranked_ideas": [{"rank": 1, "symbol": "NVDA", "theme": "AI", "score": 0.9}],
        "bull_case": [{"thesis": "AI up", "reasoning": "x", "conviction": 0.8}],
        "bear_case": [{"thesis": "valuations", "reasoning": "y", "conviction": 0.4}],
        "pre_mortem_findings": [],
        "portfolio_recommendation": {"allocations": []},
        "reflection_summary": {"summary_text": ""},
    }
    rendered = render_workflow_state(state)
    assert rendered is not None
