from __future__ import annotations

import logging
from pathlib import Path

import click

from .config import Config
from .data.base import DataFetcher
from .data.cache import SQLiteCache
from .graph.workflow import build_discovery_state, build_portfolio_graph
from .llm import create_llm_client
from .memory import MemoryStore, append_decision_log, compute_reflection
from .models import AgentState
from .profile_store import DEFAULT_PROFILE_PATH, resolve_profile
from .universe import default_universe, open_universe
from .backtest import run_walk_forward_backtest, write_backtest_report
from .backtest.mock_prices import MockHistoricalPrices
from .tui import stream_graph_with_tui

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Disclaimer: This tool is for informational and educational purposes only "
    "and does not constitute financial advice. All trading and investment "
    "decisions are solely your responsibility."
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def _prompt_user(
    *,
    profile_path: str | None = None,
    new_profile: bool = False,
    edit_profile: bool = False,
) -> dict:
    """Resolve the investor profile via the saved-profile flow.

    Delegates to ``dolphi.profile_store.resolve_profile`` so the prompt
    logic stays out of the CLI and is independently testable.
    """
    return dict(resolve_profile(
        path=profile_path,
        force_new=new_profile,
        force_edit=edit_profile,
        interactive=True,
    ))


def _print_portfolio(
    rec: dict,
    profile: dict,
    pre_mortem_findings: list[dict] | None = None,
    debate_judgments: list[dict] | None = None,
) -> None:
    allocations = rec.get("allocations", [])
    notes = rec.get("notes", "")

    click.echo()
    click.echo("=== PORTFOLIO RECOMMENDATION ===")
    click.echo()
    click.echo(
        f"Based on your profile (Risk: {profile.get('risk_tolerance', 'N/A')}, "
        f"Goal: {profile.get('goal', 'N/A')}) "
        f"and current market conditions:"
    )

    # Strategy summary: $-amount-to-invest + cash buffer kept outside the strategy.
    currency = str(profile.get("currency", "USD"))
    savings = float(profile.get("total_savings", 0) or 0)
    invest_pct = float(profile.get("investment_percentage", 100.0) or 100.0)
    invest_amount = savings * invest_pct / 100.0
    cash_buffer = savings - invest_amount
    if savings > 0:
        click.echo()
        click.echo(
            f"Strategy: deploy {invest_pct:.0f}% ({invest_amount:,.0f} {currency}) "
            f"of your {savings:,.0f} {currency}. "
            f"Hold {cash_buffer:,.0f} {currency} as cash buffer outside the strategy."
        )
        click.echo("Below: how the deployed amount splits across positions.")

    click.echo()
    header = f"{'Asset':<16} {'Weight %':<10} {'Amount':<16} {'Rationale':<50}"
    click.echo(header)
    click.echo("-" * len(header))

    for a in allocations:
        sym = a.get("symbol", "?")
        pct = a.get("allocation_pct", 0)
        amount = invest_amount * pct / 100.0 if invest_amount > 0 else 0.0
        rationale = a.get("rationale", "")
        amount_str = f"{amount:,.0f} {currency}" if invest_amount > 0 else "—"
        click.echo(f"{sym:<16} {pct:<10.1f} {amount_str:<16} {rationale:<50}")

    if debate_judgments:
        click.echo()
        click.echo("=== DEBATE VERDICTS (bull vs bear, per symbol) ===")
        for item in debate_judgments:
            delta = float(item.get("conviction_delta", 0))
            sign = "+" if delta > 0 else ""
            click.echo(
                f"  {item.get('symbol')}: winner={item.get('winner')} "
                f"(delta {sign}{delta:.2f}) — {str(item.get('rationale', ''))[:200]}"
            )

    if pre_mortem_findings:
        click.echo()
        click.echo("=== PRE-MORTEM: WHAT WOULD KILL THIS? ===")
        for finding in pre_mortem_findings:
            falsifiers = finding.get("falsifiers", []) or []
            if not falsifiers:
                continue
            click.echo(
                f"  {finding.get('symbol')} (fragility {finding.get('overall_fragility', 0):.2f}):"
            )
            for item in falsifiers[:3]:
                horizon = item.get("horizon", "")
                horizon_tag = f" [{horizon}]" if horizon else ""
                click.echo(
                    f"    - p={item.get('probability', 0):.2f}{horizon_tag} {item.get('failure_mode', '')}"
                )
                breaks = item.get("breaks_assumption", "")
                if breaks:
                    click.echo(f"        breaks: {breaks}")
                indicator = item.get("leading_indicator", "")
                if indicator:
                    click.echo(f"        watch:  {indicator}")

    click.echo()
    click.echo(f"Additional notes: {notes}")
    click.echo()
    click.echo("Disclaimer: Past performance does not guarantee future results.")


