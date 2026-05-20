from __future__ import annotations

from dolphi.agents.fundamental_analyst import fundamental_analyst
from dolphi.agents.sentiment_analyst import sentiment_analyst
from dolphi.agents.technical_analyst import technical_analyst
from dolphi.data.base import DataFetcher


class _LLMScripted:
    def __init__(self, payload):
        self._payload = payload
        self.prompts: list[tuple[str, str | None]] = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.prompts.append((prompt, system))
        return self._payload


def _state_with_candidates(symbols):
    return {
        "user_profile": {
            "total_savings": 100_000,
            "monthly_salary": 10_000,
            "currency": "USD",
            "goal": "growth",
            "risk_tolerance": "Moderate",
            "preferred_asset_classes": ["stocks", "etfs"],
        },
        "candidate_symbols": symbols,
        "config": {"verbose": False},
    }


def test_technical_analyst_emits_per_ticker_dict_and_overall_summary():
    payload = {
        "per_ticker": {
            "NVDA": {"reasoning": "trend up, above 50DMA", "score": 0.7, "details": {"trend": "up"}},
            "TSM": {"reasoning": "consolidating at resistance", "score": 0.3, "details": {"trend": "flat"}},
        },
        "overall_reasoning": "Semis broadly constructive",
        "overall_score": 0.5,
    }
    llm = _LLMScripted(payload)
    data = DataFetcher(cache=None, mock=True)

    result = technical_analyst(_state_with_candidates(["NVDA", "TSM"]), llm, data)

    per_ticker = result["per_ticker_technical"]
    assert set(per_ticker.keys()) == {"NVDA", "TSM"}
    assert per_ticker["NVDA"]["score"] == 0.7
    assert per_ticker["TSM"]["reasoning"].startswith("consolidating")
    overall = result["technical_analysis"]
    assert overall["reasoning"] == "Semis broadly constructive"
    assert overall["score"] == 0.5
    assert overall["details"]["per_ticker_count"] == 2


def test_technical_analyst_handles_missing_per_ticker_entries():
    payload = {
        "per_ticker": {"NVDA": {"reasoning": "ok", "score": 0.4, "details": {}}},
        "overall_reasoning": "mixed",
        "overall_score": 0.0,
    }
    llm = _LLMScripted(payload)
    data = DataFetcher(cache=None, mock=True)

    result = technical_analyst(_state_with_candidates(["NVDA", "TSM"]), llm, data)

    assert result["per_ticker_technical"]["TSM"]["score"] == 0.0
    assert result["per_ticker_technical"]["TSM"]["reasoning"] == ""


def test_fundamental_analyst_emits_per_ticker_breakdown():
    payload = {
        "per_ticker": {
            "NVDA": {"reasoning": "rich valuation, growing", "score": 0.2, "details": {"pe": "high"}},
            "BND": {"reasoning": "yield improving", "score": 0.1, "details": {"yield": "+1%"}},
        },
        "overall_reasoning": "cohort mixed",
        "overall_score": 0.15,
    }
    llm = _LLMScripted(payload)
    data = DataFetcher(cache=None, mock=True)

    result = fundamental_analyst(_state_with_candidates(["NVDA", "BND"]), llm, data)

    assert result["per_ticker_fundamental"]["NVDA"]["details"]["pe"] == "high"


def test_sentiment_analyst_per_ticker_falls_back_to_neutral_when_llm_errors():
    payload = {"error": "Invalid JSON response", "raw": ""}
    llm = _LLMScripted(payload)
    data = DataFetcher(cache=None, mock=True)

    result = sentiment_analyst(_state_with_candidates(["NVDA", "TSM"]), llm, data)

    assert set(result["per_ticker_sentiment"].keys()) == {"NVDA", "TSM"}
    assert all(entry["score"] == 0.0 for entry in result["per_ticker_sentiment"].values())
    assert result["sentiment_analysis"]["score"] == 0.0


def test_technical_analyst_clamps_per_ticker_scores_to_unit_interval():
    payload = {
        "per_ticker": {
            "NVDA": {"reasoning": "extreme", "score": 5.0, "details": {}},
            "TSM": {"reasoning": "extreme low", "score": -3.0, "details": {}},
        },
        "overall_reasoning": "extreme reads clamped",
        "overall_score": 0.0,
    }
    llm = _LLMScripted(payload)
    data = DataFetcher(cache=None, mock=True)

    result = technical_analyst(_state_with_candidates(["NVDA", "TSM"]), llm, data)

    assert result["per_ticker_technical"]["NVDA"]["score"] == 1.0
    assert result["per_ticker_technical"]["TSM"]["score"] == -1.0
