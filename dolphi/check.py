"""``dolphi --check`` — the retention loop.

Loads the most recent decision from ``~/.dolphi/decision_log.jsonl``,
walks the user through every falsifier the pre-mortem agent named
(each one comes with a weekly-checkable leading indicator), and
classifies each as ``safe`` / ``triggered`` / ``unsure``. The summary
recommends position-size adjustments for any symbol whose falsifiers
fired.

This is the part that turns the agent from "useful once" into "open
every Monday." The pre-mortem prompt is already designed to produce
weekly-checkable indicators — this module just surfaces them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import click
from rich.box import HEAVY_HEAD, ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .banner import print_banner

logger = logging.getLogger(__name__)


Status = Literal["safe", "triggered", "unsure"]

# How much to shave off a position when one of its falsifiers fires. The
# fragility multiplier in the allocator is the real arithmetic; this is
# a per-check heuristic for "here's what you should do today."
_TRIGGER_DISCOUNT = 0.30   # 30% reduction per triggered falsifier
_UNSURE_DISCOUNT = 0.10    # 10% nudge per unsure


@dataclass
class _Indicator:
    symbol: str
    fragility: float
    weight_pct: float
    falsifier_index: int
    failure_mode: str
    probability: float
    horizon: str
    leading_indicator: str
    breaks_assumption: str
    status: Status | None = None


@dataclass
class CheckResult:
    decision_date: str
    indicators: list[_Indicator] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.indicators)

    @property
    def n_safe(self) -> int:
        return sum(1 for i in self.indicators if i.status == "safe")

    @property
    def n_triggered(self) -> int:
        return sum(1 for i in self.indicators if i.status == "triggered")

    @property
    def n_unsure(self) -> int:
        return sum(1 for i in self.indicators if i.status == "unsure")

    def adjustment_by_symbol(self) -> dict[str, tuple[float, float, str]]:
        """Return ``{symbol: (old_weight, new_weight, note)}``.

        Heuristic: each triggered falsifier shaves 30% off the position;
        each unsure shaves 10%. Capped at 90% reduction.
        """
        by_symbol: dict[str, list[_Indicator]] = {}
        for ind in self.indicators:
            by_symbol.setdefault(ind.symbol, []).append(ind)
        out: dict[str, tuple[float, float, str]] = {}
        for symbol, items in by_symbol.items():
            triggered = sum(1 for i in items if i.status == "triggered")
            unsure = sum(1 for i in items if i.status == "unsure")
            if not triggered and not unsure:
                continue
            old = items[0].weight_pct
            multiplier = max(0.10, 1.0 - _TRIGGER_DISCOUNT * triggered - _UNSURE_DISCOUNT * unsure)
            new = old * multiplier
            parts = []
            if triggered:
                parts.append(f"{triggered} triggered (-{_TRIGGER_DISCOUNT * triggered * 100:.0f}%)")
            if unsure:
                parts.append(f"{unsure} unsure (-{_UNSURE_DISCOUNT * unsure * 100:.0f}%)")
            out[symbol] = (old, new, ", ".join(parts))
        return out


# ---------- decision log loading ----------------------------------------------


def load_latest_decision(jsonl_path: Path) -> dict | None:
    """Return the most recent JSONL record, or None if the file is missing/empty.

    Skips legacy records that don't carry the full ``pre_mortem_findings``
    field (added in v0.2.0). If only legacy records exist, this returns
    ``None`` and the CLI surfaces a useful error message.
    """
    if not jsonl_path.exists():
        return None
    latest_full: dict | None = None
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "pre_mortem_findings" in record:
                latest_full = record
    return latest_full


# ---------- main flow ---------------------------------------------------------


def _weight_by_symbol(allocations: list[dict]) -> dict[str, float]:
    by_symbol: dict[str, float] = {}
    for item in allocations or []:
        symbol = item.get("symbol")
        if symbol:
            by_symbol[symbol] = float(item.get("allocation_pct", 0.0) or 0.0)
    return by_symbol


def _build_indicators(decision: dict) -> list[_Indicator]:
    weights = _weight_by_symbol(decision.get("allocations", []))
    out: list[_Indicator] = []
    for finding in decision.get("pre_mortem_findings", []) or []:
        symbol = finding.get("symbol", "")
        fragility = float(finding.get("overall_fragility", 0.0) or 0.0)
        weight = weights.get(symbol, 0.0)
        for idx, falsifier in enumerate(finding.get("falsifiers", []) or [], 1):
            out.append(_Indicator(
                symbol=symbol,
                fragility=fragility,
                weight_pct=weight,
                falsifier_index=idx,
                failure_mode=str(falsifier.get("failure_mode", "")),
                probability=float(falsifier.get("probability", 0.0) or 0.0),
                horizon=str(falsifier.get("horizon", "")),
                leading_indicator=str(falsifier.get("leading_indicator", "")),
                breaks_assumption=str(falsifier.get("breaks_assumption", "")),
            ))
    return out


def _fragility_style(value: float) -> str:
    if value >= 0.5:
        return "bold red"
    if value >= 0.25:
        return "bold yellow"
    return "bold green"


def _status_prompt(console: Console, label: str) -> Status:
    console.print(
        Text("  Status? ", style="bold")
        + Text("[S]till safe  ", style="green")
        + Text("[T]riggered  ", style="red")
        + Text("[U]nsure", style="yellow")
        + Text(f"  ({label})", style="dim")
    )
    while True:
        raw = click.prompt("  >", default="S", show_default=True).strip().upper()
        if raw in ("S", "SAFE"):
            return "safe"
        if raw in ("T", "TRIGGERED"):
            return "triggered"
        if raw in ("U", "UNSURE"):
            return "unsure"
        console.print("  [yellow]Enter S, T, or U.[/yellow]")


def _print_header(console: Console, decision: dict) -> None:
    decision_date = decision.get("decision_date") or decision.get("timestamp", "")[:10]
    try:
        decision_dt = datetime.fromisoformat(decision.get("timestamp", "").replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - decision_dt
        hours = int(age.total_seconds() // 3600)
        age_str = f"{hours} hour(s) ago" if hours < 48 else f"{hours // 24} day(s) ago"
    except (ValueError, TypeError):
        age_str = "age unknown"

    profile_risk = decision.get("profile_risk", "?")
    profile_goal = decision.get("profile_goal", "?")
    n_positions = len([a for a in decision.get("allocations", []) if a.get("symbol") not in ("CASH", "BND")])
    n_indicators = sum(
        len(finding.get("falsifiers", []) or [])
        for finding in decision.get("pre_mortem_findings", []) or []
    )

    intro = Text.assemble(
        ("Most recent decision: ", "dim"),
        (decision_date, "bold bright_white"),
        ("  (", "dim"),
        (age_str, "cyan"),
        (")", "dim"),
        "\n",
        ("Profile: ", "dim"),
        (f"{profile_risk} · {profile_goal}", "bright_white"),
        "\n",
        ("Tracking: ", "dim"),
        (f"{n_positions} positions, {n_indicators} indicators to verify", "bright_white"),
    )
    console.print(Panel(intro, border_style="cyan", title="🔍 falsifier check", title_align="left"))
    console.print()


def _print_indicator(console: Console, ind: _Indicator, idx: int, total: int) -> None:
    weight_str = f"{ind.weight_pct:.1f}%"
    frag_text = Text(f"{ind.fragility:.2f}", style=_fragility_style(ind.fragility))
    title = Text.assemble(
        (f"  {idx}/{total}  ", "dim"),
        (ind.symbol, "bold bright_cyan"),
        ("    weight ", "dim"),
        (weight_str, "bright_white"),
        ("    fragility ", "dim"),
        frag_text,
        (f"    falsifier #{ind.falsifier_index}/3", "dim"),
    )
    console.print(title)
    console.print(
        Text("    💥 ", style="red")
        + Text(ind.failure_mode, style="bright_white")
    )
    meta = Text.assemble(
        ("    p=", "dim"),
        (f"{ind.probability:.2f}", "bright_yellow"),
        ("   horizon: ", "dim"),
        (ind.horizon or "unspecified", "bright_white"),
    )
    console.print(meta)
    if ind.leading_indicator:
        console.print(Text("    📌 watch: ", style="cyan") + Text(ind.leading_indicator, style="bright_white"))
    if ind.breaks_assumption:
        console.print(Text("    🎯 breaks: ", style="magenta") + Text(ind.breaks_assumption, style="dim italic"))


def _print_summary(console: Console, result: CheckResult) -> None:
    console.print()
    summary = Table(box=HEAVY_HEAD, show_header=False, expand=False, pad_edge=False)
    summary.add_column(style="bold")
    summary.add_column(justify="right", style="bright_white")
    summary.add_row(Text("✓ still safe", style="green"), str(result.n_safe))
    summary.add_row(Text("⚠ triggered", style="red"), str(result.n_triggered))
    summary.add_row(Text("? unsure", style="yellow"), str(result.n_unsure))
    summary.add_row(Text("total", style="dim"), str(result.total))
    console.print(Panel(summary, border_style="cyan", title="summary", title_align="left"))

    adjustments = result.adjustment_by_symbol()
    if not adjustments:
        console.print(
            Panel(
                Text("All indicators still safe. Holding current allocation.", style="green"),
                border_style="green",
                title="action",
                title_align="left",
            )
        )
        return

    table = Table(box=ROUNDED, expand=False)
    table.add_column("symbol", style="bold bright_cyan")
    table.add_column("current %", justify="right")
    table.add_column("suggested %", justify="right", style="bold")
    table.add_column("reason", style="dim")
    for symbol, (old, new, note) in adjustments.items():
        arrow_style = "red" if new < old else "green"
        table.add_row(
            symbol,
            f"{old:.1f}",
            Text(f"{new:.1f}", style=arrow_style),
            note,
        )
    console.print(Panel(table, border_style="yellow", title="position-size suggestions", title_align="left"))
    console.print(
        Text("\nNext: ", style="dim")
        + Text("dolphi", style="bold bright_cyan")
        + Text(" to generate a fresh decision incorporating these triggers.\n", style="dim")
    )


def run_check(*, jsonl_path: Path | None = None, console: Console | None = None) -> int:
    """Entry point used by the CLI.

    Returns 0 on success, 1 if no usable decision was found.
    """
    target_console = console or Console()
    print_banner(target_console, subtitle="🔍 falsifier check — Mondays were made for this")
    target_console.print()

    target = jsonl_path if jsonl_path else Path.home() / ".dolphi" / "decision_log.jsonl"
    decision = load_latest_decision(target)
    if decision is None:
        target_console.print(
            Panel(
                Text.assemble(
                    "No decision log with full falsifier data was found at ",
                    (str(target), "bold"),
                    ".\n\nRun ", ("dolphi", "bold bright_cyan"),
                    " (without --check) first to produce a decision, then come back here on Monday.",
                ),
                border_style="red",
                title="no decision to check",
                title_align="left",
            )
        )
        return 1

    _print_header(target_console, decision)
    indicators = _build_indicators(decision)
    if not indicators:
        target_console.print("[yellow]No falsifiers in the latest decision — nothing to check.[/yellow]")
        return 1

    result = CheckResult(decision_date=decision.get("decision_date", ""))
    result.indicators = indicators

    for i, ind in enumerate(indicators, 1):
        _print_indicator(target_console, ind, i, len(indicators))
        ind.status = _status_prompt(target_console, f"{ind.symbol} #{ind.falsifier_index}")
        target_console.print()

    _print_summary(target_console, result)
    return 0
