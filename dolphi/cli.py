from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .banner import print_banner
from .check import run_check
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


def _fragility_style(value: float) -> str:
    if value >= 0.5:
        return "bold red"
    if value >= 0.25:
        return "bold yellow"
    return "bold green"


def _delta_style(delta: float) -> str:
    if delta >= 0.10:
        return "bold green"
    if delta <= -0.10:
        return "bold red"
    return "dim"


def _print_portfolio(
    rec: dict,
    profile: dict,
    pre_mortem_findings: list[dict] | None = None,
    debate_judgments: list[dict] | None = None,
) -> None:
    allocations = rec.get("allocations", [])
    notes = rec.get("notes", "")
    console = Console()

    currency = str(profile.get("currency", "USD"))
    savings = float(profile.get("total_savings", 0) or 0)
    invest_pct = float(profile.get("investment_percentage", 100.0) or 100.0)
    invest_amount = savings * invest_pct / 100.0
    cash_buffer = savings - invest_amount

    fragility_by_symbol = {
        finding.get("symbol"): float(finding.get("overall_fragility", 0.0) or 0.0)
        for finding in (pre_mortem_findings or [])
    }

    console.print()
    header_text = Text.assemble(
        ("portfolio recommendation", "bold bright_white"),
        ("    risk=", "dim"), (profile.get("risk_tolerance", "?"), "bright_white"),
        ("    goal=", "dim"), (profile.get("goal", "?"), "bright_white"),
    )
    console.print(Panel(header_text, border_style="bright_cyan", box=ROUNDED))

    if savings > 0:
        strategy = Text.assemble(
            ("deploy ", "dim"),
            (f"{invest_pct:.0f}%", "bold bright_cyan"),
            ("  (", "dim"),
            (f"{invest_amount:,.0f} {currency}", "bold bright_white"),
            (")  of your ", "dim"),
            (f"{savings:,.0f} {currency}", "bright_white"),
            ("\nhold ", "dim"),
            (f"{cash_buffer:,.0f} {currency}", "bold yellow"),
            (" as cash buffer outside the strategy", "dim"),
        )
        console.print(Panel(strategy, border_style="cyan", title="strategy", title_align="left"))

    # Allocation table.
    table = Table(box=ROUNDED, expand=False, show_lines=False, title_style="bold bright_white")
    table.add_column("symbol", style="bold bright_cyan", no_wrap=True)
    table.add_column("weight", justify="right")
    table.add_column("amount", justify="right", style="bright_white")
    table.add_column("fragility", justify="right")
    table.add_column("rationale", style="dim", overflow="fold")
    for a in allocations:
        sym = str(a.get("symbol", "?"))
        pct = float(a.get("allocation_pct", 0) or 0)
        amount = invest_amount * pct / 100.0 if invest_amount > 0 else 0.0
        amount_str = f"{amount:,.0f} {currency}" if invest_amount > 0 else "—"
        fragility = fragility_by_symbol.get(sym)
        frag_cell = (
            Text(f"{fragility:.2f}", style=_fragility_style(fragility))
            if fragility is not None
            else Text("—", style="dim")
        )
        rationale = str(a.get("rationale", ""))
        # Trim *display* length; full text is preserved in the decision log.
        if len(rationale) > 120:
            rationale = rationale[:117] + "…"
        table.add_row(sym, f"{pct:.1f}%", amount_str, frag_cell, rationale)
    console.print(table)

    if debate_judgments:
        dj_table = Table(box=ROUNDED, title="debate verdicts (bull vs bear, per symbol)",
                          title_style="bold magenta", expand=False)
        dj_table.add_column("symbol", style="bold bright_cyan")
        dj_table.add_column("winner")
        dj_table.add_column("delta", justify="right")
        dj_table.add_column("rationale", style="dim", overflow="fold")
        for item in debate_judgments:
            winner = str(item.get("winner", "tie"))
            winner_style = "green" if winner == "bull" else "red" if winner == "bear" else "dim"
            delta = float(item.get("conviction_delta", 0) or 0)
            sign = "+" if delta > 0 else ""
            rationale = str(item.get("rationale", ""))[:200]
            dj_table.add_row(
                str(item.get("symbol", "?")),
                Text(winner, style=winner_style),
                Text(f"{sign}{delta:.2f}", style=_delta_style(delta)),
                rationale,
            )
        console.print(dj_table)

    if pre_mortem_findings:
        console.print()
        console.print(Text("pre-mortem: what would kill this?", style="bold bright_red"))
        for finding in pre_mortem_findings:
            falsifiers = finding.get("falsifiers", []) or []
            if not falsifiers:
                continue
            fragility = float(finding.get("overall_fragility", 0) or 0)
            header = Text.assemble(
                ("  ", ""),
                (str(finding.get("symbol", "?")), "bold bright_cyan"),
                ("    fragility ", "dim"),
                (f"{fragility:.2f}", _fragility_style(fragility)),
            )
            console.print(header)
            for item in falsifiers[:3]:
                horizon = item.get("horizon", "")
                p = float(item.get("probability", 0) or 0)
                line = Text.assemble(
                    ("    p=", "dim"),
                    (f"{p:.2f}", "bright_yellow"),
                    (f" [{horizon}] " if horizon else " ", "dim"),
                    (str(item.get("failure_mode", "")), "bright_white"),
                )
                console.print(line)
                breaks = str(item.get("breaks_assumption", ""))
                if breaks:
                    console.print(Text("        breaks: ", style="magenta") + Text(breaks, style="dim italic"))
                indicator = str(item.get("leading_indicator", ""))
                if indicator:
                    console.print(Text("        watch:  ", style="cyan") + Text(indicator, style="bright_white"))

    if notes:
        console.print()
        console.print(Panel(Text(notes, style="dim italic"), border_style="dim", title="notes", title_align="left"))

    console.print()
    console.print(Text("Past performance does not guarantee future results.", style="dim"))
    console.print(
        Text("\nNext Monday: ", style="dim")
        + Text("dolphi --check", style="bold bright_cyan")
        + Text(" to revisit the leading indicators above.", style="dim")
    )


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
@click.option("--check", "check_falsifiers", is_flag=True, help="Revisit the leading indicators from the most recent decision and mark each safe / triggered / unsure")
@click.option("--include-uae", is_flag=True, help="Include UAE-listed equities (DFM + ADX) in the universe alongside US listings")
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
    check_falsifiers: bool,
    include_uae: bool,
) -> None:
    _setup_logging(verbose)

    if check_falsifiers:
        from pathlib import Path
        log_path = (
            Path(profile_path).parent / "decision_log.jsonl"
            if profile_path
            else None
        )
        raise SystemExit(run_check(jsonl_path=log_path))

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

    print_banner()
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
        if include_uae:
            from .universe import load_uae_listed
            universe = universe + load_uae_listed()
            logger.info("Mock-data universe extended with %d UAE symbols (DFM + ADX)", len(load_uae_listed()))
        logger.info("Using curated demo universe (%d symbols) because --mock-data is set", len(universe))
    else:
        universe = open_universe(
            cache_dir=config.universe_cache_dir,
            max_age_hours=config.universe_max_age_hours,
            fetch=True,
            include_uae=include_uae,
        )
        logger.info("Loaded open universe with %d symbols%s",
                    len(universe), " (incl. UAE)" if include_uae else "")

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
