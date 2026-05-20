"""Pre-Mortem Agent — the falsification-first node.

Phase 1 implementation:
1. Extract the bull case's *named assumptions* in one LLM call. These
   are the load-bearing claims (e.g., "AI capex grows >30% YoY") that
   the bull thesis depends on.
2. For each top-ranked idea, run a per-symbol pre-mortem call. Each
   produced falsifier MUST cite exactly one assumption it breaks
   (constrained to the list from step 1) and specify a verification
   horizon.

This is more expensive than Phase 0 (1 + N LLM calls instead of 1) but
the cost buys (a) cross-grounded falsifiers that reference the bull's
own claims, and (b) richer per-symbol differentiation. For
``top_k = 5`` that's 6 LLM calls — acceptable on cheap models and
trivial on local Ollama.

The single most important property of this agent is still that its
prompts do NOT include the bull *thesis*. Only the bull's *named
assumptions* are passed in, and only into the per-symbol call. This
preserves the falsification-first stance while letting the agent
target assumptions specifically.
"""

from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import (
    AgentState,
    BullAssumption,
    Falsifier,
    PreMortemFinding,
    RankedIdea,
    ResearcherOutput,
)
from ._common import safe_float

logger = logging.getLogger(__name__)

_ASSUMPTION_SYSTEM_PROMPT = (
    "You are a research editor. Extract the load-bearing assumptions implicit in the bull thesis "
    "presented to you. An assumption is a specific factual claim about the world the thesis "
    "depends on — not a value judgment. Phrase each as a short positive statement "
    "(e.g., 'AI capex grows >30% YoY through 2027'). "
    "Return ONLY valid JSON, no markdown. Required shape:\n"
    '{"assumptions": [{"text": str}, ...]}\n'
    "Produce 3-5 distinct assumptions. Do not repeat the thesis."
)

_PRE_MORTEM_SYSTEM_PROMPT = (
    "You are a falsification-first risk researcher. Your only job is to BREAK the thesis "
    "for the symbol presented to you. Do not defend it; do not produce balanced commentary. "
    "Each falsifier MUST target exactly ONE of the named assumptions provided. "
    "Each falsifier MUST be observable, dated within the provided horizon, and inexpensive to verify. "
    "Return ONLY valid JSON, no markdown. Required shape:\n"
    "{\n"
    '  "falsifiers": [\n'
    "    {\n"
    '      "failure_mode": str,\n'
    '      "probability": float in [0, 1],\n'
    '      "leading_indicator": str,\n'
    '      "breaks_assumption": str (must match one of the provided assumption texts),\n'
    '      "horizon": str (e.g. "30 days", "6 months")\n'
    "    }, ... (exactly 3)\n"
    "  ]\n"
    "}\n"
    "probability is your honest estimate of the event occurring in the named horizon — not a confidence."
)


def _empty_finding(symbol: str) -> PreMortemFinding:
    return PreMortemFinding(symbol=symbol, falsifiers=[], overall_fragility=0.0)


def _coerce_falsifier(raw: Any, allowed_assumptions: list[str]) -> Falsifier | None:
    if not isinstance(raw, dict):
        return None
    failure_mode = str(raw.get("failure_mode", "")).strip()
    if not failure_mode:
        return None
    breaks = str(raw.get("breaks_assumption", "")).strip()
    if allowed_assumptions:
        match = next(
            (assumption for assumption in allowed_assumptions if breaks and breaks.lower() in assumption.lower()),
            None,
        )
        if match is None:
            match = next(
                (assumption for assumption in allowed_assumptions if assumption.lower() in breaks.lower()),
                None,
            )
        breaks = match or allowed_assumptions[0]
    return Falsifier(
        failure_mode=failure_mode,
        probability=max(0.0, min(1.0, safe_float(raw.get("probability", 0.0), 0.0))),
        leading_indicator=str(raw.get("leading_indicator", "")).strip(),
        breaks_assumption=breaks,
        horizon=str(raw.get("horizon", "")).strip() or "6 months",
    )


def _parse_per_symbol(raw: Any, allowed_assumptions: list[str]) -> list[Falsifier]:
    items = raw.get("falsifiers") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    falsifiers: list[Falsifier] = []
    for entry in items[:3]:
        falsifier = _coerce_falsifier(entry, allowed_assumptions)
        if falsifier is not None:
            falsifiers.append(falsifier)
    return falsifiers


