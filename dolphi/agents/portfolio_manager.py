from __future__ import annotations

import logging
import re
from typing import Any

from ..allocation.optimizer import allocate_ranked_ideas
from ..llm import OllamaClient
from ..models import AgentState, Allocation, PortfolioRecommendation

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior portfolio manager. Synthesise technical, fundamental, sentiment, bull/bear, "
    "risk, and PRE-MORTEM (falsifier) research into a final portfolio allocation. "
    "Explain narratives for two audiences at once: plain-English beginner clarity and professional investor depth. "
    "EVERY position must directly address its top falsifier, if one exists, in plain language. "
    "Output ONLY valid JSON with these exact keys:\n"
    '  "allocations": [{"symbol": str, "allocation_pct": float, "rationale": str}, ...]\n'
    '  "notes": str (cross-domain insights)\n'
    "Allocation percentages must sum to 100. Include 3-7 assets. "
    "Match the asset allocation to the user's risk tolerance and goal."
)


def _format_research_items(items: list[dict[str, Any]], key: str, limit: int = 3) -> str:
    if not items:
        return "None"
    lines = []
    for i, item in enumerate(items[:limit], 1):
        conviction = item.get("conviction")
        thesis = item.get(key, item.get("reasoning", ""))
        lines.append(f"{i}. Conviction: {conviction}; {str(thesis)[:600]}")
    return "\n".join(lines)


def _format_risk_items(items: list[dict[str, Any]], limit: int = 3) -> str:
    if not items:
        return "None"
    lines = []
    for i, item in enumerate(items[:limit], 1):
        lines.append(
            f"{i}. fit={item.get('fits_profile')} score={item.get('adjusted_score')}; "
            f"{str(item.get('reasoning', ''))[:300]}"
        )
    return "\n".join(lines)


def _clean_allocation(raw: dict[str, Any]) -> Allocation:
    return {
        "symbol": str(raw.get("symbol", "CASH")),
        "allocation_pct": float(raw.get("allocation_pct", 0.0)),
        "rationale": str(raw.get("rationale", "")),
    }


def _sanitize_notes(note: str, allocated_symbols: set[str]) -> str:
    if not note:
        return ""
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", note.strip()):
        symbols = set(re.findall(r"\b[A-Z]{2,5}\b", sentence))
        unknown_symbols = symbols - allocated_symbols
        if unknown_symbols:
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _format_per_ticker(per_ticker_blocks: list[tuple[str, dict[str, Any]]], limit: int = 5) -> str:
    if not any(block for _, block in per_ticker_blocks):
        return "  (not available)"
    symbols: list[str] = []
    for _, block in per_ticker_blocks:
        symbols.extend(block.keys())
    seen: list[str] = []
    for sym in symbols:
        if sym not in seen:
            seen.append(sym)
        if len(seen) >= limit:
            break
    lines = []
    for sym in seen:
        parts = [f"  - {sym}:"]
        for label, block in per_ticker_blocks:
            entry = block.get(sym) or {}
            score = entry.get("score") if isinstance(entry, dict) else None
            reason = str(entry.get("reasoning", "")) if isinstance(entry, dict) else ""
            parts.append(f"      {label} score={score} :: {reason[:180]}")
        lines.append("\n".join(parts))
    return "\n".join(lines) or "  (no per-ticker reads)"


def _format_debate(judgments: list[dict[str, Any]], limit: int = 5) -> str:
    if not judgments:
        return "  (no debate judgments)"
    rows = []
    for item in judgments[:limit]:
        delta = float(item.get("conviction_delta", 0))
        sign = "+" if delta > 0 else ""
        rows.append(
            f"  - {item.get('symbol')}: winner={item.get('winner')} delta={sign}{delta:.2f} :: "
            f"{str(item.get('rationale', ''))[:200]}"
        )
    return "\n".join(rows)


def _format_pre_mortem(findings: list[dict[str, Any]], limit: int = 5) -> str:
    if not findings:
        return "  (no pre-mortem findings available)"
    blocks: list[str] = []
    for finding in findings[:limit]:
        falsifiers = finding.get("falsifiers", []) or []
        if not falsifiers:
            blocks.append(f"  - {finding.get('symbol')}: no falsifiers produced (fragility=0.00)")
            continue
        bullets = [
            f"      * p={item.get('probability', 0):.2f} [{item.get('horizon', '')[:24]}] — "
            f"{item.get('failure_mode', '')[:160]} "
            f"[breaks: {item.get('breaks_assumption', '')[:80]}; watch: {item.get('leading_indicator', '')[:80]}]"
            for item in falsifiers[:3]
        ]
        blocks.append(
            f"  - {finding.get('symbol')} (fragility={finding.get('overall_fragility', 0):.2f}):\n"
            + "\n".join(bullets)
        )
    return "\n".join(blocks)


