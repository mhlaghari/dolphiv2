from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from ..agents import (
    bear_researcher,
    bull_researcher,
    debate,
    debate_judge,
    fundamental_analyst,
    portfolio_manager,
    pre_mortem,
    risk_aggressive,
    risk_conservative,
    sentiment_analyst,
    technical_analyst,
)
from ..data.base import DataFetcher
from ..ideas.pipeline import discover_ranked_ideas
from ..llm import OllamaClient
from ..models import AgentState, UniverseSymbol

logger = logging.getLogger(__name__)


def _analyst_team(state: AgentState) -> list[Send]:
    return [
        Send("technical_analyst", state),
        Send("fundamental_analyst", state),
        Send("sentiment_analyst", state),
    ]


def build_discovery_state(
    profile: dict,
    data: DataFetcher,
    top_k: int = 5,
    seed_symbols: list[str] | None = None,
    research_queries: list[str] | None = None,
    research_depth: str = "standard",
    newsapi_key: str | None = None,
    brave_api_key: str | None = None,
    searxng_base_url: str | None = None,
    universe: list[UniverseSymbol] | None = None,
    llm: OllamaClient | None = None,
) -> dict:
    result = discover_ranked_ideas(
        profile,
        data,
        top_k=top_k,
        seed_symbols=seed_symbols,
        research_queries=research_queries,
        research_depth=research_depth,
        newsapi_key=newsapi_key,
        brave_api_key=brave_api_key,
        searxng_base_url=searxng_base_url,
        universe=universe,
        llm=llm,
    )
    return {
        "candidate_symbols": result.candidate_symbols,
        "ranked_ideas": result.ranked_ideas,
        "theme_clusters": result.theme_clusters,
        "research_documents": result.documents,
        "market_narratives": result.narratives,
    }


def build_portfolio_graph(llm: OllamaClient, data: DataFetcher) -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("technical_analyst", lambda s: technical_analyst(s, llm=llm, data=data))
    workflow.add_node("fundamental_analyst", lambda s: fundamental_analyst(s, llm=llm, data=data))
    workflow.add_node("sentiment_analyst", lambda s: sentiment_analyst(s, llm=llm, data=data))
    workflow.add_node("bull_researcher", lambda s: bull_researcher(s, llm=llm))
    workflow.add_node("bear_researcher", lambda s: bear_researcher(s, llm=llm))
    workflow.add_node("debate", lambda s: debate(s, llm=llm))
    workflow.add_node("debate_judge", lambda s: debate_judge(s, llm=llm))
    workflow.add_node("risk_aggressive", lambda s: risk_aggressive(s, llm=llm))
    workflow.add_node("risk_conservative", lambda s: risk_conservative(s, llm=llm))
    workflow.add_node("pre_mortem", lambda s: pre_mortem(s, llm=llm))
    workflow.add_node("portfolio_manager", lambda s: portfolio_manager(s, llm=llm))

    workflow.set_conditional_entry_point(_analyst_team)

    analyst_nodes = ["technical_analyst", "fundamental_analyst", "sentiment_analyst"]
    workflow.add_edge(analyst_nodes, "bull_researcher")
    workflow.add_edge(analyst_nodes, "bear_researcher")

    researcher_nodes = ["bull_researcher", "bear_researcher"]
    workflow.add_edge(researcher_nodes, "debate")
    workflow.add_edge("debate", "debate_judge")
    workflow.add_edge("debate_judge", "risk_aggressive")
    workflow.add_edge("debate_judge", "risk_conservative")

    workflow.add_edge(["risk_aggressive", "risk_conservative"], "pre_mortem")
    workflow.add_edge("pre_mortem", "portfolio_manager")

    workflow.add_edge("portfolio_manager", END)

    return workflow.compile()
