"""Tests for the Pre-Mortem agent — Phase 1 contract.

Contract (Phase 1):
- Pre-Mortem makes one LLM call to extract bull assumptions (system prompt
  contains "research editor") IFF a bull_case is present.
- Pre-Mortem then makes one LLM call per ranked idea (system prompt
  contains "falsification-first"), each producing exactly 3 falsifiers.
- Each falsifier is required to cite a known assumption when one is
  available — the agent post-processes to coerce free-text into a
  matched assumption.
- The agent must NOT pass the bull *thesis* into the per-symbol prompts,
  only the named *assumptions*.
"""

from __future__ import annotations

from dolphi.agents.pre_mortem import pre_mortem


def _idea(symbol: str, sector: str = "Technology") -> dict:
    return {
        "rank": 1,
        "symbol": symbol,
        "name": symbol,
        "asset_type": "stock",
        "is_adr": False,
        "sector": sector,
        "theme": "AI infrastructure",
        "score": 0.9,
        "confidence": 0.85,
        "thesis": f"{symbol} benefits from AI capex",
        "evidence": ["AI infrastructure demand"],
        "risks": ["valuation"],
        "score_breakdown": {},
    }


class _ScriptedLLM:
    """LLM stub that dispatches by system prompt and records every call."""

    def __init__(
        self,
        assumption_payload: dict | None = None,
        falsifier_payload: dict | None = None,
    ):
        self.assumption_payload = assumption_payload or {"assumptions": []}
        self.falsifier_payload = falsifier_payload or {"falsifiers": []}
        self.calls: list[tuple[str, str | None]] = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.calls.append((prompt, system))
        sys_lower = (system or "").lower()
        if "research editor" in sys_lower:
            return self.assumption_payload
        if "falsification-first" in sys_lower:
            return self.falsifier_payload
        return {"error": "Unrecognised system prompt"}

    @property
    def assumption_calls(self) -> list[tuple[str, str | None]]:
        return [call for call in self.calls if "research editor" in (call[1] or "").lower()]

    @property
    def per_symbol_calls(self) -> list[tuple[str, str | None]]:
        return [call for call in self.calls if "falsification-first" in (call[1] or "").lower()]


def _state(ranked_ideas: list[dict], bull_case: list[dict] | None = None) -> dict:
    return {
        "user_profile": {"risk_tolerance": "Moderate", "goal": "growth", "preferred_asset_classes": ["stocks"]},
        "ranked_ideas": ranked_ideas,
        "bull_case": bull_case or [],
        "config": {"verbose": False},
    }


def test_pre_mortem_returns_empty_when_no_ranked_ideas():
    llm = _ScriptedLLM()

    result = pre_mortem(_state([]), llm)

    assert result == {"pre_mortem_findings": [], "bull_assumptions": []}
    assert llm.calls == []


def test_pre_mortem_fans_out_one_call_per_symbol():
    llm = _ScriptedLLM(
        assumption_payload={"assumptions": [{"text": "AI capex grows >30% YoY"}]},
        falsifier_payload={
            "falsifiers": [
                {
                    "failure_mode": "Hyperscaler capex pause",
                    "probability": 0.25,
                    "leading_indicator": "Quarterly capex guides",
                    "breaks_assumption": "AI capex grows >30% YoY",
                    "horizon": "60 days",
                },
                {
                    "failure_mode": "Custom silicon takes share",
                    "probability": 0.20,
                    "leading_indicator": "MTIA disclosures",
                    "breaks_assumption": "AI capex grows >30% YoY",
                    "horizon": "6 months",
                },
                {
                    "failure_mode": "Policy headwind",
                    "probability": 0.15,
                    "leading_indicator": "BIS announcements",
                    "breaks_assumption": "AI capex grows >30% YoY",
                    "horizon": "12 months",
                },
            ]
        },
    )

    bull = [{"thesis": "AI demand will dominate", "reasoning": "capex up", "conviction": 0.9}]
    result = pre_mortem(_state([_idea("NVDA"), _idea("TSM")], bull_case=bull), llm)

    findings = result["pre_mortem_findings"]
    assert {item["symbol"] for item in findings} == {"NVDA", "TSM"}
    assert len(llm.assumption_calls) == 1
    assert len(llm.per_symbol_calls) == 2
    for finding in findings:
        assert len(finding["falsifiers"]) == 3
        assert all(f["horizon"] for f in finding["falsifiers"])


def test_pre_mortem_skips_assumption_call_when_no_bull_case():
    llm = _ScriptedLLM(
        falsifier_payload={
            "falsifiers": [
                {
                    "failure_mode": "X",
                    "probability": 0.1,
                    "leading_indicator": "y",
                    "breaks_assumption": "anything",
                    "horizon": "30 days",
                }
            ]
        }
    )

    result = pre_mortem(_state([_idea("NVDA")], bull_case=[]), llm)

    assert result["bull_assumptions"] == []
    assert llm.assumption_calls == []
    assert len(llm.per_symbol_calls) == 1
    assert result["pre_mortem_findings"][0]["symbol"] == "NVDA"


