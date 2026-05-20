from dolphi.agents.portfolio_manager import portfolio_manager
from dolphi.agents.risk_aggressive import risk_aggressive
from dolphi.agents.risk_conservative import risk_conservative
from dolphi.cli import _print_portfolio


class FakeLLM:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.prompts = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return {
            "reasoning": "risk reviewed",
            "fits_profile": True,
            "adjusted_score": 0.75,
        }


def base_state():
    return {
        "user_profile": {
            "total_savings": 100000,
            "monthly_salary": 10000,
            "currency": "USD",
            "goal": "growth",
            "risk_tolerance": "Moderate",
            "preferred_asset_classes": ["stocks", "etfs"],
        },
        "market_data": {
            "spx_level": 5000,
            "vix_level": 15,
            "key_sectors": {},
            "news_headlines": [],
        },
        "technical_analysis": {"reasoning": "tech strong", "score": 0.7, "details": {}},
        "fundamental_analysis": {"reasoning": "fundamentals strong", "score": 0.5, "details": {}},
        "sentiment_analysis": {"reasoning": "sentiment positive", "score": 0.4, "details": {}},
        "bull_case": [
            {"reasoning": "old bull", "thesis": "old bull thesis", "conviction": 0.5},
            {"reasoning": "new bull", "thesis": "new bull thesis", "conviction": 0.8},
        ],
        "bear_case": [
            {"reasoning": "old bear", "thesis": "old bear thesis", "conviction": 0.4},
            {"reasoning": "new bear", "thesis": "new bear thesis", "conviction": 0.6},
        ],
        "risk_aggressive_eval": [],
        "risk_conservative_eval": [],
        "portfolio_recommendation": {"allocations": [], "notes": ""},
        "memory_hits": [],
        "config": {"verbose": False},
    }


def test_risk_agents_accept_bull_and_bear_case_lists():
    state = base_state()
    llm = FakeLLM()

    aggressive = risk_aggressive(state, llm)
    conservative = risk_conservative(state, llm)

    assert aggressive["risk_aggressive_eval"][0]["adjusted_score"] == 0.75
    assert conservative["risk_conservative_eval"][0]["adjusted_score"] == 0.75
    assert "new bull thesis" in llm.prompts[0]
    assert "new bear thesis" in llm.prompts[1]


def test_portfolio_manager_synthesizes_all_research_items():
    state = base_state()
    state["risk_aggressive_eval"] = [
        {"reasoning": "aggressive old", "fits_profile": True, "adjusted_score": 0.5},
        {"reasoning": "aggressive current", "fits_profile": True, "adjusted_score": 0.9},
    ]
    state["risk_conservative_eval"] = [
        {"reasoning": "conservative old", "fits_profile": True, "adjusted_score": 0.6},
        {"reasoning": "conservative current", "fits_profile": False, "adjusted_score": 0.2},
    ]
    llm = FakeLLM([
        {
            "allocations": [
                {"symbol": "NVDA", "allocation_pct": 50, "rationale": "AI leader"},
                {"symbol": "BND", "allocation_pct": 50, "rationale": "Risk ballast"},
            ],
            "notes": "balanced allocation",
        }
    ])

    result = portfolio_manager(state, llm)

    prompt = llm.prompts[0]
    assert "old bull thesis" in prompt
    assert "new bull thesis" in prompt
    assert "old bear thesis" in prompt
    assert "new bear thesis" in prompt
    assert "aggressive current" in prompt
    assert result["portfolio_recommendation"]["allocations"][0]["symbol"] == "NVDA"


def test_portfolio_manager_ignores_extra_allocation_keys():
    state = base_state()
    llm = FakeLLM([
        {
            "allocations": [
                {"symbol": "NVDA", "allocation_pct": 100, "rationale": "AI leader", "extra": "ignored"},
            ],
            "notes": "extra keys should not crash",
        }
    ])

    result = portfolio_manager(state, llm)

    assert result["portfolio_recommendation"]["allocations"] == [
        {"symbol": "NVDA", "allocation_pct": 100, "rationale": "AI leader"}
    ]


def test_print_portfolio_uses_profile_for_risk_and_goal(monkeypatch):
    lines = []
    monkeypatch.setattr("click.echo", lambda value="": lines.append(str(value)))
    rec = {
        "allocations": [
            {"symbol": "NVDA", "allocation_pct": 60, "rationale": "AI leader"},
            {"symbol": "BND", "allocation_pct": 40, "rationale": "Risk ballast"},
        ],
        "notes": "example",
    }
    profile = {"risk_tolerance": "Moderate", "goal": "growth"}

    _print_portfolio(rec, profile)

    assert any("Risk: Moderate" in line and "Goal: growth" in line for line in lines)


def test_portfolio_manager_notes_do_not_reference_unallocated_symbols():
    state = base_state()
    state["ranked_ideas"] = [
        {
            "rank": 1,
            "symbol": "NVDA",
            "name": "NVIDIA",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI infrastructure",
            "score": 0.9,
            "confidence": 0.9,
            "thesis": "AI accelerator demand",
            "evidence": ["source-backed AI accelerator demand"],
            "risks": ["valuation"],
            "score_breakdown": {},
        }
    ]
    llm = FakeLLM([
        {
            "allocations": [{"symbol": "NVDA", "allocation_pct": 100, "rationale": "AI leader"}],
            "notes": "NVDA is attractive. SMH offers broad semiconductor exposure.",
        }
    ])

    result = portfolio_manager(state, llm)

    notes = result["portfolio_recommendation"]["notes"]
    assert "NVDA" in notes
    assert "SMH" not in notes
