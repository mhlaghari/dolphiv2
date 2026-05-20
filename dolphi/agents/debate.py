"""Multi-round bull ⇌ bear debate.

After the initial bull and bear researchers run once in parallel, this
node runs N additional rebuttal rounds. In each round:

1. Bull reads the most recent bear case and writes a rebuttal that
   attacks the bear's specific claims.
2. Bear reads the most recent bull case (including the new rebuttal)
   and writes a counter-rebuttal.

Each rebuttal is appended as a fresh ``ResearcherOutput`` to
``bull_case`` / ``bear_case`` — those channels are
``Annotated[..., operator.add]`` so they accumulate across rounds.

This makes the conversation visible (every round is preserved) and lets
the downstream judge see the full debate while still letting the
pre-mortem agent extract assumptions from the original thesis plus all
rebuttals.

Cost: ``2 * rounds`` LLM calls (default 4 for ``rounds=2``).
"""

from __future__ import annotations

import logging
from typing import Any

from ..llm import OllamaClient
from ..models import AgentState, ResearcherOutput

logger = logging.getLogger(__name__)

_BULL_REBUTTAL_SYSTEM = (
    "You are a bullish equity researcher engaged in a structured debate. "
    "Your task: rebut the bear's most recent argument while reinforcing the bullish thesis. "
    "Attack the bear's specific claims — do not restate your own case in generic terms. "
    "Concede a single weakness in your own thesis if honesty demands it; this strengthens credibility. "
    "Output ONLY valid JSON with keys: reasoning (str), thesis (str — your updated bullish stance), "
    "conviction (float 0-1)."
)

_BEAR_REBUTTAL_SYSTEM = (
    "You are a bearish equity researcher engaged in a structured debate. "
    "Your task: rebut the bull's most recent argument while sharpening the bearish thesis. "
    "Attack the bull's specific claims — do not restate your own case in generic terms. "
    "Concede a single bull-side strength if honesty demands it; this strengthens credibility. "
    "Output ONLY valid JSON with keys: reasoning (str), thesis (str — your updated bearish stance), "
    "conviction (float 0-1)."
)


def _latest(items: list[ResearcherOutput]) -> ResearcherOutput | None:
    if not items:
        return None
    return items[-1]


def _format_side(label: str, item: ResearcherOutput | None) -> str:
    if item is None:
        return f"{label}: (no opening statement yet)"
    return (
        f"{label} (conviction {item.get('conviction', 0):.2f}):\n"
        f"  Thesis: {str(item.get('thesis', ''))[:600]}\n"
        f"  Reasoning: {str(item.get('reasoning', ''))[:600]}"
    )


def _rebut(
    llm: OllamaClient,
    system: str,
    opponent_label: str,
    opponent: ResearcherOutput | None,
    own_label: str,
    own_last: ResearcherOutput | None,
    round_index: int,
    profile: dict[str, Any],
) -> ResearcherOutput:
    prompt = (
        f"Round {round_index} of debate. User risk tolerance: {profile.get('risk_tolerance')}; goal: {profile.get('goal')}.\n\n"
        f"{_format_side(opponent_label, opponent)}\n\n"
        f"{_format_side(own_label + ' (your last turn)', own_last)}\n\n"
        f"Write your rebuttal. Refer to {opponent_label.lower()}'s specific points. Be concrete."
    )
    result = llm.generate_json(prompt, system=system, temperature=0.45)
    if "error" in result:
        return ResearcherOutput(
            reasoning="Rebuttal unavailable due to LLM error.",
            thesis=str(own_last.get("thesis", "")) if own_last else "",
            conviction=float(own_last.get("conviction", 0.5)) if own_last else 0.5,
        )
    return ResearcherOutput(
        reasoning=str(result.get("reasoning", "")),
        thesis=str(result.get("thesis", "")),
        conviction=max(0.0, min(1.0, float(result.get("conviction", 0.5)))),
    )


def debate(state: AgentState, llm: OllamaClient, **kwargs: Any) -> dict[str, list[ResearcherOutput]]:
    rounds = int(state.get("config", {}).get("debate_rounds", 2))
    if rounds <= 0:
        return {}

    profile = state["user_profile"]
    bull_history = list(state.get("bull_case", []) or [])
    bear_history = list(state.get("bear_case", []) or [])

    if not bull_history and not bear_history:
        logger.info("Debate skipped: no opening bull/bear cases found in state")
        return {}

    logger.info("Debate running %d rebuttal round(s)...", rounds)
    new_bull: list[ResearcherOutput] = []
    new_bear: list[ResearcherOutput] = []

    for idx in range(1, rounds + 1):
        bull_rebuttal = _rebut(
            llm,
            system=_BULL_REBUTTAL_SYSTEM,
            opponent_label="Bear",
            opponent=_latest(bear_history),
            own_label="Bull",
            own_last=_latest(bull_history),
            round_index=idx,
            profile=profile,
        )
        bull_history.append(bull_rebuttal)
        new_bull.append(bull_rebuttal)

        bear_rebuttal = _rebut(
            llm,
            system=_BEAR_REBUTTAL_SYSTEM,
            opponent_label="Bull",
            opponent=_latest(bull_history),
            own_label="Bear",
            own_last=_latest(bear_history),
            round_index=idx,
            profile=profile,
        )
        bear_history.append(bear_rebuttal)
        new_bear.append(bear_rebuttal)

        if state.get("config", {}).get("verbose"):
            logger.info(
                "Round %d: bull conviction=%.2f, bear conviction=%.2f",
                idx,
                bull_rebuttal["conviction"],
                bear_rebuttal["conviction"],
            )

    return {"bull_case": new_bull, "bear_case": new_bear}
