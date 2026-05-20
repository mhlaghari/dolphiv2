"""Tests for the multi-round bull/bear debate node."""

from __future__ import annotations

from dolphi.agents.debate import debate


class _ScriptedLLM:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []
        self._bull_counter = 0
        self._bear_counter = 0

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.calls.append((prompt, system))
        sys_lower = (system or "").lower()
        if "bullish equity researcher engaged in a structured debate" in sys_lower:
            self._bull_counter += 1
            return {
                "reasoning": f"bull rebuttal {self._bull_counter}",
                "thesis": f"bull thesis v{self._bull_counter + 1}",
                "conviction": 0.7 + 0.05 * self._bull_counter,
            }
        if "bearish equity researcher engaged in a structured debate" in sys_lower:
            self._bear_counter += 1
            return {
                "reasoning": f"bear rebuttal {self._bear_counter}",
                "thesis": f"bear thesis v{self._bear_counter + 1}",
                "conviction": 0.4 + 0.05 * self._bear_counter,
            }
        return {"error": "Unexpected system prompt"}

    @property
    def bull_calls(self):
        return [c for c in self.calls if "bullish equity researcher engaged in a structured debate" in (c[1] or "").lower()]

    @property
    def bear_calls(self):
        return [c for c in self.calls if "bearish equity researcher engaged in a structured debate" in (c[1] or "").lower()]


def _state(rounds: int = 2):
    return {
        "user_profile": {"risk_tolerance": "Moderate", "goal": "growth"},
        "bull_case": [{"reasoning": "initial bull", "thesis": "bull thesis v1", "conviction": 0.7}],
        "bear_case": [{"reasoning": "initial bear", "thesis": "bear thesis v1", "conviction": 0.4}],
        "config": {"verbose": False, "debate_rounds": rounds},
    }


def test_debate_runs_configured_number_of_rounds():
    llm = _ScriptedLLM()
    result = debate(_state(rounds=2), llm)

    assert len(result["bull_case"]) == 2
    assert len(result["bear_case"]) == 2
    assert len(llm.bull_calls) == 2
    assert len(llm.bear_calls) == 2


def test_debate_returns_only_new_turns_so_langgraph_appends():
    llm = _ScriptedLLM()
    state = _state(rounds=1)
    result = debate(state, llm)

    assert len(result["bull_case"]) == 1
    assert len(result["bear_case"]) == 1
    assert state["bull_case"][0]["thesis"] == "bull thesis v1"


def test_debate_bull_rebuttal_sees_latest_bear_argument():
    llm = _ScriptedLLM()
    state = _state(rounds=2)
    debate(state, llm)

    first_bull_prompt = llm.bull_calls[0][0]
    second_bull_prompt = llm.bull_calls[1][0]
    assert "bear thesis v1" in first_bull_prompt
    assert "bear thesis v2" in second_bull_prompt


def test_debate_bear_rebuttal_sees_latest_bull_rebuttal():
    llm = _ScriptedLLM()
    state = _state(rounds=2)
    debate(state, llm)

    first_bear_prompt = llm.bear_calls[0][0]
    assert "bull thesis v2" in first_bear_prompt


def test_debate_skips_when_no_opening_cases():
    llm = _ScriptedLLM()
    state = _state(rounds=2)
    state["bull_case"] = []
    state["bear_case"] = []

    result = debate(state, llm)
    assert result == {}
    assert llm.calls == []


def test_debate_zero_rounds_is_noop():
    llm = _ScriptedLLM()
    result = debate(_state(rounds=0), llm)
    assert result == {}
    assert llm.calls == []


def test_debate_clamps_conviction_to_unit_interval():
    class _LLMOutOfRange:
        def generate_json(self, prompt, system=None, temperature=0.3):
            return {"reasoning": "x", "thesis": "y", "conviction": 5.0}

    state = _state(rounds=1)
    result = debate(state, _LLMOutOfRange())

    assert result["bull_case"][0]["conviction"] == 1.0
    assert result["bear_case"][0]["conviction"] == 1.0


def test_debate_falls_back_when_llm_errors():
    class _LLMErr:
        def generate_json(self, prompt, system=None, temperature=0.3):
            return {"error": "boom"}

    state = _state(rounds=1)
    result = debate(state, _LLMErr())

    assert result["bull_case"][0]["thesis"] == "bull thesis v1"
    assert result["bear_case"][0]["thesis"] == "bear thesis v1"
