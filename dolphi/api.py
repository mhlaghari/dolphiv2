"""Public Python library facade over the dolphi graph workflow.

Other agents (including external trading bots) should import from this
module rather than touching LangGraph state directly. The four public
functions below — ``evaluate``, ``check_falsifiers``, ``list_falsifiers``,
``get_decision_log`` — are the entire supported surface.

All functions are sync. Internal TypedDicts are converted to Pydantic v2
models at this boundary; downstream agent code keeps its TypedDicts.

``mock=True`` runs the whole pipeline offline with a built-in deterministic
LLM stub and the ``DataFetcher(mock=True)`` path — no network, no API keys.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .check import compute_adjustments
from .config import Config
from .data.base import DataFetcher
from .graph.workflow import build_discovery_state, build_portfolio_graph
from .llm.factory import create_llm_client


# ---------- Pydantic v2 models (public API boundary) -------------------------


class UserProfile(BaseModel):
    total_savings: float
    monthly_salary: float = 0.0
    currency: str = "USD"
    goal: Literal["retirement", "growth", "income", "other"] = "growth"
    risk_tolerance: Literal["Aggressive", "Moderate", "Conservative"] = "Moderate"
    preferred_asset_classes: list[str] = Field(default_factory=lambda: ["stocks", "etfs"])
    investment_percentage: float = 100.0


class Falsifier(BaseModel):
    failure_mode: str
    probability: float
    leading_indicator: str
    breaks_assumption: str
    horizon: str


class RankedIdea(BaseModel):
    rank: int
    symbol: str
    score: float
    confidence: float
    thesis: str
    evidence: list[str]
    risks: list[str]


class DebateJudgment(BaseModel):
    symbol: str
    winner: Literal["bull", "bear", "tie"]
    conviction_delta: float
    rationale: str


class Allocation(BaseModel):
    symbol: str
    weight_pct: float
    rationale: str


class EvaluateResult(BaseModel):
    ranked_ideas: list[RankedIdea]
    falsifiers: dict[str, list[Falsifier]]
    fragility: dict[str, float]
    debate: dict[str, DebateJudgment]
    allocations: list[Allocation]
    decision_id: str


class CheckResult(BaseModel):
    decision_id: str
    position_adjustments: dict[str, float]
    triggered_falsifiers: list[dict]
    notes: list[str]


# ---------- mock LLM for offline mode ----------------------------------------


class _MockLLM:
    """Deterministic LLM stub used when ``evaluate(mock=True)``.

    Mirrors the FakeLLM in ``tests/test_workflow_smoke.py`` so the graph
    produces a complete, structured result without network calls.
    """

    def generate_json(self, prompt: str, system: str | None = None, temperature: float = 0.3) -> dict:
        system_text = (system or "").lower()
        if "research editor" in system_text:
            return {
                "assumptions": [
                    {"text": "Demand growth sustains current revenue trajectory"},
                    {"text": "Competitive moat remains intact"},
                    {"text": "Valuation multiple is supported by fundamentals"},
                ]
            }
        if "falsification-first" in system_text:
            return {
                "falsifiers": [
                    {
                        "failure_mode": "Demand growth decelerates sharply",
                        "probability": 0.30,
                        "leading_indicator": "Quarterly revenue guides",
                        "breaks_assumption": "Demand growth sustains current revenue trajectory",
                        "horizon": "6 months",
                    },
                    {
                        "failure_mode": "Competitive threat materializes",
                        "probability": 0.25,
                        "leading_indicator": "Market share data",
                        "breaks_assumption": "Competitive moat remains intact",
                        "horizon": "12 months",
                    },
                    {
                        "failure_mode": "Multiple compression on rates",
                        "probability": 0.20,
                        "leading_indicator": "10y UST yield trend",
                        "breaks_assumption": "Valuation multiple is supported by fundamentals",
                        "horizon": "9 months",
                    },
                ]
            }
        if "bullish equity researcher engaged in a structured debate" in system_text:
            return {"reasoning": "bull rebuttal", "thesis": "thesis still durable", "conviction": 0.78}
        if "bearish equity researcher engaged in a structured debate" in system_text:
            return {"reasoning": "bear rebuttal", "thesis": "valuation risk", "conviction": 0.42}
        if "debate judge" in system_text:
            return {"judgments": []}
        if "bullish" in system_text:
            return {"reasoning": "bullish view", "thesis": "secular demand", "conviction": 0.75}
        if "bearish" in system_text:
            return {"reasoning": "bearish view", "thesis": "valuation risk", "conviction": 0.45}
        if "risk assessment" in system_text:
            return {"reasoning": "risk reviewed", "fits_profile": True, "adjusted_score": 0.65}
        if "portfolio manager" in system_text:
            return {
                "allocations": [
                    {"symbol": "NVDA", "allocation_pct": 35.0, "rationale": "mock allocation"},
                    {"symbol": "BND", "allocation_pct": 65.0, "rationale": "ballast"},
                ],
                "notes": "mock recommendation",
            }
        if "technical analyst" in system_text or "fundamental analyst" in system_text or "sentiment analyst" in system_text:
            return {"per_ticker": {}, "overall_reasoning": "neutral", "overall_score": 0.0}
        return {"reasoning": "analysis", "score": 0.5, "details": {}}


# ---------- internal helpers --------------------------------------------------


_DEFAULT_LOG_PATH = Path.home() / ".dolphi" / "decision_log.jsonl"


def _default_profile() -> UserProfile:
    return UserProfile(total_savings=100_000.0, monthly_salary=10_000.0)


def _coerce_profile(profile: UserProfile | dict | None) -> UserProfile:
    if profile is None:
        return _default_profile()
    if isinstance(profile, UserProfile):
        return profile
    return UserProfile(**profile)


def _load_config(config_path: Path | str | None) -> Config:
    if config_path is not None:
        import os

        os.environ["DOLPHI_CONFIG"] = str(config_path)
    return Config()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _find_decision(records: list[dict], decision_id: str | None) -> dict | None:
    """Find a record by decision_id (matched against timestamp); else the most recent
    with ``pre_mortem_findings``."""
    candidates = [r for r in records if "pre_mortem_findings" in r]
    if not candidates:
        return None
    if decision_id is None:
        return candidates[-1]
    for record in reversed(candidates):
        if record.get("timestamp") == decision_id or record.get("decision_date") == decision_id:
            return record
    return None


# ---------- public API --------------------------------------------------------


def evaluate(
    *,
    symbols: list[str] | None = None,
    profile: UserProfile | dict | None = None,
    top_k: int = 5,
    mock: bool = False,
    config_path: Path | str | None = None,
) -> EvaluateResult:
    """Run the full multi-agent workflow and return a structured result.

    When ``mock=True``, the pipeline runs offline with a deterministic LLM
    stub and ``DataFetcher(mock=True)`` — safe to call in CI with no keys.
    """
    config = _load_config(config_path)
    user_profile = _coerce_profile(profile)
    profile_dict = user_profile.model_dump()

    data = DataFetcher(cache=None, skip_cache=True, mock=mock)
    llm: Any = _MockLLM() if mock else create_llm_client(config)

    discovery = build_discovery_state(
        profile_dict,
        data,
        top_k=top_k,
        seed_symbols=symbols,
        llm=None if mock else llm,
    )

    market_data = data.get_market_summary()
    sectors = data.get_sector_performance()

    initial_state: dict = {
        "user_profile": profile_dict,
        "market_data": {
            "spx_level": market_data.get("spx_level"),
            "vix_level": market_data.get("vix_level"),
            "key_sectors": sectors,
            "news_headlines": [],
        },
        "technical_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "fundamental_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "sentiment_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "per_ticker_technical": {},
        "per_ticker_fundamental": {},
        "per_ticker_sentiment": {},
        "bull_case": [],
        "bear_case": [],
        "risk_aggressive_eval": [],
        "risk_conservative_eval": [],
        "pre_mortem_findings": [],
        "bull_assumptions": [],
        "debate_judgments": [],
        "reflection_summary": {"entries_count": 0, "summary_text": "", "entries": []},
        "portfolio_recommendation": {"allocations": [], "notes": ""},
        "memory_hits": [],
        "config": {
            "verbose": False,
            "provider": config.llm_provider,
            "model": config.llm_model,
            "research_depth": config.research_depth,
            "use_memory": False,
        },
        **discovery,
    }

    graph = build_portfolio_graph(llm, data)
    final_state = graph.invoke(initial_state)

    decision_id = datetime.now(timezone.utc).isoformat(timespec="seconds")

    ranked_ideas_out: list[RankedIdea] = []
    for idea in final_state.get("ranked_ideas", []) or []:
        ranked_ideas_out.append(
            RankedIdea(
                rank=int(idea.get("rank", 0)),
                symbol=str(idea.get("symbol", "")),
                score=float(idea.get("score", 0.0) or 0.0),
                confidence=float(idea.get("confidence", 0.0) or 0.0),
                thesis=str(idea.get("thesis", "")),
                evidence=list(idea.get("evidence", []) or []),
                risks=list(idea.get("risks", []) or []),
            )
        )

    falsifiers_by_symbol: dict[str, list[Falsifier]] = {}
    fragility_by_symbol: dict[str, float] = {}
    for finding in final_state.get("pre_mortem_findings", []) or []:
        symbol = str(finding.get("symbol", ""))
        if not symbol:
            continue
        fragility_by_symbol[symbol] = float(finding.get("overall_fragility", 0.0) or 0.0)
        falsifiers_by_symbol[symbol] = [
            Falsifier(
                failure_mode=str(f.get("failure_mode", "")),
                probability=float(f.get("probability", 0.0) or 0.0),
                leading_indicator=str(f.get("leading_indicator", "")),
                breaks_assumption=str(f.get("breaks_assumption", "")),
                horizon=str(f.get("horizon", "")),
            )
            for f in (finding.get("falsifiers", []) or [])
        ]

    debate_by_symbol: dict[str, DebateJudgment] = {}
    for judgment in final_state.get("debate_judgments", []) or []:
        symbol = str(judgment.get("symbol", ""))
        if not symbol:
            continue
        winner = str(judgment.get("winner", "tie")).lower()
        if winner not in ("bull", "bear", "tie"):
            winner = "tie"
        debate_by_symbol[symbol] = DebateJudgment(
            symbol=symbol,
            winner=winner,  # type: ignore[arg-type]
            conviction_delta=float(judgment.get("conviction_delta", 0.0) or 0.0),
            rationale=str(judgment.get("rationale", "")),
        )

    allocations_out: list[Allocation] = []
    rec = final_state.get("portfolio_recommendation", {}) or {}
    for alloc in rec.get("allocations", []) or []:
        allocations_out.append(
            Allocation(
                symbol=str(alloc.get("symbol", "")),
                weight_pct=float(alloc.get("allocation_pct", 0.0) or 0.0),
                rationale=str(alloc.get("rationale", "")),
            )
        )

    return EvaluateResult(
        ranked_ideas=ranked_ideas_out,
        falsifiers=falsifiers_by_symbol,
        fragility=fragility_by_symbol,
        debate=debate_by_symbol,
        allocations=allocations_out,
        decision_id=decision_id,
    )


def check_falsifiers(
    *,
    feedback: dict[str, Literal["safe", "triggered", "unsure"]],
    decision_id: str | None = None,
    jsonl_path: Path | str | None = None,
) -> CheckResult:
    """Apply weekly falsifier-check feedback to a stored decision.

    ``feedback`` keys are falsifier IDs of the form ``"{symbol}-{index}"``
    (0-based index into the per-symbol falsifier list). Values are one of
    ``"safe" | "triggered" | "unsure"``. Returns a ``CheckResult`` whose
    ``position_adjustments`` map gives the symbol-level delta to apply
    (negative numbers mean cut the position by that fraction).

    Pure function — no Console prompts, no I/O beyond reading the log.
    """
    path = Path(jsonl_path) if jsonl_path is not None else _DEFAULT_LOG_PATH
    records = _read_jsonl(path)
    record = _find_decision(records, decision_id)
    if record is None:
        return CheckResult(
            decision_id=decision_id or "",
            position_adjustments={},
            triggered_falsifiers=[],
            notes=["no matching decision found"],
        )

    resolved_id = str(record.get("timestamp") or record.get("decision_date") or "")
    adjustments, triggered = compute_adjustments(record, feedback)
    notes: list[str] = []
    if not feedback:
        notes.append("empty feedback dict — no adjustments computed")
    return CheckResult(
        decision_id=resolved_id,
        position_adjustments=adjustments,
        triggered_falsifiers=triggered,
        notes=notes,
    )


def list_falsifiers(
    *,
    decision_id: str | None = None,
    jsonl_path: Path | str | None = None,
) -> dict[str, list[Falsifier]]:
    """Return falsifiers from a stored decision, keyed by symbol.

    The list order is the canonical per-symbol order; in ``check_falsifiers``
    you reference each falsifier by ``"{symbol}-{index}"`` where index is the
    0-based position in this list.
    """
    path = Path(jsonl_path) if jsonl_path is not None else _DEFAULT_LOG_PATH
    records = _read_jsonl(path)
    record = _find_decision(records, decision_id)
    if record is None:
        return {}
    out: dict[str, list[Falsifier]] = {}
    for finding in record.get("pre_mortem_findings", []) or []:
        symbol = str(finding.get("symbol", ""))
        if not symbol:
            continue
        out[symbol] = [
            Falsifier(
                failure_mode=str(f.get("failure_mode", "")),
                probability=float(f.get("probability", 0.0) or 0.0),
                leading_indicator=str(f.get("leading_indicator", "")),
                breaks_assumption=str(f.get("breaks_assumption", "")),
                horizon=str(f.get("horizon", "")),
            )
            for f in (finding.get("falsifiers", []) or [])
        ]
    return out


def get_decision_log(
    *,
    jsonl_path: Path | str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return up to ``limit`` most recent decision-log records (newest last)."""
    path = Path(jsonl_path) if jsonl_path is not None else _DEFAULT_LOG_PATH
    records = _read_jsonl(path)
    if limit <= 0:
        return []
    return records[-limit:]


__all__ = [
    "Allocation",
    "CheckResult",
    "DebateJudgment",
    "EvaluateResult",
    "Falsifier",
    "RankedIdea",
    "UserProfile",
    "check_falsifiers",
    "evaluate",
    "get_decision_log",
    "list_falsifiers",
]
