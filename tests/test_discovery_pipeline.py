from dolphi.allocation.optimizer import allocate_ranked_ideas
from dolphi.data.base import DataFetcher
from dolphi.ideas.pipeline import discover_ranked_ideas
from dolphi.scoring.composite import rank_candidates
from dolphi.themes.expander import expand_themes
from dolphi.universe.symbols import default_universe, find_symbol, symbols_for_profile


def profile(risk="Moderate"):
    return {
        "total_savings": 100000,
        "monthly_salary": 10000,
        "currency": "USD",
        "goal": "growth",
        "risk_tolerance": risk,
        "preferred_asset_classes": ["stocks", "etfs"],
    }


def test_default_universe_includes_us_etfs_and_major_adrs():
    universe = default_universe()

    assert find_symbol("NVDA", universe)["asset_type"] == "stock"
    assert find_symbol("SMH", universe)["asset_type"] == "etf"
    assert find_symbol("TSM", universe)["is_adr"] is True
    assert find_symbol("NOTREAL", universe) is None


def test_symbols_for_profile_filters_by_asset_preferences():
    universe = default_universe()

    stocks_only = symbols_for_profile({"preferred_asset_classes": ["stocks"]}, universe)
    etfs_only = symbols_for_profile({"preferred_asset_classes": ["etfs"]}, universe)

    assert "NVDA" in stocks_only
    assert "SPY" not in stocks_only
    assert "SPY" in etfs_only
    assert "NVDA" not in etfs_only


def test_theme_expansion_validates_related_symbols_against_universe():
    clusters = expand_themes(["NVDA", "NOTREAL"], default_universe())

    nvda = clusters[0]
    related = {item["symbol"] for item in nvda["related_symbols"]}
    assert nvda["seed_symbol"] == "NVDA"
    assert {"TSM", "SMH", "CEG"}.issubset(related)
    assert "NOTREAL" not in {cluster["seed_symbol"] for cluster in clusters}


def test_rank_candidates_is_deterministic_and_limits_top_k():
    candidates = [
        {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI Infrastructure",
            "price": 880,
            "features": {"momentum": 0.4, "valuation": 0.2, "liquidity": 1.0, "theme_strength": 0.9},
            "evidence": ["strong momentum"],
            "risks": ["valuation"],
        },
        {
            "symbol": "BND",
            "name": "Vanguard Total Bond Market ETF",
            "asset_type": "etf",
            "is_adr": False,
            "sector": "Fixed Income",
            "theme": "Defensive ballast",
            "price": 72,
            "features": {"momentum": 0.05, "valuation": 0.5, "liquidity": 0.9, "theme_strength": 0.2},
            "evidence": ["low volatility"],
            "risks": ["rate sensitivity"],
        },
    ]

    ranked = rank_candidates(candidates, top_k=1)

    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "NVDA"
    assert ranked[0]["rank"] == 1
    assert 0 <= ranked[0]["confidence"] <= 1


def test_rank_candidates_diversifies_sectors_when_scores_are_close():
    candidates = [
        {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI",
            "price": 1,
            "features": {"narrative_confidence": 0.9, "source_diversity": 0.8, "source_recency": 0.9, "relationship_strength": 0.9, "market_trend": 0.8, "valuation": 0.5, "liquidity": 0.9},
            "evidence": ["AI"],
            "risks": [],
        },
        {
            "symbol": "AMD",
            "name": "AMD",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI",
            "price": 1,
            "features": {"narrative_confidence": 0.88, "source_diversity": 0.8, "source_recency": 0.9, "relationship_strength": 0.9, "market_trend": 0.8, "valuation": 0.5, "liquidity": 0.9},
            "evidence": ["AI"],
            "risks": [],
        },
        {
            "symbol": "CEG",
            "name": "Constellation Energy",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Utilities",
            "theme": "AI Power",
            "price": 1,
            "features": {"narrative_confidence": 0.86, "source_diversity": 0.8, "source_recency": 0.9, "relationship_strength": 0.9, "market_trend": 0.8, "valuation": 0.5, "liquidity": 0.9},
            "evidence": ["Power"],
            "risks": [],
        },
    ]

    ranked = rank_candidates(candidates, top_k=2)

    assert {idea["sector"] for idea in ranked} == {"Technology", "Utilities"}


