"""Eval harness — runs the pre-mortem agent under each model and scores it.

Reuses ``dolphi.agents.pre_mortem._per_symbol_pre_mortem`` for the actual
falsifier generation so the eval is grading exactly the code that ships
to users — not a re-implementation.

Cost / latency tracking is wall-clock only in v0.2.0; per-token cost is
deferred until the OpenAI-compatible client exposes usage counters.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..agents.pre_mortem import _per_symbol_pre_mortem
from ..llm.json_mixin import JsonGeneratingClient
from ..models import BullAssumption, RankedIdea
from .fixtures import BullCaseFixture
from .judge import FalsifierJudge, FalsifierScore, ScoredFalsifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Identifier for one model under test.

    ``label`` is what shows up in the leaderboard (e.g. "anthropic:sonnet-4-6").
    ``client_factory`` is a zero-arg callable that returns a fresh
    ``JsonGeneratingClient`` — this lets the harness instantiate clients
    lazily and re-use them across fixtures.
    """

    label: str
    client_factory: Callable[[], JsonGeneratingClient]


@dataclass
class ModelResult:
    model: str
    scored_falsifiers: list[ScoredFalsifier] = field(default_factory=list)
    fixtures_run: list[str] = field(default_factory=list)
    total_latency_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def n_falsifiers(self) -> int:
        return len(self.scored_falsifiers)

    @property
    def mean_aggregate(self) -> float:
        if not self.scored_falsifiers:
            return 0.0
        return sum(f.score.aggregate for f in self.scored_falsifiers) / len(self.scored_falsifiers)

    def mean_axis(self, axis: str) -> float:
        if not self.scored_falsifiers:
            return 0.0
        values = [getattr(f.score, axis) for f in self.scored_falsifiers]
        return sum(values) / len(values)


@dataclass
class EvalReport:
    results: list[ModelResult]
    judge_label: str
    fixture_slugs: list[str]
    repeats: int

    def leaderboard(self) -> list[dict[str, Any]]:
        rows = []
        for r in self.results:
            rows.append({
                "model": r.model,
                "mean_aggregate": round(r.mean_aggregate, 3),
                "horizon_observability": round(r.mean_axis("horizon_observability"), 3),
                "assumption_coherence": round(r.mean_axis("assumption_coherence"), 3),
                "indicator_specificity": round(r.mean_axis("indicator_specificity"), 3),
                "probability_calibration": round(r.mean_axis("probability_calibration"), 3),
                "n_falsifiers": r.n_falsifiers,
                "fixtures_run": len(r.fixtures_run),
                "total_latency_seconds": round(r.total_latency_seconds, 2),
                "errors": len(r.errors),
            })
        rows.sort(key=lambda row: row["mean_aggregate"], reverse=True)
        return rows


def _idea_for_fixture(fixture: BullCaseFixture) -> RankedIdea:
    return RankedIdea(
        rank=1,
        symbol=fixture.symbol,
        name=fixture.symbol,
        asset_type="stock",
        is_adr=False,
        sector=fixture.sector,
        theme=fixture.title,
        score=0.7,
        confidence=0.7,
        thesis=fixture.thesis,
        evidence=[],
        risks=[],
        score_breakdown={},
    )


def _assumptions_for_fixture(fixture: BullCaseFixture) -> list[BullAssumption]:
    return [BullAssumption(text=text) for text in fixture.assumptions]


def _profile_for_eval() -> dict[str, Any]:
    return {"risk_tolerance": "Moderate", "goal": "growth"}


def _run_one_pair(
    *,
    model_spec: ModelSpec,
    fixture: BullCaseFixture,
    judge: FalsifierJudge,
    llm: JsonGeneratingClient,
) -> tuple[list[ScoredFalsifier], float, list[str]]:
    """Run pre-mortem under one model on one fixture, score every falsifier."""
    errors: list[str] = []
    scored: list[ScoredFalsifier] = []
    assumptions = _assumptions_for_fixture(fixture)
    idea = _idea_for_fixture(fixture)

    t0 = time.monotonic()
    try:
        finding = _per_symbol_pre_mortem(llm, idea, assumptions, _profile_for_eval())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pre_mortem_failed: {fixture.slug}: {exc!r}")
        return scored, time.monotonic() - t0, errors
    latency_generate = time.monotonic() - t0

    for falsifier in finding["falsifiers"]:
        targeted = falsifier.get("breaks_assumption") or (assumptions[0]["text"] if assumptions else "")
        try:
            score = judge.score(
                falsifier=falsifier,
                targeted_assumption=targeted,
                thesis=fixture.thesis,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"judge_failed: {fixture.slug}/{falsifier.get('failure_mode', '?')[:40]}: {exc!r}")
            score = FalsifierScore(0.0, 0.0, 0.0, 0.0, comment="judge_exception")
        scored.append(ScoredFalsifier(
            model=model_spec.label,
            fixture_slug=fixture.slug,
            falsifier=falsifier,
            targeted_assumption=targeted,
            score=score,
            latency_seconds=latency_generate / max(1, len(finding["falsifiers"])),
        ))
    return scored, latency_generate, errors


def run_eval(
    *,
    models: list[ModelSpec],
    fixtures: list[BullCaseFixture],
    judge_spec: ModelSpec,
    repeats: int = 1,
) -> EvalReport:
    """Run the falsifier eval across ``models`` and ``fixtures``.

    Args:
        models: list of ModelSpec, each tested independently.
        fixtures: list of BullCaseFixture, each used by every model.
        judge_spec: ModelSpec for the **fixed judge model**. The judge
            client is instantiated once and reused across all (model,
            fixture) pairs to keep the rubric stable.
        repeats: number of times each (model, fixture) pair is run.
            Used to quantify LLM nondeterminism; the report includes all
            repeats so variance is computable.
    """
    if not models:
        raise ValueError("run_eval requires at least one model")
    if not fixtures:
        raise ValueError("run_eval requires at least one fixture")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")

    logger.info(
        "Eval start: %d models × %d fixtures × %d repeats, judge=%s",
        len(models), len(fixtures), repeats, judge_spec.label,
    )
    judge = FalsifierJudge(judge_spec.client_factory())
    results: list[ModelResult] = []

    for model_spec in models:
        logger.info("Eval model: %s", model_spec.label)
        client = model_spec.client_factory()
        result = ModelResult(model=model_spec.label)
        for fixture in fixtures:
            for repeat in range(repeats):
                logger.debug("  fixture=%s repeat=%d", fixture.slug, repeat)
                scored, latency, errors = _run_one_pair(
                    model_spec=model_spec, fixture=fixture, judge=judge, llm=client,
                )
                result.scored_falsifiers.extend(scored)
                result.fixtures_run.append(fixture.slug)
                result.total_latency_seconds += latency
                result.errors.extend(errors)
        logger.info(
            "  %s: %d falsifiers, mean aggregate=%.3f, errors=%d",
            model_spec.label, result.n_falsifiers, result.mean_aggregate, len(result.errors),
        )
        results.append(result)

    return EvalReport(
        results=results,
        judge_label=judge_spec.label,
        fixture_slugs=[fx.slug for fx in fixtures],
        repeats=repeats,
    )
