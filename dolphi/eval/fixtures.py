"""Curated bull-case fixtures for the falsifier-quality eval.

Each fixture is a (thesis, named load-bearing assumptions, primary symbol)
tuple representing a real-ish macro/sector investment thesis. The eval feeds
the assumptions and the symbol into the pre-mortem agent under test; the
falsifiers it produces are then scored by the judge.

Adding a fixture:

    BullCaseFixture(
        slug="kebab-case-id",            # stable across runs; used as CSV column
        title="Human-readable title",
        symbol="TICK",                   # primary symbol the pre-mortem attacks
        sector="GICS sector or 'macro'",
        thesis="2-3 sentences of the bull case.",
        assumptions=(
            "Load-bearing claim 1.",
            "Load-bearing claim 2.",
            "Load-bearing claim 3.",
        ),
    )

Assumptions should be phrased as *positive factual claims about the world*
the thesis depends on — not opinions, not value judgments. The eval treats
these as ground truth; falsifiers are graded on whether they actually
threaten one of these claims.

Coverage (v0.2.0): all eight fixtures ship — AI capex, semiconductor
pricing power, energy transition, GLP-1 demand, defence procurement,
China/ADR overhang, regional banking, REIT rate sensitivity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BullCaseFixture:
    slug: str
    title: str
    symbol: str
    sector: str
    thesis: str
    assumptions: tuple[str, ...]

    def as_research_output(self) -> dict:
        return {
            "thesis": self.thesis,
            "reasoning": " ".join(self.assumptions),
            "conviction": 0.7,
        }


_AI_CAPEX = BullCaseFixture(
    slug="ai-capex",
    title="AI capex sustains semiconductor leadership through 2027",
    symbol="NVDA",
    sector="Technology",
    thesis=(
        "Hyperscaler AI capex remains above $200B annually through 2027, "
        "driven by training-cluster scale-up and inference deployment at the "
        "edge. NVDA retains > 80% accelerator share on software moat (CUDA, "
        "TensorRT) and hardware roadmap (Blackwell, Rubin). Forward P/E of "
        "30x is consistent with 25% earnings growth and 70%+ gross margins."
    ),
    assumptions=(
        "Hyperscaler AI capex grows at least 20% YoY each year through 2027.",
        "NVDA accelerator share stays above 75% as competitors (AMD, Intel, "
        "in-house silicon) fail to close the software/ecosystem gap.",
        "Gross margins remain above 65% as supply constraints ease without "
        "triggering ASP compression.",
    ),
)


_SEMI_PRICING_POWER = BullCaseFixture(
    slug="semi-pricing-power",
    title="Semiconductor cycle pricing power holds through inventory normalisation",
    symbol="TSM",
    sector="Technology",
    thesis=(
        "TSMC's leading-edge node (3nm/2nm) capacity remains supply-constrained "
        "while Apple, NVIDIA, and AMD compete for wafer starts. Pricing power "
        "in advanced nodes offsets PC/handset weakness; gross margin floor at "
        "53% even in a downcycle. Foundry consolidation around TSMC reduces "
        "customer ability to extract concessions."
    ),
    assumptions=(
        "Leading-edge (≤3nm) capacity utilisation stays above 90% for the next "
        "8 quarters.",
        "TSMC raises N3 wafer ASPs at least 5% per year through 2027.",
        "Samsung Foundry and Intel Foundry Services do not capture more than "
        "10% combined of leading-edge demand by 2026.",
    ),
)


_ENERGY_TRANSITION = BullCaseFixture(
    slug="energy-transition",
    title="Data-centre power demand drives utility re-rating",
    symbol="CEG",
    sector="Utilities",
    thesis=(
        "AI training and inference workloads add 50-90 TWh of US incremental "
        "data-centre electricity demand by 2027. Behind-the-meter nuclear PPAs "
        "with hyperscalers (Microsoft-Three Mile Island template) lock in "
        "premium pricing and decouple CEG's revenue from spot power markets. "
        "Capacity prices in PJM stay structurally elevated."
    ),
    assumptions=(
        "At least 30 GW of new hyperscaler data-centre nameplate capacity is "
        "contracted in the US by end of 2027.",
        "PJM capacity auction clearing prices stay above $200/MW-day through "
        "2027.",
        "At least two more behind-the-meter nuclear PPAs at premium to spot "
        "are announced in the next 12 months.",
    ),
)


_GLP_1 = BullCaseFixture(
    slug="glp-1",
    title="GLP-1 obesity-drug demand sustains pricing power through 2027",
    symbol="LLY",
    sector="Healthcare",
    thesis=(
        "Tirzepatide (Mounjaro / Zepbound) and the next-generation oral and "
        "long-acting injectables keep Lilly at the centre of the obesity "
        "category. Insurance coverage expands as outcomes data (cardio, renal, "
        "MASH) accumulates. Manufacturing capacity catches up faster than "
        "demand, but real-world adherence keeps Rx volume growing at "
        "high-double-digit YoY rates through 2027."
    ),
    assumptions=(
        "Tirzepatide US retail prescription volume grows at least 30% YoY "
        "through end of 2027.",
        "At least 60% of large US employer-sponsored health plans cover "
        "GLP-1s for obesity (not just diabetes) by end of 2026.",
        "No new entrant captures more than 15% of the GLP-1 obesity market "
        "(by US Rx share) before 2028.",
    ),
)


_DEFENCE_PROCUREMENT = BullCaseFixture(
    slug="defence-procurement",
    title="Sustained US + NATO procurement budgets through 2028",
    symbol="LMT",
    sector="Industrials",
    thesis=(
        "Geopolitical realignment forces structurally higher defence spending: "
        "European NATO members crossing the 2% GDP floor, US DoD topline above "
        "$900B, and replenishment cycles for Ukraine-depleted munitions and "
        "missile-defence stocks. Lockheed's F-35, PAC-3, HIMARS, and CH-53K "
        "franchises sit at the centre of those budgets with multi-year "
        "backlogs."
    ),
    assumptions=(
        "US Department of Defense base topline (excluding OCO) grows at least "
        "3% nominal each year through FY2028.",
        "At least 18 of 32 NATO members meet or exceed the 2% of GDP defence "
        "spending floor by end of 2027.",
        "Lockheed Martin's reported backlog stays above $150B at every fiscal "
        "year-end through 2027.",
    ),
)


_CHINA_ADR_OVERHANG = BullCaseFixture(
    slug="china-adr-overhang",
    title="Sentiment normalisation lifts US-listed China ADRs",
    symbol="BABA",
    sector="Consumer Cyclical",
    thesis=(
        "China policy easing (consumption stimulus, property-sector "
        "stabilisation, AI champion support) plus PCAOB audit clarity reduce "
        "the delisting tail risk that has compressed multiples on US-listed "
        "China ADRs since 2021. Alibaba's cloud + AI franchise re-rates as "
        "domestic AI capex accelerates and its core commerce stabilises GMV "
        "share."
    ),
    assumptions=(
        "PCAOB inspection access to China-based auditors is renewed at every "
        "annual review through 2027 without material restriction.",
        "Alibaba Cloud revenue grows at least 15% YoY in each of the next "
        "eight reported quarters.",
        "Chinese household-consumption growth (NBS retail sales ex-auto) "
        "exceeds 5% YoY in at least three of the next four calendar quarters.",
    ),
)


_REGIONAL_BANKING = BullCaseFixture(
    slug="regional-banking",
    title="Regional bank NIM recovery as the curve steepens",
    symbol="KEY",
    sector="Financial Services",
    thesis=(
        "Post-SVB deposit costs have peaked and start to roll lower as the "
        "Fed cuts the front end while the long end stays anchored above 4%. "
        "Net interest margin expands ~25-40 bps from trough through 2026. "
        "Office-CRE losses are mostly reserved-for at this point; loan-loss "
        "provisioning normalises. KeyCorp's fee-income mix and the Laurel Road "
        "consumer franchise are under-appreciated."
    ),
    assumptions=(
        "The 2s10s US Treasury spread stays positive on at least 80% of "
        "trading days through end of 2026.",
        "KeyCorp's net interest margin expands at least 20 bps from its 2024 "
        "trough by end of fiscal 2026.",
        "Office-CRE net charge-off rate at US regional banks (FDIC data) "
        "peaks below 2.5% and declines YoY by end of 2026.",
    ),
)


_REIT_RATE_SENSITIVITY = BullCaseFixture(
    slug="reit-rate-sensitivity",
    title="Cell-tower REIT re-rates as the 10y comes off the highs",
    symbol="AMT",
    sector="Real Estate",
    thesis=(
        "Tower REITs have been a duration trade in disguise: when the US 10y "
        "settles into a 3.5-4.5% range from the 2023 highs, AMT's discount "
        "rate falls and its AFFO multiple re-rates. Mobile-data traffic "
        "growth (5G mid-band densification, fixed-wireless access) supports "
        "mid-single-digit organic leasing growth. India divestiture removes "
        "an FX/risk drag."
    ),
    assumptions=(
        "The US 10-year Treasury yield's monthly average stays below 4.5% in "
        "at least nine of the twelve months of 2026.",
        "American Tower's organic tenant billings growth stays above 5% YoY "
        "in each of the next eight reported quarters.",
        "AMT achieves an investment-grade credit rating from at least two of "
        "S&P / Moody's / Fitch at every quarter-end through 2027.",
    ),
)


def all_fixtures() -> list[BullCaseFixture]:
    """Return all shipped fixtures in stable order (alphabetical by slug).

    Add new fixtures here as they are written. The leaderboard report
    relies on the stable order so re-runs compare like-for-like.
    """
    return [
        _AI_CAPEX,
        _CHINA_ADR_OVERHANG,
        _DEFENCE_PROCUREMENT,
        _ENERGY_TRANSITION,
        _GLP_1,
        _REGIONAL_BANKING,
        _REIT_RATE_SENSITIVITY,
        _SEMI_PRICING_POWER,
    ]


def fixtures_by_slug(slugs: list[str] | None) -> list[BullCaseFixture]:
    """Filter fixtures by slug. ``None`` or ``["all"]`` returns all fixtures."""
    if not slugs or slugs == ["all"]:
        return all_fixtures()
    by_slug = {fx.slug: fx for fx in all_fixtures()}
    out: list[BullCaseFixture] = []
    for slug in slugs:
        if slug in by_slug:
            out.append(by_slug[slug])
    return out