def test_discover_ranked_ideas_uses_mock_data_and_theme_expansion():
    data = DataFetcher(cache=None, mock=True)

    result = discover_ranked_ideas(profile(), data, top_k=5, seed_symbols=["NVDA"])

    symbols = [idea["symbol"] for idea in result.ranked_ideas]
    assert "NVDA" in symbols
    assert any(cluster["seed_symbol"] == "NVDA" for cluster in result.theme_clusters)
    assert result.candidate_symbols == symbols


def test_discover_ranked_ideas_respects_asset_preferences_during_theme_expansion():
    data = DataFetcher(cache=None, mock=True)

    result = discover_ranked_ideas(
        {"preferred_asset_classes": ["stocks"], "risk_tolerance": "Moderate", "goal": "growth"},
        data,
        top_k=10,
        seed_symbols=["NVDA"],
    )

    assert "NVDA" in result.candidate_symbols
    assert "SMH" not in result.candidate_symbols
    assert "SOXX" not in result.candidate_symbols


def test_allocate_ranked_ideas_sums_to_100_and_respects_risk_profile():
    ideas = [
        {
            "rank": 1,
            "symbol": "NVDA",
            "name": "NVIDIA",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI Infrastructure",
            "score": 0.9,
            "confidence": 0.9,
            "thesis": "AI leader",
            "evidence": ["strong demand"],
            "risks": ["valuation"],
        },
        {
            "rank": 2,
            "symbol": "TSM",
            "name": "Taiwan Semiconductor",
            "asset_type": "stock",
            "is_adr": True,
            "sector": "Technology",
            "theme": "Foundry beneficiary",
            "score": 0.7,
            "confidence": 0.7,
            "thesis": "foundry exposure",
            "evidence": ["AI demand"],
            "risks": ["geopolitical risk"],
        },
    ]

    rec = allocate_ranked_ideas(ideas, profile("Conservative"))

    assert round(sum(item["allocation_pct"] for item in rec["allocations"]), 1) == 100.0
    assert any(item["symbol"] == "BND" for item in rec["allocations"])
    assert max(item["allocation_pct"] for item in rec["allocations"]) <= 45


def test_allocate_ranked_ideas_caps_single_sector_exposure():
    ideas = [
        {
            "rank": 1,
            "symbol": "NVDA",
            "name": "NVIDIA",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI",
            "score": 0.95,
            "confidence": 0.9,
            "thesis": "AI leader",
            "evidence": ["AI"],
            "risks": [],
            "score_breakdown": {},
        },
        {
            "rank": 2,
            "symbol": "AMD",
            "name": "AMD",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Technology",
            "theme": "AI",
            "score": 0.9,
            "confidence": 0.85,
            "thesis": "AI competitor",
            "evidence": ["AI"],
            "risks": [],
            "score_breakdown": {},
        },
        {
            "rank": 3,
            "symbol": "CEG",
            "name": "Constellation Energy",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Utilities",
            "theme": "AI power",
            "score": 0.7,
            "confidence": 0.75,
            "thesis": "Power demand",
            "evidence": ["Power"],
            "risks": [],
            "score_breakdown": {},
        },
    ]

    rec = allocate_ranked_ideas(ideas, profile("Moderate"))
    technology_weight = sum(item["allocation_pct"] for item in rec["allocations"] if item["symbol"] in {"NVDA", "AMD"})

    assert technology_weight <= 45


def test_allocate_ranked_ideas_merges_duplicate_defensive_holdings_and_avoids_negative_cash():
    ideas = [
        {
            "rank": 1,
            "symbol": "JPM",
            "name": "JPMorgan Chase",
            "asset_type": "stock",
            "is_adr": False,
            "sector": "Financial Services",
            "theme": "Financial Conditions",
            "score": 0.88,
            "confidence": 0.9,
            "thesis": "large-cap bank exposure",
            "evidence": ["credit conditions"],
            "risks": [],
            "score_breakdown": {},
        },
        {
            "rank": 2,
            "symbol": "BND",
            "name": "Vanguard Total Bond Market ETF",
            "asset_type": "etf",
            "is_adr": False,
            "sector": "Fixed Income",
            "theme": "Defensive Rotation",
            "score": 0.61,
            "confidence": 0.7,
            "thesis": "bond ballast",
            "evidence": ["defensive rotation"],
            "risks": [],
            "score_breakdown": {},
        },
    ]

    rec = allocate_ranked_ideas(ideas, profile("Moderate"))
    symbols = [item["symbol"] for item in rec["allocations"]]

    assert symbols.count("BND") == 1
    assert all(item["allocation_pct"] >= 0 for item in rec["allocations"])
    assert round(sum(item["allocation_pct"] for item in rec["allocations"]), 1) == 100.0