def _run_backtest(
    *,
    mock_data: bool,
    skip_cache: bool,
    start_date: str | None,
    end_date: str | None,
    output_dir: str,
    verbose: bool,
) -> None:
    config = Config()
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    if mock_data:
        price_data = MockHistoricalPrices()
        use_demo = True
        jsonl_path = None
        click.echo("Running walk-forward backtest with bundled demo decisions (offline)...")
    else:
        cache = SQLiteCache(config.cache_path, ttl_hours=config.sqlite_cache_ttl_hours)
        price_data = DataFetcher(
            cache,
            skip_cache=skip_cache,
            mock=False,
            newsapi_key=config.newsapi_key,
            alpha_vantage_key=config.alpha_vantage_key,
        )
        use_demo = False
        jsonl_path = config.decision_log_path.with_suffix(".jsonl")
        click.echo(f"Backtesting decisions from {jsonl_path}...")

    result = run_walk_forward_backtest(
        price_data,
        jsonl_path=jsonl_path,
        start_date=start_date,
        end_date=end_date,
        use_demo_fixture=use_demo,
    )
    paths = write_backtest_report(result, output_path)

    click.echo()
    click.echo("=== WALK-FORWARD BACKTEST ===")
    click.echo(f"Window:     {result.start_date} → {result.end_date}")
    click.echo(f"Source:     {result.source}")
    click.echo(f"Periods:    {result.periods}")
    click.echo(f"Portfolio:  {result.total_return_portfolio_pct:+.2f}%")
    click.echo(f"SPY:        {result.total_return_spy_pct:+.2f}%")
    click.echo(f"Alpha:      {result.alpha_pct:+.2f}%")
    click.echo(f"Max DD:     {result.max_drawdown_portfolio_pct:.2f}%")
    click.echo()
    click.echo(f"Metrics:  {paths['metrics']}")
    click.echo(f"Chart:    {paths['svg']}")
    click.echo(f"Summary:  {paths['summary']}")
    if result.notes and verbose:
        click.echo()
        click.echo("Notes:")
        for note in result.notes[:8]:
            click.echo(f"  - {note}")
    click.echo()
    click.echo(_DISCLAIMER)


