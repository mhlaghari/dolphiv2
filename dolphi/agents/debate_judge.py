"""Debate judge — emits per-symbol conviction deltas.

The judge reads the full bull and bear conversation, then for each of
the top-ranked ideas issues:

- ``winner``: ``"bull"`` | ``"bear"`` | ``"tie"``
- ``conviction_delta``: float in ``[-0.3, 0.3]`` — added to the idea's
  score by the allocator. Positive favours the bull, negative favours
  the bear.
- ``rationale``: one-sentence explanation.

The delta is bounded so a single debate cannot dominate the
ranker / pre-mortem signals. We typically expect ``|delta| < 0.2`` in
practice; the cap of 0.3 prevents runaway swings while still letting
the debate move allocations meaningfully.
"""

from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, DebateJudgment, RankedIdea, ResearcherOutput

logger = logging.getLogger(__name__)


_JUDGE_SYSTEM_PROMPT = (
    "You are the debate judge. You have read a full multi-round bull vs bear debate. "
    "For EACH symbol presented, decide which side argued more persuasively about THAT symbol "
    "and assign a conviction_delta in the range [-0.3, 0.3]. "
    "Positive delta favours the bull; negative favours the bear; zero means the debate did not "
    "shift conviction on this symbol. Use deltas with absolute value > 0.2 only when one side "
    "clearly dismantled the other on this specific name. "
    "Output ONLY valid JSON, no markdown:\n"
    "{\n"
    '  "judgments": [\n'
    "    {\n"
    '      "symbol": str,\n'
    '      "winner": "bull" | "bear" | "tie",\n'
    '      "conviction_delta": float in [-0.3, 0.3],\n'
    '      "rationale": str (one sentence)\n'
    "    }, ... (one per symbol provided)\n"
    "  ]\n"
    "}"
)


_VALID_WINNERS = {"bull", "bear", "tie"}
_DELTA_CAP = 0.3


def _format_side(history: list[ResearcherOutput], label: str) -> str:
    if not history:
        return f"{label}: (silent)"
    lines = [f"{label}:"]
    for i, item in enumerate(history, 1):
        thesis = str(item.get("thesis", ""))[:280]
        reasoning = str(item.get("reasoning", ""))[:280]
        conviction = item.get("conviction", 0)
        lines.append(f"  Turn {i} (conviction {conviction:.2f}): {thesis}")
        if reasoning:
            lines.append(f"    Reasoning: {reasoning}")
    return "\n".join(lines)


def _coerce(raw: Any, ranked_symbols: set[str]) -> DebateJudgment | None:
    if not isinstance(raw, dict):
        return None
    symbol = str(raw.get("symbol", "")).strip().upper()
    if not symbol or symbol not in ranked_symbols:
        return None
    winner = str(raw.get("winner", "tie")).strip().lower()
    if winner not in _VALID_WINNERS:
        winner = "tie"
    try:
        delta = float(raw.get("conviction_delta", 0.0))
    except (TypeError, ValueError):
        delta = 0.0
    delta = max(-_DELTA_CAP, min(_DELTA_CAP, delta))
    if winner == "tie":
        delta = 0.0
    rationale = str(raw.get("rationale", "")).strip()
    return DebateJudgment(
        symbol=symbol,
        winner=winner,
        conviction_delta=round(delta, 3),
        rationale=rationale,
    )


def debate_judge(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, list[DebateJudgment]]:
    ranked_ideas: list[RankedIdea] = state.get("ranked_ideas", []) or []
    if not ranked_ideas:
        return {"debate_judgments": []}

    bull_history = state.get("bull_case", []) or []
    bear_history = state.get("bear_case", []) or []
    if not bull_history and not bear_history:
        return {"debate_judgments": []}

    top_ideas = ranked_ideas[:5]
    symbol_block = "\n".join(
        f"  - {idea['symbol']} ({idea.get('sector', 'n/a')}): {str(idea.get('thesis', ''))[:160]}"
        for idea in top_ideas
    )

    prompt = (
        f"User risk tolerance: {state['user_profile'].get('risk_tolerance')}\n\n"
        f"Symbols under consideration:\n{symbol_block}\n\n"
        f"=== BULL TRANSCRIPT ===\n{_format_side(bull_history, 'BULL')}\n\n"
        f"=== BEAR TRANSCRIPT ===\n{_format_side(bear_history, 'BEAR')}\n\n"
        "Produce one judgment per symbol above. Be calibrated; do not default to ties."
    )

    result = llm.generate_json(prompt, system=_JUDGE_SYSTEM_PROMPT, temperature=0.3)
    if "error" in result:
        logger.warning("Debate judge failed: %s", result.get("error"))
        return {"debate_judgments": []}

    raw_items = result.get("judgments")
    if not isinstance(raw_items, list):
        return {"debate_judgments": []}

    ranked_symbols = {idea["symbol"] for idea in top_ideas}
    judgments: list[DebateJudgment] = []
    seen: set[str] = set()
    for raw in raw_items:
        judgment = _coerce(raw, ranked_symbols)
        if judgment is None or judgment["symbol"] in seen:
            continue
        seen.add(judgment["symbol"])
        judgments.append(judgment)

    if state.get("config", {}).get("verbose"):
        logger.info("Debate judge emitted %d judgments", len(judgments))

    return {"debate_judgments": judgments}
