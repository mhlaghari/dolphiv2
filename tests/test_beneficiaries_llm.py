"""Tests for the LLM-driven beneficiary mapper.

Contract:
- When llm is None, keyword fallback is used (back-compat).
- When llm is provided, exactly one LLM call is issued per narrative.
- LLM-proposed symbols are universe-validated; unknown tickers are dropped.
- LLM-proposed symbols are profile-filtered; e.g. ETFs are dropped when
  user excluded ETFs from preferred_asset_classes.
- If the LLM errors or returns nothing usable, we fall back to the
  keyword path *for that narrative only* (graceful per-narrative degradation).
- Confidence is clamped to [0, 1] and scaled by narrative confidence.
"""

from __future__ import annotations

from dolphi.models import MarketNarrative
from dolphi.research.beneficiaries import map_beneficiaries
from dolphi.universe.symbols import default_universe


class _LLMScripted:
    def __init__(self, payloads):
        # payloads can be a single dict (returned for every call) or a list
        # of dicts (returned in order).
        if isinstance(payloads, dict):
            self._sequence = None
            self._single = payloads
        else:
            self._sequence = list(payloads)
            self._single = None
        self.calls: list[tuple[str, str | None]] = []

    def generate_json(self, prompt, system=None, temperature=0.3):
        self.calls.append((prompt, system))
        if self._sequence is not None:
            return self._sequence.pop(0)
        return dict(self._single)


def _narrative(title: str, thesis: str, keywords: list[str] | None = None) -> MarketNarrative:
    return MarketNarrative(
        title=title,
        thesis=thesis,
        evidence=[f"Evidence supporting {title}."],
        source_count=2,
        source_diversity=0.5,
        freshness=0.7,
        confidence=0.7,
        related_sectors=["Technology"],
        keywords=keywords or ["ai", "semiconductor", "chip"],
        source_urls=["https://example.com/article"],
    )


def test_keyword_fallback_used_when_no_llm():
    narrative = _narrative("AI Infrastructure", "AI capex remains strong.")
    universe = default_universe()
    clusters = map_beneficiaries([narrative], universe, profile={}, llm=None)

    assert len(clusters) == 1
    related = clusters[0]["related_symbols"]
    assert {item["symbol"] for item in related} & {"NVDA", "TSM", "ASML"}


def test_llm_path_uses_proposed_symbols():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {"symbol": "NVDA", "relationship": "AI compute monopoly", "evidence": "Dominant accelerator", "confidence": 0.9},
                {"symbol": "AVGO", "relationship": "custom AI silicon", "evidence": "Hyperscaler ASIC supplier", "confidence": 0.8},
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "AI capex stays elevated.")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    assert len(clusters) == 1
    related = clusters[0]["related_symbols"]
    assert {item["symbol"] for item in related} == {"NVDA", "AVGO"}
    assert any(item["relationship"] == "custom AI silicon" for item in related)
    assert all(0 <= item["confidence"] <= 1 for item in related)


def test_llm_path_drops_unknown_symbols():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {"symbol": "NVDA", "relationship": "real", "evidence": "real", "confidence": 0.9},
                {"symbol": "FAKE9", "relationship": "fake", "evidence": "fake", "confidence": 0.9},
                {"symbol": "ZZZZ", "relationship": "fake", "evidence": "fake", "confidence": 0.9},
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks", "etfs"]},
        llm=llm,
    )

    related = clusters[0]["related_symbols"]
    assert {item["symbol"] for item in related} == {"NVDA"}


def test_llm_path_respects_profile_asset_filter():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {"symbol": "NVDA", "relationship": "stock", "evidence": "x", "confidence": 0.9},
                {"symbol": "SMH", "relationship": "ETF proxy", "evidence": "x", "confidence": 0.85},
                {"symbol": "SOXX", "relationship": "ETF proxy", "evidence": "x", "confidence": 0.8},
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    related = clusters[0]["related_symbols"]
    assert {item["symbol"] for item in related} == {"NVDA"}


