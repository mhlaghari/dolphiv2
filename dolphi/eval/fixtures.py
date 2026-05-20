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

Coverage targets (v0.2.0): AI capex, semiconductor pricing power, energy
transition, GLP-1 demand, defence procurement, China/ADR overhang, regional
banking, REIT rate sensitivity. v0.2.0 ships with the first three; the
remaining five are flagged as TODO in PLAN.md.
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


def all_fixtures() -> list[BullCaseFixture]:
    """Return all shipped fixtures in stable order.

    Add new fixtures here as they are written. Order is preserved in the
    leaderboard report.
    """
    return [_AI_CAPEX, _SEMI_PRICING_POWER, _ENERGY_TRANSITION]


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
