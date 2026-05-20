"""Rich live display for the portfolio workflow."""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _truncate(text: str, limit: int = 120) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _stage_label(state: dict[str, Any]) -> str:
    if state.get("portfolio_recommendation", {}).get("allocations"):
        return "portfolio_manager ✓"
    if state.get("pre_mortem_findings"):
        return "pre_mortem ✓"
    if state.get("debate_judgments"):
        return "debate_judge ✓"
    if len(state.get("bull_case") or []) > 1 or len(state.get("bear_case") or []) > 1:
        return "debate ✓"
    if state.get("bull_case") and state.get("bear_case"):
        return "researchers ✓"
    if state.get("per_ticker_technical") or state.get("technical_analysis", {}).get("reasoning"):
        return "analysts ✓"
    return "starting…"


def render_workflow_state(state: dict[str, Any]) -> RenderableType:
    stage = _stage_label(state)
    header = Text(f"Dolphi — {stage}", style="bold cyan")

    ideas_table = Table(title="Discovered ideas", expand=True, show_header=True, header_style="bold")
    ideas_table.add_column("Rank", width=5)
    ideas_table.add_column("Symbol", width=8)
    ideas_table.add_column("Theme", width=24)
    ideas_table.add_column("Score", width=8)
    for idea in (state.get("ranked_ideas") or [])[:5]:
        ideas_table.add_row(
            str(idea.get("rank", "")),
            str(idea.get("symbol", "")),
            _truncate(str(idea.get("theme", "")), 24),
            f"{float(idea.get('score', 0)):.2f}",
        )
    if not (state.get("ranked_ideas") or []):
        ideas_table.add_row("—", "—", "(pending discovery)", "—")

    debate_table = Table(title="Debate", expand=True)
    debate_table.add_column("Side", width=8)
    debate_table.add_column("Turns", width=6)
    debate_table.add_column("Latest thesis", width=60)
    bull = state.get("bull_case") or []
    bear = state.get("bear_case") or []
    bull_latest = bull[-1].get("thesis", "") if bull else ""
    bear_latest = bear[-1].get("thesis", "") if bear else ""
    debate_table.add_row("Bull", str(len(bull)), _truncate(bull_latest, 60))
    debate_table.add_row("Bear", str(len(bear)), _truncate(bear_latest, 60))

    verdicts = state.get("debate_judgments") or []
    if verdicts:
        debate_table.add_row("", "", "")
        debate_table.add_row("Judge", str(len(verdicts)), _truncate(verdicts[0].get("rationale", ""), 60))

    prem_table = Table(title="Pre-mortem falsifiers", expand=True)
    prem_table.add_column("Symbol", width=8)
    prem_table.add_column("Fragility", width=10)
    prem_table.add_column("Top falsifier", width=50)
    for finding in (state.get("pre_mortem_findings") or [])[:5]:
        falsifiers = finding.get("falsifiers") or []
        top = falsifiers[0].get("failure_mode", "") if falsifiers else ""
        prem_table.add_row(
            str(finding.get("symbol", "")),
            f"{float(finding.get('overall_fragility', 0)):.2f}",
            _truncate(top, 50),
        )
    if not (state.get("pre_mortem_findings") or []):
        prem_table.add_row("—", "—", "(pending)")

    alloc_table = Table(title="Allocation", expand=True)
    alloc_table.add_column("Symbol", width=10)
    alloc_table.add_column("Weight %", width=10)
    alloc_table.add_column("Rationale", width=50)
    rec = state.get("portfolio_recommendation") or {}
    for row in (rec.get("allocations") or [])[:7]:
        alloc_table.add_row(
            str(row.get("symbol", "")),
            f"{float(row.get('allocation_pct', 0)):.1f}",
            _truncate(str(row.get("rationale", "")), 50),
        )
    if not (rec.get("allocations") or []):
        alloc_table.add_row("—", "—", "(pending)")

    reflection = state.get("reflection_summary") or {}
    reflection_text = reflection.get("summary_text") or ""
    reflection_panel = Panel(
        _truncate(reflection_text, 400) if reflection_text else "(no prior decisions graded yet)",
        title="Prior outcomes vs SPY",
        border_style="dim",
    )

    return Group(
        header,
        Panel(ideas_table, border_style="blue"),
        Panel(debate_table, border_style="magenta"),
        Panel(prem_table, border_style="red"),
        Panel(alloc_table, border_style="green"),
        reflection_panel,
    )


def stream_graph_with_tui(graph: Any, initial_state: dict[str, Any]) -> dict[str, Any]:
    from rich.live import Live

    final_state: dict[str, Any] = dict(initial_state)
    with Live(render_workflow_state(final_state), refresh_per_second=4, screen=True) as live:
        for state in graph.stream(initial_state, stream_mode="values"):
            final_state = state
            live.update(render_workflow_state(final_state))
    return final_state
