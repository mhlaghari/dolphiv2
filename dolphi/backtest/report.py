"""Write backtest artefacts to disk (JSON metrics + SVG chart + summary markdown)."""

from __future__ import annotations

import json
from pathlib import Path

from .chart import render_equity_curve_svg
from .walk_forward import WalkForwardResult


def write_backtest_report(result: WalkForwardResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = output_dir / "walk_forward_metrics.json"
    svg_path = output_dir / "equity_curve.svg"
    summary_path = output_dir / "walk_forward_summary.md"

    payload = {
        "start_date": result.start_date,
        "end_date": result.end_date,
        "source": result.source,
        "periods": result.periods,
        "total_return_portfolio_pct": result.total_return_portfolio_pct,
        "total_return_spy_pct": result.total_return_spy_pct,
        "alpha_pct": result.alpha_pct,
        "max_drawdown_portfolio_pct": result.max_drawdown_portfolio_pct,
        "rebalance_dates": result.rebalance_dates,
        "portfolio_equity": result.portfolio_equity,
        "spy_equity": result.spy_equity,
        "period_returns_portfolio": result.period_returns_portfolio,
        "period_returns_spy": result.period_returns_spy,
        "notes": result.notes,
    }
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    svg_path.write_text(render_equity_curve_svg(result), encoding="utf-8")

    alpha_sign = "+" if result.alpha_pct >= 0 else ""
    summary = f"""# Walk-forward backtest summary

| Metric | Value |
|--------|------:|
| Window | {result.start_date} → {result.end_date} |
| Source | `{result.source}` |
| Hold periods | {result.periods} |
| Portfolio return | {result.total_return_portfolio_pct:+.2f}% |
| SPY return | {result.total_return_spy_pct:+.2f}% |
| Alpha vs SPY | {alpha_sign}{result.alpha_pct:.2f}% |
| Max drawdown (portfolio) | {result.max_drawdown_portfolio_pct:.2f}% |

![Equity curve](equity_curve.svg)

> Sanity-check only. Past simulated performance of logged allocations does not
> guarantee future results. Not financial advice.
"""
    if result.notes:
        summary += "\n## Notes\n\n" + "\n".join(f"- {note}" for note in result.notes[:10]) + "\n"

    summary_path.write_text(summary, encoding="utf-8")

    return {
        "metrics": metrics_path,
        "svg": svg_path,
        "summary": summary_path,
    }