@click.command()
@click.option("--provider", default=None, help="LLM provider override from config.json (ollama, openai, openrouter, deepseek)")
@click.option("--model", default=None, help="LLM model override from config.json")
@click.option("--use-memory", is_flag=True, help="Enable ChromaDB memory retrieval")
@click.option("--verbose", is_flag=True, help="Print each agent's reasoning")
@click.option("--skip-cache", is_flag=True, help="Force fresh API calls")
@click.option("--mock-data", is_flag=True, help="Use synthetic data (no network calls)")
@click.option("--top-k", default=5, show_default=True, help="Number of discovered ideas to analyze")
@click.option("--seed-symbol", multiple=True, help="Optional seed ticker for theme expansion")
@click.option("--research-query", multiple=True, help="Optional override for the default broad market research agenda")
@click.option(
    "--backtest",
    is_flag=True,
    help="Run walk-forward backtest of decision-log allocations vs SPY (skips portfolio workflow)",
)
@click.option("--backtest-start", default=None, help="Backtest window start (YYYY-MM-DD)")
@click.option("--backtest-end", default=None, help="Backtest window end (YYYY-MM-DD)")
@click.option(
    "--backtest-output",
    default="docs/benchmarks",
    show_default=True,
    help="Directory for backtest metrics, SVG chart, and summary",
)
@click.option("--tui", is_flag=True, help="Rich live dashboard while the workflow runs")
@click.option(
    "--profile-path",
    default=None,
    help=f"Override path for the saved investor profile (default: {DEFAULT_PROFILE_PATH})",
)
@click.option("--new-profile", is_flag=True, help="Discard any saved profile and rebuild from scratch")
@click.option("--edit-profile", is_flag=True, help="Walk through the saved profile field-by-field, press Enter to keep each")
def main(
    provider: str | None,
    model: str,
    use_memory: bool,
    verbose: bool,
    skip_cache: bool,
    mock_data: bool,
    top_k: int,
    seed_symbol: tuple[str, ...],
    research_query: tuple[str, ...],
    backtest: bool,
    backtest_start: str | None,
    backtest_end: str | None,
    backtest_output: str,
    tui: bool,
    profile_path: str | None,
    new_profile: bool,
    edit_profile: bool,
) -> None:
    _setup_logging(verbose)

    if backtest:
        _run_backtest(
            mock_data=mock_data,
            skip_cache=skip_cache,
            start_date=backtest_start,
            end_date=backtest_end,
            output_dir=backtest_output,
            verbose=verbose,
        )
        return

    click.echo()
    click.echo(_DISCLAIMER)
    click.echo()

    config = Config()
    if provider:
        config.llm_provider = provider
    if model:
        config.llm_model = model
    config.verbose = verbose
    config.use_memory = use_memory
    config.skip_cache = skip_cache
    config.mock_data = mock_data

    if not config.alpha_vantage_key:
        logger.info("ALPHA_VANTAGE_KEY not set — skipping Alpha Vantage (using yfinance)")
    if not config.newsapi_key:
        logger.info("NEWSAPI_KEY not set — skipping NewsAPI (no news sentiment)")
    if not config.brave_api_key:
        logger.info("BRAVE_API_KEY not set — skipping Brave Search research")
    if not config.searxng_base_url:
        logger.info("SEARXNG_BASE_URL not set — skipping SearXNG research")

    cache = SQLiteCache(config.cache_path, ttl_hours=config.sqlite_cache_ttl_hours)
    data = DataFetcher(
        cache,
        skip_cache=skip_cache,
        mock=mock_data,
        newsapi_key=config.newsapi_key,
        alpha_vantage_key=config.alpha_vantage_key,
    )

    user_profile = _prompt_user(
        profile_path=profile_path,
        new_profile=new_profile,
        edit_profile=edit_profile,
    )

    llm = create_llm_client(config)
    if mock_data:
        beneficiary_llm = None
        logger.info("LLM beneficiary mapping disabled in mock mode; falling back to keyword path")
    else:
        beneficiary_llm = llm

    memory: MemoryStore | None = None
    memory_hits: list[dict] = []
    if use_memory:
        try:
            memory = MemoryStore(config.chroma_path)
            memory_hits = memory.recall(user_profile, n=3)
            if memory_hits:
                click.echo(f"Found {len(memory_hits)} similar past analyses in memory.")
        except Exception as e:
            logger.warning("Memory store unavailable: %s. Continuing without it.", e)

    click.echo("Fetching market data...")
    market_data = data.get_market_summary()
    sectors = data.get_sector_performance()

    reflection_summary: dict = {"entries_count": 0, "summary_text": "", "entries": []}
    if not mock_data:
        try:
            reflection_summary = compute_reflection(
                config.decision_log_path.with_suffix(".jsonl"),
                data,
            )
            if reflection_summary.get("entries_count"):
                click.echo(
                    f"Reflection: graded {reflection_summary['entries_count']} prior decision(s) vs SPY"
                )
        except Exception as exc:
            logger.warning("Reflection skipped: %s", exc)

    if mock_data:
        universe = default_universe()
        logger.info("Using curated demo universe (%d symbols) because --mock-data is set", len(universe))
    else:
        universe = open_universe(
            cache_dir=config.universe_cache_dir,
            max_age_hours=config.universe_max_age_hours,
            fetch=True,
        )
        logger.info("Loaded open universe with %d symbols", len(universe))

    discovery = build_discovery_state(
        user_profile,
        data,
        top_k=top_k,
        seed_symbols=list(seed_symbol) or None,
        research_queries=list(research_query) or None,
        research_depth=config.research_depth,
        newsapi_key=config.newsapi_key,
        brave_api_key=config.brave_api_key,
        searxng_base_url=config.searxng_base_url,
        universe=universe,
        llm=beneficiary_llm,
    )
    narratives = discovery.get("market_narratives", [])
    if narratives:
        click.echo("Discovered research narratives:")
        for narrative in narratives[:3]:
            click.echo(f"  - {narrative.title} confidence={narrative.confidence:.2f}")
    if discovery["ranked_ideas"]:
        click.echo("Discovered top ideas:")
        for idea in discovery["ranked_ideas"]:
            click.echo(f"  {idea['rank']}. {idea['symbol']} ({idea['theme']}) score={idea['score']:.2f}")

    initial_state: AgentState = {
        "user_profile": user_profile,
        "market_data": {
            "spx_level": market_data.get("spx_level"),
            "vix_level": market_data.get("vix_level"),
            "key_sectors": sectors,
            "news_headlines": [],
        },
        "technical_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "fundamental_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "sentiment_analysis": {"reasoning": "", "score": 0.0, "details": {}},
        "bull_case": [],
        "bear_case": [],
        "risk_aggressive_eval": [],
        "risk_conservative_eval": [],
        "pre_mortem_findings": [],
        "bull_assumptions": [],
        "debate_judgments": [],
        "reflection_summary": reflection_summary,
        "portfolio_recommendation": {"allocations": [], "notes": ""},
        "memory_hits": memory_hits,
        "config": {
            "verbose": verbose,
            "provider": config.llm_provider,
            "model": config.llm_model,
            "research_depth": config.research_depth,
            "use_memory": use_memory,
        },
        **discovery,
    }

    click.echo("Running analyst team...")
    graph = build_portfolio_graph(llm, data)

    click.echo("Executing analysis workflow...")
    if tui:
        final_state = stream_graph_with_tui(graph, initial_state)
    else:
        final_state = graph.invoke(initial_state)

    rec = final_state.get("portfolio_recommendation", {})
    pre_mortem_findings = final_state.get("pre_mortem_findings", [])
    debate_judgments = final_state.get("debate_judgments", [])
    _print_portfolio(
        rec,
        user_profile,
        pre_mortem_findings=pre_mortem_findings,
        debate_judgments=debate_judgments,
    )
    append_decision_log(
        config.decision_log_path,
        user_profile,
        final_state.get("ranked_ideas", []),
        final_state.get("theme_clusters", []),
        rec,
        pre_mortem_findings=pre_mortem_findings,
        debate_judgments=debate_judgments,
    )
    click.echo(f"Decision log updated: {config.decision_log_path}")

    if memory is not None:
        try:
            snippets = []
            for key in ["technical_analysis", "fundamental_analysis", "sentiment_analysis"]:
                val = final_state.get(key, {})
                if val.get("reasoning"):
                    snippets.append(val["reasoning"][:200])
            memory.remember(user_profile, market_data, rec, snippets)
            click.echo("Past analysis stored in memory for future reference.")
        except Exception as e:
            logger.warning("Failed to store memory: %s", e)


if __name__ == "__main__":
    main()
