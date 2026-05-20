"""Tests for walk-forward backtester (Phase 2.1)."""

from __future__ import annotations

import json
from pathlib import Path

from dolphi.backtest.chart import render_equity_curve_svg
from dolphi.backtest.mock_prices import MockHistoricalPrices
from dolphi.backtest.report import write_backtest_report
from dolphi.backtest.walk_forward import run_walk_forward_backtest


def test_demo_fixture_produces_positive_periods():
    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        use_demo_fixture=True,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )

    assert result.periods >= 3
    assert len(result.portfolio_equity) == result.periods + 1
    assert len(result.spy_equity) == result.periods + 1
    assert result.portfolio_equity[0] == 100.0
    assert result.spy_equity[0] == 100.0


def test_demo_portfolio_outperforms_spy_in_mock_series():
    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        use_demo_fixture=True,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )

    assert result.total_return_portfolio_pct > result.total_return_spy_pct
    assert result.alpha_pct > 0


def test_empty_decision_log_returns_zero_periods(tmp_path: Path):
    data = MockHistoricalPrices()
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    result = run_walk_forward_backtest(
        data,
        jsonl_path=empty,
        start_date="2024-01-31",
        end_date="2024-06-30",
    )

    assert result.periods == 0
    assert result.notes


def test_user_jsonl_decisions_drive_backtest(tmp_path: Path):
    log = tmp_path / "decisions.jsonl"
    records = [
        {
            "decision_date": "2024-02-29",
            "allocations": [{"symbol": "NVDA", "allocation_pct": 100.0}],
        },
        {
            "decision_date": "2024-05-31",
            "allocations": [{"symbol": "SPY", "allocation_pct": 100.0}],
        },
    ]
    with log.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")

    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        jsonl_path=log,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )

    assert result.periods >= 1
    assert result.source == "decision_log"


def test_cash_allocations_do_not_break_backtest():
    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        use_demo_fixture=True,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )
    assert result.max_drawdown_portfolio_pct >= 0


def test_render_equity_curve_svg_contains_series_labels():
    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        use_demo_fixture=True,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )
    svg = render_equity_curve_svg(result)

    assert "<svg" in svg
    assert "Dolphi allocations" in svg
    assert "SPY buy-and-hold" in svg


def test_write_backtest_report_creates_artefacts(tmp_path: Path):
    data = MockHistoricalPrices()
    result = run_walk_forward_backtest(
        data,
        use_demo_fixture=True,
        start_date="2024-01-31",
        end_date="2024-12-31",
    )
    paths = write_backtest_report(result, tmp_path)

    assert paths["metrics"].exists()
    assert paths["svg"].exists()
    assert paths["summary"].exists()
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert "alpha_pct" in metrics
    assert "equity_curve.svg" in paths["summary"].read_text(encoding="utf-8")
