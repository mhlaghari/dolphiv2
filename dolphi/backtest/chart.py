"""SVG equity-curve chart — stdlib only, no matplotlib."""

from __future__ import annotations

from .walk_forward import WalkForwardResult


def render_equity_curve_svg(
    result: WalkForwardResult,
    *,
    width: int = 720,
    height: int = 320,
    title: str = "Dolphi walk-forward vs SPY",
) -> str:
    portfolio = result.portfolio_equity
    spy = result.spy_equity
    if len(portfolio) < 2 or len(spy) < 2:
        return _empty_chart_svg(title, width, height, "Not enough data points")

    dates = result.rebalance_dates
    if len(dates) != len(portfolio):
        dates = [str(i) for i in range(len(portfolio))]

    pad_left, pad_right, pad_top, pad_bottom = 56, 24, 36, 44
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    all_vals = portfolio + spy
    y_min = min(all_vals)
    y_max = max(all_vals)
    if y_max == y_min:
        y_max = y_min + 1.0

    def x_at(index: int) -> float:
        if len(portfolio) == 1:
            return pad_left
        return pad_left + index / (len(portfolio) - 1) * plot_w

    def y_at(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return pad_top + plot_h - ratio * plot_h

    def polyline(values: list[float]) -> str:
        points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
        return points

    y100 = y_at(100.0)
    alpha_sign = "+" if result.alpha_pct >= 0 else ""
    subtitle = (
        f"{result.start_date} → {result.end_date} · "
        f"portfolio {result.total_return_portfolio_pct:+.1f}% · "
        f"SPY {result.total_return_spy_pct:+.1f}% · "
        f"alpha {alpha_sign}{result.alpha_pct:.1f}%"
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <rect width="100%" height="100%" fill="#0f1419"/>
  <text x="{pad_left}" y="22" fill="#e6edf3" font-family="Segoe UI, system-ui, sans-serif" font-size="14" font-weight="600">{title}</text>
  <text x="{pad_left}" y="38" fill="#8b949e" font-family="Segoe UI, system-ui, sans-serif" font-size="11">{subtitle}</text>
  <line x1="{pad_left}" y1="{y100:.1f}" x2="{width - pad_right}" y2="{y100:.1f}" stroke="#30363d" stroke-dasharray="4 4"/>
  <text x="{pad_left - 8}" y="{y100 + 4:.1f}" fill="#8b949e" font-family="monospace" font-size="10" text-anchor="end">100</text>
  <polyline fill="none" stroke="#58a6ff" stroke-width="2.5" points="{polyline(spy)}"/>
  <polyline fill="none" stroke="#3fb950" stroke-width="2.5" points="{polyline(portfolio)}"/>
  <circle cx="{x_at(len(portfolio) - 1):.1f}" cy="{y_at(portfolio[-1]):.1f}" r="4" fill="#3fb950"/>
  <circle cx="{x_at(len(spy) - 1):.1f}" cy="{y_at(spy[-1]):.1f}" r="4" fill="#58a6ff"/>
  <rect x="{pad_left}" y="{height - 28}" width="12" height="3" fill="#3fb950"/>
  <text x="{pad_left + 18}" y="{height - 20}" fill="#c9d1d9" font-family="Segoe UI, system-ui, sans-serif" font-size="11">Dolphi allocations</text>
  <rect x="{pad_left + 160}" y="{height - 28}" width="12" height="3" fill="#58a6ff"/>
  <text x="{pad_left + 178}" y="{height - 20}" fill="#c9d1d9" font-family="Segoe UI, system-ui, sans-serif" font-size="11">SPY buy-and-hold</text>
  <text x="{pad_left}" y="{height - 6}" fill="#6e7681" font-family="monospace" font-size="10">{dates[0]}</text>
  <text x="{width - pad_right}" y="{height - 6}" fill="#6e7681" font-family="monospace" font-size="10" text-anchor="end">{dates[-1]}</text>
</svg>"""


def _empty_chart_svg(title: str, width: int, height: int, message: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#0f1419"/>
  <text x="24" y="32" fill="#e6edf3" font-family="Segoe UI, sans-serif" font-size="14">{title}</text>
  <text x="24" y="56" fill="#8b949e" font-family="Segoe UI, sans-serif" font-size="12">{message}</text>
</svg>"""
