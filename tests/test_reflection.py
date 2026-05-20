"""Tests for the closed-loop reflection module (Phase 1.4)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dolphi.memory.decision_log import append_decision_log
from dolphi.memory.reflection import (
    compute_reflection,
    load_past_decisions,
)


class _MockData:
    """Deterministic price fetcher keyed by symbol and date."""

    def __init__(self, prices: dict[str, dict[str, float]] | None = None):
        # prices[symbol][date or "latest"] = price
        self.prices = prices or {}
        self.calls: list[tuple[str, str | None]] = []

    def get_stock_price(self, symbol: str, date: str | None = None) -> float:
        self.calls.append((symbol, date))
        bucket = self.prices.get(symbol, {})
        key = date or "latest"
        if key not in bucket:
            raise ValueError(f"No price for {symbol} @ {key}")
        return float(bucket[key])


def _write_decision(path: Path, decision_date: str, allocations: list[dict]) -> None:
    record = {
        "timestamp": f"{decision_date}T12:00:00+00:00",
        "decision_date": decision_date,
        "profile_risk": "Moderate",
        "profile_goal": "growth",
        "allocations": allocations,
        "ranked_ideas": [],
        "debate_judgments": [],
        "pre_mortem_summary": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")


def test_load_past_decisions_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_past_decisions(tmp_path / "nope.jsonl") == []


def test_decision_log_writes_sidecar_jsonl(tmp_path: Path) -> None:
    md_path = tmp_path / "log.md"
    append_decision_log(
        md_path,
        profile={"risk_tolerance": "Moderate", "goal": "growth"},
        ranked_ideas=[{"symbol": "NVDA", "score": 0.9, "theme": "AI"}],
        theme_clusters=[],
        recommendation={
            "allocations": [
                {"symbol": "NVDA", "allocation_pct": 30.0, "rationale": "AI leader"},
                {"symbol": "BND", "allocation_pct": 70.0, "rationale": "ballast"},
            ],
            "notes": "test",
        },
        debate_judgments=[{"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.15, "rationale": "x"}],
        pre_mortem_findings=[{"symbol": "NVDA", "overall_fragility": 0.4}],
    )

    sidecar = md_path.with_suffix(".jsonl")
    assert sidecar.exists()
    records = load_past_decisions(sidecar)
    assert len(records) == 1
    assert records[0]["allocations"][0]["symbol"] == "NVDA"
    assert records[0]["debate_judgments"][0]["winner"] == "bull"


def test_compute_reflection_returns_empty_when_no_decisions(tmp_path: Path) -> None:
    data = _MockData()
    result = compute_reflection(tmp_path / "nope.jsonl", data)
    assert result["entries_count"] == 0
    assert result["summary_text"] == ""


def test_compute_reflection_skips_decisions_younger_than_min_age(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(log, recent, [{"symbol": "NVDA", "allocation_pct": 50.0}])

    data = _MockData()
    result = compute_reflection(log, data, min_age_days=14, now=now)
    assert result["entries_count"] == 0
    assert data.calls == []


def test_compute_reflection_skips_decisions_older_than_max_age(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = (now - timedelta(days=600)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(log, old, [{"symbol": "NVDA", "allocation_pct": 50.0}])

    data = _MockData()
    result = compute_reflection(log, data, max_age_days=540, now=now)
    assert result["entries_count"] == 0


def test_compute_reflection_calculates_alpha_against_spy(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = (now - timedelta(days=60)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(log, decision, [{"symbol": "NVDA", "allocation_pct": 100.0}])

    data = _MockData(
        {
            "NVDA": {decision: 100.0, "latest": 130.0},
            "SPY": {decision: 500.0, "latest": 550.0},
        }
    )

    result = compute_reflection(log, data, now=now)
    assert result["entries_count"] == 1
    entry = result["entries"][0]
    # NVDA returned +30%, SPY +10% → alpha = +20%
    assert entry["per_symbol"][0]["symbol_return_pct"] == 30.0
    assert entry["spy_return_pct"] == 10.0
    assert entry["per_symbol"][0]["alpha_pct"] == 20.0
    assert entry["portfolio_return_pct"] == 30.0
    assert entry["portfolio_alpha_pct"] == 20.0


def test_compute_reflection_drops_symbols_with_missing_prices(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(
        log,
        decision,
        [
            {"symbol": "NVDA", "allocation_pct": 60.0},
            {"symbol": "FAKE", "allocation_pct": 40.0},
        ],
    )

    data = _MockData(
        {
            "NVDA": {decision: 100.0, "latest": 110.0},
            "SPY": {decision: 500.0, "latest": 510.0},
        }
    )

    result = compute_reflection(log, data, now=now)
    symbols = [item["symbol"] for item in result["entries"][0]["per_symbol"]]
    assert symbols == ["NVDA"]


def test_compute_reflection_skips_cash_allocations(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(
        log,
        decision,
        [
            {"symbol": "NVDA", "allocation_pct": 60.0},
            {"symbol": "CASH", "allocation_pct": 40.0},
        ],
    )

    data = _MockData(
        {
            "NVDA": {decision: 100.0, "latest": 110.0},
            "SPY": {decision: 500.0, "latest": 510.0},
        }
    )

    result = compute_reflection(log, data, now=now)
    symbols = [item["symbol"] for item in result["entries"][0]["per_symbol"]]
    assert symbols == ["NVDA"]


def test_compute_reflection_returns_empty_when_spy_price_missing(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(log, decision, [{"symbol": "NVDA", "allocation_pct": 100.0}])

    data = _MockData(
        {
            "NVDA": {decision: 100.0, "latest": 130.0},
            # No SPY prices
        }
    )

    result = compute_reflection(log, data, now=now)
    assert result["entries_count"] == 0


def test_compute_reflection_caps_to_max_decisions(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    log = tmp_path / "log.jsonl"
    for days_back in [30, 60, 90, 120, 150, 180, 210]:
        date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        _write_decision(log, date, [{"symbol": "NVDA", "allocation_pct": 100.0}])

    prices = {"NVDA": {"latest": 110.0}, "SPY": {"latest": 510.0}}
    for days_back in [30, 60, 90, 120, 150, 180, 210]:
        date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        prices["NVDA"][date] = 100.0
        prices["SPY"][date] = 500.0
    data = _MockData(prices)

    result = compute_reflection(log, data, max_decisions=3, now=now)
    assert result["entries_count"] == 3


def test_compute_reflection_summary_text_includes_portfolio_alpha(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    log = tmp_path / "log.jsonl"
    _write_decision(log, decision, [{"symbol": "NVDA", "allocation_pct": 100.0}])

    data = _MockData(
        {
            "NVDA": {decision: 100.0, "latest": 130.0},
            "SPY": {decision: 500.0, "latest": 550.0},
        }
    )

    result = compute_reflection(log, data, now=now)
    assert "alpha" in result["summary_text"].lower()
    assert "+20.00%" in result["summary_text"]


def test_compute_reflection_skips_unparseable_dates(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    record = {
        "timestamp": "garbage",
        "decision_date": "not-a-date",
        "allocations": [{"symbol": "NVDA", "allocation_pct": 100}],
    }
    with log.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")

    data = _MockData()
    result = compute_reflection(log, data)
    assert result["entries_count"] == 0


def test_load_past_decisions_skips_corrupt_lines(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    with log.open("w", encoding="utf-8") as handle:
        handle.write('{"valid": 1}\n')
        handle.write("not json\n")
        handle.write('{"valid": 2}\n')

    records = load_past_decisions(log)
    assert [r["valid"] for r in records] == [1, 2]
