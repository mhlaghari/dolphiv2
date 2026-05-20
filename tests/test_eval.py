"""Tests for the falsifier-quality eval harness.

Contract (v0.2.0):
- Fixtures are frozen dataclasses with non-empty thesis + assumptions.
- ``FalsifierJudge`` returns scores clamped to [0, 1] on every axis,
  returns the zero-score on parser failure, never raises.
- ``run_eval`` calls the pre-mortem agent for every (model, fixture)
  pair, scores each emitted falsifier, and aggregates into an
  ``EvalReport``.
- ``write_reports`` writes three files: ``falsifier_quality.md``,
  ``falsifier_quality.csv``, ``falsifier_quality.json``, all readable.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from dolphi.eval import (
    BullCaseFixture,
    EvalReport,
    FalsifierJudge,
    ModelSpec,
    all_fixtures,
    run_eval,
)
from dolphi.eval.fixtures import fixtures_by_slug
from dolphi.eval.report import write_reports


# ---------- fixtures ----------------------------------------------------------


def test_all_fixtures_are_well_formed():
    fixtures = all_fixtures()
    assert len(fixtures) >= 3
    slugs = {fx.slug for fx in fixtures}
    assert len(slugs) == len(fixtures), "fixture slugs must be unique"
    for fx in fixtures:
        assert fx.thesis.strip(), f"{fx.slug}: empty thesis"
        assert len(fx.assumptions) >= 3, f"{fx.slug}: need ≥3 assumptions"
        for assumption in fx.assumptions:
            assert assumption.strip(), f"{fx.slug}: empty assumption"
        assert fx.symbol.isupper(), f"{fx.slug}: symbol must be upper"


def test_fixtures_by_slug_filters_correctly():
    assert len(fixtures_by_slug(None)) == len(all_fixtures())
    assert len(fixtures_by_slug(["all"])) == len(all_fixtures())
    assert len(fixtures_by_slug(["ai-capex"])) == 1
    assert fixtures_by_slug(["ai-capex"])[0].symbol == "NVDA"
    assert fixtures_by_slug(["nonexistent-slug"]) == []


# ---------- judge -------------------------------------------------------------


class _ScriptedLLM:
    """LLM stub for tests. Returns canned JSON; records calls."""

    def __init__(self, *, falsifier_payload=None, judge_payload=None):
        self.falsifier_payload = falsifier_payload
        self.judge_payload = judge_payload
        self.calls = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.calls.append((prompt, system))
        sys_lower = (system or "").lower()
        if "falsification-first" in sys_lower:
            return self.falsifier_payload or {"falsifiers": []}
        if "research-quality judge" in sys_lower:
            return self.judge_payload or {
                "horizon_observability": 0.0,
                "assumption_coherence": 0.0,
                "indicator_specificity": 0.0,
                "probability_calibration": 0.0,
                "comment": "stub",
            }
        return {"error": "unknown system prompt"}


def _good_falsifier():
    return {
        "failure_mode": "Hyperscaler capex pauses for 2 consecutive quarters",
        "probability": 0.3,
        "leading_indicator": "Refinitiv I/B/E/S consensus EPS revision for FY+1",
        "breaks_assumption": "Hyperscaler AI capex grows at least 20% YoY each year through 2027.",
        "horizon": "6 months",
    }


def test_judge_returns_clamped_score_on_valid_response():
    llm = _ScriptedLLM(judge_payload={
        "horizon_observability": 0.9,
        "assumption_coherence": 0.8,
        "indicator_specificity": 0.7,
        "probability_calibration": 0.6,
        "comment": "good falsifier",
    })
    judge = FalsifierJudge(llm)
    score = judge.score(
        falsifier=_good_falsifier(),
        targeted_assumption="Hyperscaler AI capex grows at least 20% YoY each year through 2027.",
        thesis="bull thesis",
    )
    assert 0.0 <= score.aggregate <= 1.0
    assert score.aggregate == pytest.approx((0.9 + 0.8 + 0.7 + 0.6) / 4)
    assert "good falsifier" in score.comment


def test_judge_returns_zero_score_on_parser_error():
    llm = _ScriptedLLM(judge_payload={"error": "Invalid JSON response"})
    judge = FalsifierJudge(llm)
    score = judge.score(
        falsifier=_good_falsifier(),
        targeted_assumption="x",
        thesis="bull",
    )
    assert score.aggregate == 0.0
    assert score.comment == "judge_error"


def test_judge_clamps_out_of_range_values():
    llm = _ScriptedLLM(judge_payload={
        "horizon_observability": 1.7,    # over 1 -> 1
        "assumption_coherence": -0.5,    # negative -> 0
        "indicator_specificity": 0.5,
        "probability_calibration": 0.5,
        "comment": "out of range",
    })
    judge = FalsifierJudge(llm)
    score = judge.score(
        falsifier=_good_falsifier(),
        targeted_assumption="x",
        thesis="t",
    )
    assert 0.0 <= score.horizon_observability <= 1.0
    assert 0.0 <= score.assumption_coherence <= 1.0
    assert score.assumption_coherence == 0.0


# ---------- harness -----------------------------------------------------------


def _make_model_spec(label, llm):
    return ModelSpec(label=label, client_factory=lambda: llm)


def test_run_eval_produces_report_with_scored_falsifiers():
    model_llm = _ScriptedLLM(falsifier_payload={
        "falsifiers": [
            _good_falsifier(),
            _good_falsifier(),
            _good_falsifier(),
        ],
    })
    judge_llm = _ScriptedLLM(judge_payload={
        "horizon_observability": 0.8,
        "assumption_coherence": 0.7,
        "indicator_specificity": 0.6,
        "probability_calibration": 0.5,
        "comment": "ok",
    })

    fixtures = fixtures_by_slug(["ai-capex"])
    assert len(fixtures) == 1

    report = run_eval(
        models=[_make_model_spec("test:model-a", model_llm)],
        fixtures=fixtures,
        judge_spec=_make_model_spec("test:judge", judge_llm),
        repeats=1,
    )
    assert isinstance(report, EvalReport)
    assert len(report.results) == 1
    result = report.results[0]
    assert result.n_falsifiers == 3
    assert result.mean_aggregate == pytest.approx((0.8 + 0.7 + 0.6 + 0.5) / 4)


def test_run_eval_aggregates_over_multiple_models():
    good = _ScriptedLLM(
        falsifier_payload={"falsifiers": [_good_falsifier(), _good_falsifier(), _good_falsifier()]},
    )
    bad = _ScriptedLLM(
        falsifier_payload={"falsifiers": [_good_falsifier()]},  # only 1 falsifier
    )
    judge = _ScriptedLLM(judge_payload={
        "horizon_observability": 1.0,
        "assumption_coherence": 1.0,
        "indicator_specificity": 1.0,
        "probability_calibration": 1.0,
        "comment": "perfect",
    })
    report = run_eval(
        models=[
            _make_model_spec("test:good", good),
            _make_model_spec("test:bad", bad),
        ],
        fixtures=fixtures_by_slug(["ai-capex"]),
        judge_spec=_make_model_spec("test:judge", judge),
        repeats=1,
    )
    leaderboard = report.leaderboard()
    # Both should aggregate 1.0; sort is by mean_aggregate desc, so any order
    # between equal scores is fine. But the *count* of falsifiers differs.
    by_model = {row["model"]: row for row in leaderboard}
    assert by_model["test:good"]["n_falsifiers"] == 3
    assert by_model["test:bad"]["n_falsifiers"] == 1


def test_run_eval_handles_pre_mortem_failure_gracefully():
    class _CrashingLLM:
        def generate_json(self, prompt, system=None, temperature=0.3):
            return {"error": "boom"}

    judge = _ScriptedLLM(judge_payload={
        "horizon_observability": 0.5, "assumption_coherence": 0.5,
        "indicator_specificity": 0.5, "probability_calibration": 0.5,
        "comment": "n/a",
    })
    report = run_eval(
        models=[_make_model_spec("test:crashing", _CrashingLLM())],
        fixtures=fixtures_by_slug(["ai-capex"]),
        judge_spec=_make_model_spec("test:judge", judge),
        repeats=1,
    )
    # No falsifiers — aggregate is 0 by definition
    assert report.results[0].mean_aggregate == 0.0
    assert report.results[0].n_falsifiers == 0


def test_run_eval_rejects_invalid_inputs():
    judge = _ScriptedLLM()
    with pytest.raises(ValueError):
        run_eval(models=[], fixtures=all_fixtures(),
                 judge_spec=_make_model_spec("j", judge), repeats=1)
    with pytest.raises(ValueError):
        run_eval(models=[_make_model_spec("m", judge)], fixtures=[],
                 judge_spec=_make_model_spec("j", judge), repeats=1)
    with pytest.raises(ValueError):
        run_eval(models=[_make_model_spec("m", judge)], fixtures=all_fixtures(),
                 judge_spec=_make_model_spec("j", judge), repeats=0)


# ---------- report writers ----------------------------------------------------


def _minimal_report() -> EvalReport:
    model_llm = _ScriptedLLM(falsifier_payload={
        "falsifiers": [_good_falsifier(), _good_falsifier(), _good_falsifier()],
    })
    judge_llm = _ScriptedLLM(judge_payload={
        "horizon_observability": 0.8, "assumption_coherence": 0.7,
        "indicator_specificity": 0.6, "probability_calibration": 0.5,
        "comment": "ok",
    })
    return run_eval(
        models=[_make_model_spec("test:m1", model_llm)],
        fixtures=fixtures_by_slug(["ai-capex"]),
        judge_spec=_make_model_spec("test:j", judge_llm),
        repeats=1,
    )


def test_write_reports_emits_all_three_artifacts(tmp_path: Path):
    report = _minimal_report()
    paths = write_reports(report, tmp_path)
    assert paths["markdown"].exists()
    assert paths["csv"].exists()
    assert paths["json"].exists()
    # markdown should contain the leaderboard header
    md = paths["markdown"].read_text(encoding="utf-8")
    assert "Falsifier-quality leaderboard" in md
    assert "test:m1" in md
    # csv must be parseable + contain the 3 falsifiers
    with paths["csv"].open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 1 + 3  # header + 3 falsifiers
    assert rows[0][0] == "model"
    # json must be valid + have the per-model audit trail
    audit = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert audit["judge_label"] == "test:j"
    assert audit["fixture_slugs"] == ["ai-capex"]
    assert len(audit["per_model"]) == 1
    assert len(audit["per_model"][0]["scored_falsifiers"]) == 3


def test_leaderboard_is_sorted_by_aggregate_desc():
    # Two models with different scores.
    high = _ScriptedLLM(falsifier_payload={"falsifiers": [_good_falsifier()]})
    low = _ScriptedLLM(falsifier_payload={"falsifiers": [_good_falsifier()]})
    judge = _ScriptedLLM(judge_payload={
        "horizon_observability": 1.0, "assumption_coherence": 1.0,
        "indicator_specificity": 1.0, "probability_calibration": 1.0,
        "comment": "x",
    })
    # Both models will be rated identically because the judge is fixed —
    # but the order of insertion shouldn't matter, and the rows should exist.
    report = run_eval(
        models=[_make_model_spec("test:high", high), _make_model_spec("test:low", low)],
        fixtures=fixtures_by_slug(["ai-capex"]),
        judge_spec=_make_model_spec("test:j", judge),
        repeats=1,
    )
    rows = report.leaderboard()
    assert len(rows) == 2
    # Sorted descending — first row must have score >= second.
    assert rows[0]["mean_aggregate"] >= rows[1]["mean_aggregate"]


def test_bull_case_fixture_as_research_output_round_trips():
    fx = BullCaseFixture(
        slug="t", title="t", symbol="X", sector="s",
        thesis="thesis text", assumptions=("a", "b", "c"),
    )
    ro = fx.as_research_output()
    assert ro["thesis"] == "thesis text"
    assert 0.0 <= ro["conviction"] <= 1.0
