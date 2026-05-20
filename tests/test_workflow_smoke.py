from dolphi.data.base import DataFetcher
from dolphi.graph.workflow import build_discovery_state, build_portfolio_graph
from dolphi.models import AgentState


class FakeLLM:
    def generate_json(self, prompt, system=None, temperature=0.3):
        system_text = (system or "").lower()
        if "research editor" in system_text:
            return {
                "assumptions": [
                    {"text": "AI capex grows >30% YoY"},
                    {"text": "Foundry capacity not the bottleneck"},
                    {"text": "Pricing power is durable"},
                ]
            }
        if "falsification-first" in system_text:
            return {
                "falsifiers": [
                    {
                        "failure_mode": "Hyperscaler capex pause",
                        "probability": 0.3,
                        "leading_indicator": "Hyperscaler quarterly guides",
                        "breaks_assumption": "AI capex grows >30% YoY",
                        "horizon": "60 days",
                    },
                    {
                        "failure_mode": "Custom silicon takes share",
                        "probability": 0.25,
                        "leading_indicator": "MTIA volume disclosures",
                        "breaks_assumption": "Pricing power is durable",
                        "horizon": "6 months",
                    },
                    {
                        "failure_mode": "Export policy widens",
                        "probability": 0.2,
                        "leading_indicator": "BIS announcements",
                        "breaks_assumption": "Foundry capacity not the bottleneck",
                        "horizon": "12 months",
                    },
                ]
            }
        if "bullish equity researcher engaged in a structured debate" in system_text:
            return {"reasoning": "bull rebuttal", "thesis": "AI demand still durable", "conviction": 0.82}
        if "bearish equity researcher engaged in a structured debate" in system_text:
            return {"reasoning": "bear rebuttal", "thesis": "valuations still stretched", "conviction": 0.45}
        if "debate judge" in system_text:
            return {
                "judgments": [
                    {
                        "symbol": "NVDA",
                        "winner": "bull",
                        "conviction_delta": 0.15,
                        "rationale": "Bull side defended AI capex assumption convincingly.",
                    },
                    {
                        "symbol": "TSM",
                        "winner": "tie",
                        "conviction_delta": 0.0,
                        "rationale": "Both sides made fair points on foundry capacity.",
                    },
                ]
            }
        if "bullish" in system_text:
            return {"reasoning": "bullish", "thesis": "AI infrastructure demand", "conviction": 0.8}
        if "bearish" in system_text:
            return {"reasoning": "bearish", "thesis": "valuation risk", "conviction": 0.4}
        if "risk assessment" in system_text:
            return {"reasoning": "risk reviewed", "fits_profile": True, "adjusted_score": 0.7}
        if "portfolio manager" in system_text:
            return {
                "allocations": [
                    {"symbol": "NVDA", "allocation_pct": 40, "rationale": "AI infrastructure"},
                    {"symbol": "TSM", "allocation_pct": 30, "rationale": "Foundry beneficiary"},
                    {"symbol": "BND", "allocation_pct": 30, "rationale": "Risk ballast"},
                ],
                "notes": "mock recommendation",
            }
        if "technical analyst" in system_text or "fundamental analyst" in system_text or "sentiment analyst" in system_text:
            return {
                "per_ticker": {},
                "overall_reasoning": "neutral",
                "overall_score": 0.0,
            }
        return {"reasoning": "analysis", "score": 0.5, "details": {}}


def test_discovery_state_feeds_portfolio_graph_in_mock_mode():
    data = DataFetcher(cache=None, mock=True)
    profile = {
        "total_savings": 100000,
        "monthly_salary": 10000,
        "currency": "USD",
        "goal": "growth",
        "risk_tolerance": "Moderate",
        "preferred_asset_classes": ["stocks", "etfs"],
    }
    discovery = build_discovery_state(profile, data, top_k=3, seed_symbols=["NVDA"])

    initial_state: AgentState = {
        "user_profile": profile,
        "market_data": {
            "spx_level": 5300,
            "vix_level": 14,
            "key_sectors": data.get_sector_performance(),
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
        "config": {"verbose": False},
        **discovery,
    }

    final_state = build_portfolio_graph(FakeLLM(), data).invoke(initial_state)

    assert final_state["candidate_symbols"]
    assert final_state["portfolio_recommendation"]["allocations"]
    assert final_state["bull_case"]
    assert final_state["risk_aggressive_eval"]
    findings = final_state["pre_mortem_findings"]
    assert findings, "pre-mortem agent must produce at least one finding"
    nvda_finding = next((item for item in findings if item["symbol"] == "NVDA"), None)
    assert nvda_finding is not None
    assert len(nvda_finding["falsifiers"]) == 3
    assert 0 < nvda_finding["overall_fragility"] <= 1
    for f in nvda_finding["falsifiers"]:
        assert f.get("horizon")
        assert f.get("breaks_assumption")

    assumptions = final_state.get("bull_assumptions") or []
    assert assumptions, "expected bull-assumption extraction to populate state"
    allowed = {a["text"] for a in assumptions}
    for f in nvda_finding["falsifiers"]:
        assert f["breaks_assumption"] in allowed
