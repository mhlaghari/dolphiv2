from dolphi.memory.decision_log import append_decision_log


def test_append_decision_log_records_discovery_context(tmp_path):
    path = tmp_path / "decisions.md"
    profile = {"risk_tolerance": "Moderate", "goal": "growth"}
    ranked_ideas = [
        {"rank": 1, "symbol": "NVDA", "theme": "AI infrastructure", "score": 0.9, "confidence": 0.8},
    ]
    themes = [
        {
            "seed_symbol": "AI Infrastructure",
            "theme": "AI infrastructure",
            "thesis": "AI demand expands the supply chain",
            "related_symbols": [
                {
                    "symbol": "NVDA",
                    "relationship": "AI accelerator leader",
                    "evidence": "Source A: AI accelerator demand is rising",
                    "confidence": 0.8,
                }
            ],
            "source_urls": ["https://example.test/source-a"],
        },
    ]
    rec = {"allocations": [{"symbol": "NVDA", "allocation_pct": 50}], "notes": "narrative"}

    append_decision_log(path, profile, ranked_ideas, themes, rec)

    text = path.read_text(encoding="utf-8")
    assert "NVDA" in text
    assert "AI infrastructure" in text
    assert "Moderate" in text
    assert "https://example.test/source-a" in text
    assert "AI accelerator demand is rising" in text