def test_llm_path_dedupes_repeated_symbols():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {"symbol": "NVDA", "relationship": "leader", "evidence": "x", "confidence": 0.9},
                {"symbol": "nvda", "relationship": "duplicate", "evidence": "y", "confidence": 0.7},
                {"symbol": " NVDA ", "relationship": "duplicate2", "evidence": "z", "confidence": 0.5},
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    related = clusters[0]["related_symbols"]
    assert [item["symbol"] for item in related] == ["NVDA"]
    assert related[0]["relationship"] == "leader"


def test_llm_path_falls_back_to_keyword_on_llm_error():
    llm = _LLMScripted({"error": "Invalid JSON response", "raw": "garbled"})

    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks", "etfs"]},
        llm=llm,
    )

    assert len(clusters) == 1
    related = clusters[0]["related_symbols"]
    assert {"NVDA", "TSM"} & {item["symbol"] for item in related}


def test_llm_path_one_call_per_narrative():
    llm = _LLMScripted(
        [
            {"beneficiaries": [{"symbol": "NVDA", "relationship": "AI", "evidence": "x", "confidence": 0.9}]},
            {"beneficiaries": [{"symbol": "CEG", "relationship": "power", "evidence": "y", "confidence": 0.85}]},
        ]
    )

    clusters = map_beneficiaries(
        [
            _narrative("AI Infrastructure", "AI thesis"),
            _narrative("Data Center Power", "Power thesis", keywords=["power", "grid"]),
        ],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    assert len(llm.calls) == 2
    assert len(clusters) == 2
    assert {clusters[0]["related_symbols"][0]["symbol"]} == {"NVDA"}
    assert {clusters[1]["related_symbols"][0]["symbol"]} == {"CEG"}


def test_llm_path_clamps_confidence():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {"symbol": "NVDA", "relationship": "x", "evidence": "x", "confidence": 4.0},
                {"symbol": "AMD", "relationship": "x", "evidence": "x", "confidence": -1.0},
                {"symbol": "TSM", "relationship": "x", "evidence": "x", "confidence": "not a number"},
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    related = clusters[0]["related_symbols"]
    by_symbol = {item["symbol"]: item for item in related}
    assert 0.0 <= by_symbol["NVDA"]["confidence"] <= 1.0
    assert 0.0 <= by_symbol["AMD"]["confidence"] <= 1.0
    assert 0.0 <= by_symbol["TSM"]["confidence"] <= 1.0
    assert by_symbol["AMD"]["confidence"] == 0.0


def test_llm_path_caps_max_relations():
    big_payload = {
        "beneficiaries": [
            {"symbol": sym, "relationship": "x", "evidence": "x", "confidence": 0.5}
            for sym in ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "SMH", "SOXX", "AAPL", "MSFT"]
        ]
    }
    llm = _LLMScripted(big_payload)

    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks", "etfs"]},
        llm=llm,
    )

    assert len(clusters[0]["related_symbols"]) <= 8


def test_llm_path_skips_narrative_when_all_proposals_invalid():
    llm = _LLMScripted({"beneficiaries": [{"symbol": "ZZZZ", "relationship": "fake", "evidence": "fake", "confidence": 0.9}]})

    clusters = map_beneficiaries(
        [_narrative("Empty", "thesis", keywords=["unrelated_keyword"])],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    assert clusters == []


def test_llm_path_evidence_includes_relationship():
    llm = _LLMScripted(
        {
            "beneficiaries": [
                {
                    "symbol": "NVDA",
                    "relationship": "AI accelerator pricing power",
                    "evidence": "Dominant CUDA moat and DGX deployments",
                    "confidence": 0.9,
                }
            ]
        }
    )
    clusters = map_beneficiaries(
        [_narrative("AI", "thesis")],
        default_universe(),
        profile={"preferred_asset_classes": ["stocks"]},
        llm=llm,
    )

    evidence = clusters[0]["related_symbols"][0]["evidence"]
    assert "AI accelerator pricing power" in evidence
    assert "Dominant CUDA" in evidence
