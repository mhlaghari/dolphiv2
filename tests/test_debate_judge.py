"""Tests for the debate judge — per-symbol conviction deltas."""

from __future__ import annotations

from dolphi.agents.debate_judge import debate_judge


def _idea(symbol: str) -> dict:
    return {
        "rank": 1,
        "symbol": symbol,
        "name": symbol,
        "asset_type": "stock",
        "is_adr": False,
        "sector": "Technology",
        "theme": "AI",
        "score": 0.9,
        "confidence": 0.85,
        "thesis": f"{symbol} benefits",
        "evidence": [],
        "risks": [],
        "score_breakdown": {},
    }


class _LLMReturning:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.calls.append((prompt, system))
        return self.payload


def _state(ranked_ideas, bull=None, bear=None):
    return {
        "user_profile": {"risk_tolerance": "Moderate"},
        "ranked_ideas": ranked_ideas,
        "bull_case": bull or [{"thesis": "bull", "reasoning": "r", "conviction": 0.8}],
        "bear_case": bear or [{"thesis": "bear", "reasoning": "r", "conviction": 0.4}],
        "config": {"verbose": False},
    }


def test_judge_returns_empty_when_no_ranked_ideas():
    llm = _LLMReturning({"judgments": []})
    result = debate_judge(_state([]), llm)
    assert result == {"debate_judgments": []}
    assert llm.calls == []


def test_judge_returns_empty_when_no_debate_history():
    llm = _LLMReturning({"judgments": []})
    result = debate_judge(_state([_idea("NVDA")], bull=[], bear=[]), llm)
    assert result == {"debate_judgments": []}


def test_judge_parses_valid_judgments():
    llm = _LLMReturning(
        {
            "judgments": [
                {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.18, "rationale": "Bull defended capex"},
                {"symbol": "TSM", "winner": "bear", "conviction_delta": -0.12, "rationale": "Bear exposed capacity risk"},
            ]
        }
    )

    result = debate_judge(_state([_idea("NVDA"), _idea("TSM")]), llm)
    judgments = result["debate_judgments"]
    by_sym = {item["symbol"]: item for item in judgments}

    assert by_sym["NVDA"]["winner"] == "bull"
    assert by_sym["NVDA"]["conviction_delta"] == 0.18
    assert by_sym["TSM"]["conviction_delta"] == -0.12


def test_judge_drops_symbols_not_in_top_ideas():
    llm = _LLMReturning(
        {
            "judgments": [
                {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.1, "rationale": "x"},
                {"symbol": "ABCDE", "winner": "bull", "conviction_delta": 0.2, "rationale": "phantom"},
            ]
        }
    )

    result = debate_judge(_state([_idea("NVDA")]), llm)
    judgments = result["debate_judgments"]

    assert len(judgments) == 1
    assert judgments[0]["symbol"] == "NVDA"


def test_judge_clamps_conviction_delta_to_cap():
    llm = _LLMReturning(
        {
            "judgments": [
                {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.9, "rationale": "x"},
                {"symbol": "TSM", "winner": "bear", "conviction_delta": -1.5, "rationale": "x"},
            ]
        }
    )

    result = debate_judge(_state([_idea("NVDA"), _idea("TSM")]), llm)
    by_sym = {item["symbol"]: item for item in result["debate_judgments"]}

    assert by_sym["NVDA"]["conviction_delta"] == 0.3
    assert by_sym["TSM"]["conviction_delta"] == -0.3


def test_judge_normalises_unknown_winner_to_tie():
    llm = _LLMReturning(
        {"judgments": [{"symbol": "NVDA", "winner": "draw", "conviction_delta": 0.1, "rationale": "x"}]}
    )

    result = debate_judge(_state([_idea("NVDA")]), llm)
    judgment = result["debate_judgments"][0]

    assert judgment["winner"] == "tie"
    assert judgment["conviction_delta"] == 0.0


def test_judge_forces_zero_delta_when_winner_is_tie():
    llm = _LLMReturning(
        {"judgments": [{"symbol": "NVDA", "winner": "tie", "conviction_delta": 0.2, "rationale": "x"}]}
    )

    result = debate_judge(_state([_idea("NVDA")]), llm)
    judgment = result["debate_judgments"][0]

    assert judgment["winner"] == "tie"
    assert judgment["conviction_delta"] == 0.0


def test_judge_dedupes_same_symbol_keeps_first():
    llm = _LLMReturning(
        {
            "judgments": [
                {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.1, "rationale": "first"},
                {"symbol": "NVDA", "winner": "bear", "conviction_delta": -0.1, "rationale": "second"},
            ]
        }
    )

    result = debate_judge(_state([_idea("NVDA")]), llm)
    assert len(result["debate_judgments"]) == 1
    assert result["debate_judgments"][0]["winner"] == "bull"
    assert result["debate_judgments"][0]["rationale"] == "first"


def test_judge_returns_empty_on_llm_error():
    llm = _LLMReturning({"error": "Invalid JSON response", "raw": "garbled"})
    result = debate_judge(_state([_idea("NVDA")]), llm)
    assert result == {"debate_judgments": []}