def _extract_bull_assumptions(llm: OllamaClient, bull_case: list[ResearcherOutput]) -> list[BullAssumption]:
    if not bull_case:
        return []
    latest = bull_case[-1] if isinstance(bull_case, list) else bull_case
    thesis = str(latest.get("thesis", "")) if isinstance(latest, dict) else ""
    reasoning = str(latest.get("reasoning", "")) if isinstance(latest, dict) else ""
    if not (thesis or reasoning):
        return []
    prompt = (
        "Bull thesis:\n"
        f"  Thesis: {thesis[:600]}\n"
        f"  Reasoning: {reasoning[:800]}\n\n"
        "Extract the 3-5 load-bearing assumptions this thesis depends on."
    )
    result = llm.generate_json(prompt, system=_ASSUMPTION_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        logger.warning("Bull assumption extraction failed: %s", result.get("error"))
        return []
    raw_items = result.get("assumptions") if isinstance(result, dict) else None
    if not isinstance(raw_items, list):
        return []
    assumptions: list[BullAssumption] = []
    for entry in raw_items[:5]:
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).strip()
        elif isinstance(entry, str):
            text = entry.strip()
        else:
            continue
        if text:
            assumptions.append(BullAssumption(text=text))
    return assumptions


def _per_symbol_pre_mortem(
    llm: OllamaClient,
    idea: RankedIdea,
    assumptions: list[BullAssumption],
    profile: dict[str, Any],
) -> PreMortemFinding:
    symbol = idea["symbol"]
    assumption_texts = [item["text"] for item in assumptions]
    if assumption_texts:
        assumption_block = "\n".join(f"  {i + 1}. {text}" for i, text in enumerate(assumption_texts))
    else:
        assumption_block = "  (no named assumptions extracted — invent up to 3 implicit assumptions for this symbol and break each)"

    prompt = (
        f"User risk tolerance: {profile.get('risk_tolerance')}, goal: {profile.get('goal')}\n\n"
        f"Symbol to attack: {symbol} ({idea.get('sector', 'n/a')})\n"
        f"Theme: {idea.get('theme', 'n/a')}\n"
        f"Thesis (do not defend): {str(idea.get('thesis', ''))[:300]}\n\n"
        f"Bull-side load-bearing assumptions you may target:\n{assumption_block}\n\n"
        "Produce exactly 3 falsifiers. Each must:\n"
        "  - target ONE assumption from the list verbatim in the breaks_assumption field;\n"
        "  - be observable in a stated horizon ≤ 12 months;\n"
        "  - name a concrete leading indicator a researcher could check weekly."
    )

    result = llm.generate_json(prompt, system=_PRE_MORTEM_SYSTEM_PROMPT, temperature=0.4)
    if "error" in result:
        logger.warning("Pre-mortem JSON parse failed for %s: %s", symbol, result.get("error"))
        return _empty_finding(symbol)

    falsifiers = _parse_per_symbol(result, assumption_texts)
    fragility = (
        sum(item["probability"] for item in falsifiers) / len(falsifiers) if falsifiers else 0.0
    )
    return PreMortemFinding(
        symbol=symbol,
        falsifiers=falsifiers,
        overall_fragility=round(fragility, 3),
    )


def pre_mortem(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, Any]:
    logger.info("Pre-Mortem agent running (Phase 1)...")

    ranked_ideas = state.get("ranked_ideas", [])[:5]
    if not ranked_ideas:
        return {"pre_mortem_findings": [], "bull_assumptions": []}

    profile = state["user_profile"]
    bull_case = state.get("bull_case", []) or []

    assumptions = _extract_bull_assumptions(llm, bull_case)
    if state.get("config", {}).get("verbose"):
        logger.info("Extracted %d bull assumptions", len(assumptions))

    findings: list[PreMortemFinding] = []
    for idea in ranked_ideas:
        finding = _per_symbol_pre_mortem(llm, idea, assumptions, profile)
        findings.append(finding)
        if state.get("config", {}).get("verbose"):
            logger.info(
                "Pre-Mortem %s: fragility=%.2f, %d falsifiers",
                finding["symbol"],
                finding["overall_fragility"],
                len(finding["falsifiers"]),
            )

    return {
        "pre_mortem_findings": findings,
        "bull_assumptions": assumptions,
    }