def test_pre_mortem_extracts_bull_assumptions():
    llm = _ScriptedLLM(
        assumption_payload={
            "assumptions": [
                {"text": "AI capex grows >30% YoY"},
                "Pricing power is durable",
                {"text": ""},
                {"text": "Foundry capacity is not the bottleneck"},
            ]
        },
        falsifier_payload={"falsifiers": []},
    )

    bull = [{"thesis": "AI dominates", "reasoning": "demand strong", "conviction": 0.9}]
    result = pre_mortem(_state([_idea("NVDA")], bull_case=bull), llm)

    texts = [a["text"] for a in result["bull_assumptions"]]
    assert "AI capex grows >30% YoY" in texts
    assert "Pricing power is durable" in texts
    assert "Foundry capacity is not the bottleneck" in texts
    assert "" not in texts


def test_pre_mortem_coerces_free_text_to_matched_assumption():
    """If the LLM returns a breaks_assumption that doesn't verbatim match,
    we coerce to a substring-matched assumption to keep the link valid."""
    llm = _ScriptedLLM(
        assumption_payload={"assumptions": [{"text": "AI capex grows >30% YoY through 2027"}]},
        falsifier_payload={
            "falsifiers": [
                {
                    "failure_mode": "Capex flatlines",
                    "probability": 0.3,
                    "leading_indicator": "Big tech guides",
                    "breaks_assumption": "AI capex",
                    "horizon": "90 days",
                }
            ]
        },
    )

    bull = [{"thesis": "x", "reasoning": "y", "conviction": 0.8}]
    result = pre_mortem(_state([_idea("NVDA")], bull_case=bull), llm)

    falsifier = result["pre_mortem_findings"][0]["falsifiers"][0]
    assert falsifier["breaks_assumption"] == "AI capex grows >30% YoY through 2027"


def test_pre_mortem_falls_back_to_first_assumption_when_unmatched():
    llm = _ScriptedLLM(
        assumption_payload={"assumptions": [{"text": "Assumption A"}, {"text": "Assumption B"}]},
        falsifier_payload={
            "falsifiers": [
                {
                    "failure_mode": "Some failure",
                    "probability": 0.4,
                    "leading_indicator": "z",
                    "breaks_assumption": "totally unrelated text",
                    "horizon": "120 days",
                }
            ]
        },
    )

    bull = [{"thesis": "x", "reasoning": "y", "conviction": 0.8}]
    result = pre_mortem(_state([_idea("NVDA")], bull_case=bull), llm)

    falsifier = result["pre_mortem_findings"][0]["falsifiers"][0]
    assert falsifier["breaks_assumption"] == "Assumption A"


def test_pre_mortem_clamps_probability_to_unit_interval():
    llm = _ScriptedLLM(
        falsifier_payload={
            "falsifiers": [
                {
                    "failure_mode": "Outlier high",
                    "probability": 4.0,
                    "leading_indicator": "x",
                    "breaks_assumption": "y",
                    "horizon": "60 days",
                },
                {
                    "failure_mode": "Outlier low",
                    "probability": -2.0,
                    "leading_indicator": "x",
                    "breaks_assumption": "y",
                    "horizon": "60 days",
                },
            ]
        }
    )

    result = pre_mortem(_state([_idea("NVDA")]), llm)
    falsifiers = result["pre_mortem_findings"][0]["falsifiers"]
    assert falsifiers[0]["probability"] == 1.0
    assert falsifiers[1]["probability"] == 0.0


def test_pre_mortem_falls_back_gracefully_on_invalid_llm_output():
    llm = _ScriptedLLM(
        falsifier_payload={"error": "Invalid JSON response", "raw": "nonsense"},
    )

    result = pre_mortem(_state([_idea("NVDA"), _idea("TSM")]), llm)

    findings = result["pre_mortem_findings"]
    assert {item["symbol"] for item in findings} == {"NVDA", "TSM"}
    assert all(item["falsifiers"] == [] for item in findings)
    assert all(item["overall_fragility"] == 0.0 for item in findings)


def test_pre_mortem_per_symbol_prompt_does_not_leak_bull_thesis():
    """The bull *thesis* must not leak into per-symbol prompts — only
    the extracted *assumptions* may flow through."""
    llm = _ScriptedLLM(
        assumption_payload={"assumptions": [{"text": "AI demand is durable"}]},
        falsifier_payload={"falsifiers": []},
    )

    state = _state(
        [_idea("NVDA")],
        bull_case=[{"thesis": "AI demand is unstoppable forever", "reasoning": "secret sauce", "conviction": 0.95}],
    )
    pre_mortem(state, llm)

    per_symbol_prompts = [prompt for prompt, _ in llm.per_symbol_calls]
    for prompt in per_symbol_prompts:
        assert "unstoppable forever" not in prompt
        assert "secret sauce" not in prompt
        assert "AI demand is durable" in prompt


def test_pre_mortem_prompt_provides_assumption_block_when_no_assumptions():
    llm = _ScriptedLLM(
        assumption_payload={"assumptions": []},
        falsifier_payload={"falsifiers": []},
    )

    state = _state(
        [_idea("NVDA")],
        bull_case=[{"thesis": "x", "reasoning": "y", "conviction": 0.5}],
    )
    pre_mortem(state, llm)

    prompt, _ = llm.per_symbol_calls[0]
    assert "no named assumptions" in prompt.lower()