def portfolio_manager(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, PortfolioRecommendation]:
    logger.info("Portfolio manager synthesizing results...")

    profile = state["user_profile"]
    tech = state.get("technical_analysis", {})
    fund = state.get("fundamental_analysis", {})
    sent = state.get("sentiment_analysis", {})
    per_ticker_tech = state.get("per_ticker_technical", {}) or {}
    per_ticker_fund = state.get("per_ticker_fundamental", {}) or {}
    per_ticker_sent = state.get("per_ticker_sentiment", {}) or {}
    bull_list = state.get("bull_case", [])
    bear_list = state.get("bear_case", [])
    risk_agg_list = state.get("risk_aggressive_eval", [])
    risk_con_list = state.get("risk_conservative_eval", [])
    ranked_ideas = state.get("ranked_ideas", [])
    theme_clusters = state.get("theme_clusters", [])
    pre_mortem_findings = state.get("pre_mortem_findings", []) or []
    debate_judgments = state.get("debate_judgments", []) or []
    reflection = state.get("reflection_summary", {}) or {}

    per_ticker_block = _format_per_ticker(
        [
            ("Technical", per_ticker_tech),
            ("Fundamental", per_ticker_fund),
            ("Sentiment", per_ticker_sent),
        ]
    )
    pre_mortem_block = _format_pre_mortem(pre_mortem_findings)
    debate_block = _format_debate(debate_judgments)
    reflection_text = str(reflection.get("summary_text", "")).strip()
    reflection_block = reflection_text or "  (no graded prior decisions)"

    prompt = (
        f"=== USER PROFILE ===\n"
        f"Risk: {profile['risk_tolerance']}, Goal: {profile['goal']}\n"
        f"Savings: {profile['total_savings']} {profile['currency']}\n"
        f"Salary: {profile['monthly_salary']} {profile['currency']}/mo\n"
        f"Preferred asset classes: {profile['preferred_asset_classes']}\n\n"
        f"=== TECHNICAL — MARKET CONTEXT ===\nScore: {tech.get('score')}\n{tech.get('reasoning', '')[:500]}\n\n"
        f"=== FUNDAMENTAL — COHORT VIEW ===\nScore: {fund.get('score')}\n{fund.get('reasoning', '')[:500]}\n\n"
        f"=== SENTIMENT — MOOD ===\nScore: {sent.get('score')}\n{sent.get('reasoning', '')[:500]}\n\n"
        f"=== PER-TICKER ANALYST READS ===\n{per_ticker_block}\n\n"
        f"=== DISCOVERED IDEAS ===\n{ranked_ideas[:5]}\n\n"
        f"=== THEMES ===\n{theme_clusters[:3]}\n\n"
        f"=== BULL CASES ===\n{_format_research_items(bull_list, 'thesis')}\n\n"
        f"=== BEAR CASES ===\n{_format_research_items(bear_list, 'thesis')}\n\n"
        f"=== DEBATE VERDICTS ===\n{debate_block}\n\n"
        f"=== PRIOR DECISION OUTCOMES (realised vs SPY) ===\n{reflection_block}\n\n"
        f"=== PRE-MORTEM (FALSIFIERS) ===\n{pre_mortem_block}\n\n"
        f"=== RISK EVALUATIONS ===\n"
        f"Aggressive:\n{_format_risk_items(risk_agg_list)}\n"
        f"Conservative:\n{_format_risk_items(risk_con_list)}\n\n"
        f"=== MEMORY HITS ===\n"
    )

    hits = state.get("memory_hits", [])
    if hits:
        for i, hit in enumerate(hits[:3], 1):
            prompt += f"Similar past situation {i}: {hit.get('text', '')[:300]}\n"
    else:
        prompt += "No similar past situations found.\n"

    prompt += (
        "\nIMPORTANT: Produce a diversified portfolio allocation based on ALL the above.\n"
        "- For Aggressive risk: tilt toward stocks/growth (70-90% equities)\n"
        "- For Moderate risk: balanced (50-70% equities, rest bonds/defensive)\n"
        "- For Conservative risk: capital preservation (20-40% equities, rest bonds/cash)\n"
        "Include at least one bond/defensive asset for non-aggressive profiles.\n"
        "Sum of allocation_pct must equal exactly 100.\n"
        "In notes, explain the narrative chain in plain English, then the professional investor view. "
        "If PRIOR DECISION OUTCOMES are shown, briefly call out one lesson learnt from them. "
        "Conclude with the TOP TWO falsifiers from the pre-mortem and how each one would be observed."
    )

    result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.4)
    if "error" in result:
        result = {
            "allocations": [
                {"symbol": "SPY", "allocation_pct": 40, "rationale": "Default diversified equity"},
                {"symbol": "BND", "allocation_pct": 40, "rationale": "Default bond hedge"},
                {"symbol": "CASH", "allocation_pct": 20, "rationale": "Default cash reserve"},
            ],
            "notes": "Recommendation unavailable due to analysis error. Above is a generic starter allocation.",
        }

    if ranked_ideas:
        deterministic = allocate_ranked_ideas(
            ranked_ideas,
            profile,
            pre_mortem_findings=pre_mortem_findings,
            debate_judgments=debate_judgments,
        )
        allocations = deterministic["allocations"]
        allocated_symbols = {allocation["symbol"] for allocation in allocations}
        note = _sanitize_notes(result.get("notes", ""), allocated_symbols) or deterministic["notes"]
        note = f"{note} Deterministic risk caps were used for allocation sizing."
    else:
        allocations = result.get("allocations", [])
        note = result.get("notes", "")

    total = sum(a.get("allocation_pct", 0) for a in allocations)
    if total > 0 and abs(total - 100) > 0.01:
        factor = 100.0 / total
        for a in allocations:
            a["allocation_pct"] = round(a["allocation_pct"] * factor, 1)
        note += f" (allocations normalized from {total:.0f}% to 100%)"

    rec = PortfolioRecommendation(allocations=[_clean_allocation(a) for a in allocations], notes=note)

    if state.get("config", {}).get("verbose"):
        logger.info("Portfolio recommendation generated with %d assets", len(allocations))

    return {"portfolio_recommendation": rec}
