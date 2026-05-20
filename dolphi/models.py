from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Optional
from typing_extensions import NotRequired, Required, TypedDict


class UserProfile(TypedDict, total=False):
    total_savings: Required[float]
    monthly_salary: Required[float]
    currency: Required[str]
    goal: Required[str]  # retirement, growth, income, other
    risk_tolerance: Required[str]  # Aggressive, Moderate, Conservative
    preferred_asset_classes: Required[list[str]]
    # NotRequired — added in v0.2.0; older saved profiles default to 100.
    investment_percentage: NotRequired[float]  # % of total_savings to deploy (10-100)


class AnalystOutput(TypedDict):
    reasoning: str
    score: float  # -1.0 to 1.0
    details: dict


class ResearcherOutput(TypedDict):
    reasoning: str
    thesis: str
    conviction: float  # 0.0 to 1.0


class RiskEvaluation(TypedDict):
    reasoning: str
    fits_profile: bool
    adjusted_score: float


class Allocation(TypedDict):
    symbol: str
    allocation_pct: float
    rationale: str


class PortfolioRecommendation(TypedDict):
    allocations: list[Allocation]
    notes: str


class UniverseSymbol(TypedDict):
    symbol: str
    name: str
    asset_type: str  # stock, etf
    sector: str
    industry: str
    exchange: str
    is_adr: bool


class ThemeRelation(TypedDict):
    symbol: str
    relationship: str
    evidence: str
    confidence: float


class ThemeCluster(TypedDict, total=False):
    seed_symbol: Required[str]
    theme: Required[str]
    thesis: Required[str]
    related_symbols: Required[list[ThemeRelation]]
    source_urls: NotRequired[list[str]]
    narrative_confidence: NotRequired[float]
    source_diversity: NotRequired[float]
    freshness: NotRequired[float]
    source_count: NotRequired[int]


class CandidateIdea(TypedDict):
    symbol: str
    name: str
    asset_type: str
    is_adr: bool
    sector: str
    theme: str
    price: Optional[float]
    features: dict[str, float]
    evidence: list[str]
    risks: list[str]


class RankedIdea(TypedDict):
    rank: int
    symbol: str
    name: str
    asset_type: str
    is_adr: bool
    sector: str
    theme: str
    score: float
    confidence: float
    thesis: str
    evidence: list[str]
    risks: list[str]
    score_breakdown: dict[str, float]


@dataclass(frozen=True)
class MarketNarrative:
    title: str
    thesis: str
    evidence: list[str]
    source_count: int
    source_diversity: float
    freshness: float
    confidence: float
    related_sectors: list[str]
    keywords: list[str]
    source_urls: list[str]


@dataclass
class DiscoveryResult:
    candidate_symbols: list[str]
    ranked_ideas: list[RankedIdea]
    theme_clusters: list[ThemeCluster]
    documents: list[object] = field(default_factory=list)
    narratives: list[MarketNarrative] = field(default_factory=list)


class MarketSummary(TypedDict):
    spx_level: Optional[float]
    vix_level: Optional[float]
    key_sectors: dict[str, float]
    news_headlines: list[str]


class BullAssumption(TypedDict):
    text: str


class DebateJudgment(TypedDict):
    symbol: str
    winner: str  # "bull" | "bear" | "tie"
    conviction_delta: float  # bounded [-0.3, 0.3]
    rationale: str


class Falsifier(TypedDict):
    failure_mode: str
    probability: float
    leading_indicator: str
    breaks_assumption: str
    horizon: str


class PreMortemFinding(TypedDict):
    symbol: str
    falsifiers: list[Falsifier]
    overall_fragility: float


@dataclass
class MemoryRecord:
    user_profile: UserProfile
    date: str
    market_summary: MarketSummary
    recommendation: PortfolioRecommendation
    key_snippets: list[str]


class AgentState(TypedDict):
    user_profile: UserProfile
    market_data: MarketSummary
    technical_analysis: AnalystOutput
    fundamental_analysis: AnalystOutput
    sentiment_analysis: AnalystOutput
    per_ticker_technical: dict[str, AnalystOutput]
    per_ticker_fundamental: dict[str, AnalystOutput]
    per_ticker_sentiment: dict[str, AnalystOutput]
    bull_case: Annotated[list[ResearcherOutput], operator.add]
    bear_case: Annotated[list[ResearcherOutput], operator.add]
    risk_aggressive_eval: Annotated[list[RiskEvaluation], operator.add]
    risk_conservative_eval: Annotated[list[RiskEvaluation], operator.add]
    pre_mortem_findings: list[PreMortemFinding]
    bull_assumptions: list[BullAssumption]
    debate_judgments: list[DebateJudgment]
    reflection_summary: dict
    portfolio_recommendation: PortfolioRecommendation
    memory_hits: list[dict]
    config: dict
    candidate_symbols: list[str]
    ranked_ideas: list[RankedIdea]
    theme_clusters: list[ThemeCluster]
    research_documents: list[object]
    market_narratives: list[MarketNarrative]
