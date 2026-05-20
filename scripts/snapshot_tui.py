"""Render the current TUI to a text file using a synthesised final state.

Used to capture a baseline snapshot of `dolphi/tui/live.py:render_workflow_state`
for the Workstream A baseline-observations doc, without needing to drive the
interactive TUI through stdin.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from rich.console import Console

from dolphi.tui.live import render_workflow_state


def _state() -> dict:
    return {
        "ranked_ideas": [
            {"rank": 1, "symbol": "NVDA", "theme": "NVIDIA Related Opportunity Chain", "score": 0.66},
            {"rank": 2, "symbol": "CEG", "theme": "NVIDIA Related Opportunity Chain", "score": 0.56},
            {"rank": 3, "symbol": "ETN", "theme": "NVIDIA Related Opportunity Chain", "score": 0.56},
            {"rank": 4, "symbol": "NEE", "theme": "NVIDIA Related Opportunity Chain", "score": 0.56},
            {"rank": 5, "symbol": "VST", "theme": "NVIDIA Related Opportunity Chain", "score": 0.56},
        ],
        "bull_case": [
            {"thesis": "AI capex remains elevated; semis + power demand benefit.", "reasoning": "", "conviction": 0.75},
            {"thesis": "Rebuttal round 2: pricing power persists into 2026.", "reasoning": "", "conviction": 0.78},
        ],
        "bear_case": [
            {"thesis": "Concentration risk: top-10 weight at 33% leaves little headroom.", "reasoning": "", "conviction": 0.6},
            {"thesis": "Rebuttal round 2: Fed surprise + China ADR overhang.", "reasoning": "", "conviction": 0.55},
        ],
        "debate_judgments": [
            {"symbol": "NVDA", "winner": "bull", "conviction_delta": 0.20, "rationale": "Forward P/E and earnings growth defend the bull frame."},
            {"symbol": "CEG", "winner": "bull", "conviction_delta": 0.15, "rationale": "Data-center power demand supports the thesis."},
        ],
        "pre_mortem_findings": [
            {"symbol": "NVDA", "overall_fragility": 0.32, "falsifiers": [{"failure_mode": "Hyperscaler capex pause causes consensus EPS to fall >5% in a month", "probability": 0.30, "leading_indicator": "Refinitiv I/B/E/S NVDA FY+1 EPS revision", "breaks_assumption": "Forward P/E of 22x is consistent with 15% earnings growth", "horizon": "6 months"}]},
            {"symbol": "CEG", "overall_fragility": 0.23, "falsifiers": [{"failure_mode": "Rising rates compress utility valuations", "probability": 0.30, "leading_indicator": "EPS revision next 4Q", "breaks_assumption": "Forward P/E 22x is consistent with 15% growth", "horizon": "6 months"}]},
            {"symbol": "ETN", "overall_fragility": 0.22, "falsifiers": [{"failure_mode": "Copper input cost spike compresses gross margin", "probability": 0.30, "leading_indicator": "LME copper weekly", "breaks_assumption": "Pricing power persists", "horizon": "6 months"}]},
            {"symbol": "NEE", "overall_fragility": 0.30, "falsifiers": [{"failure_mode": "10y Treasury above 4.5% compresses P/E", "probability": 0.35, "leading_indicator": "Weekly UST10Y", "breaks_assumption": "Forward P/E 22x is consistent", "horizon": "6 months"}]},
            {"symbol": "VST", "overall_fragility": 0.25, "falsifiers": [{"failure_mode": "Wholesale electricity prices roll over", "probability": 0.30, "leading_indicator": "PJM West Hub weekly", "breaks_assumption": "Pricing power persists", "horizon": "6 months"}]},
        ],
        "portfolio_recommendation": {
            "allocations": [
                {"symbol": "NVDA", "allocation_pct": 16.6, "rationale": "NVIDIA leadership; pre-mortem fragility 0.32; bull debate delta +0.20"},
                {"symbol": "CEG", "allocation_pct": 14.8, "rationale": "Data-center power supplier; fragility 0.23; bull delta +0.15"},
                {"symbol": "ETN", "allocation_pct": 15.0, "rationale": "Electrical infrastructure; fragility 0.22; bull delta +0.15"},
                {"symbol": "NEE", "allocation_pct": 13.9, "rationale": "Renewable utility; fragility 0.30; bull delta +0.15"},
                {"symbol": "VST", "allocation_pct": 14.6, "rationale": "Power producer; fragility 0.25; bull delta +0.15"},
                {"symbol": "BND", "allocation_pct": 25.1, "rationale": "Defensive ballast based on the investor risk profile"},
            ],
            "notes": "Risk evaluation confirms moderate profile fit.",
        },
        "reflection_summary": {"summary_text": "No prior decisions graded yet."},
    }


def main() -> int:
    buf = io.StringIO()
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 140
    console = Console(file=buf, width=width, force_terminal=False, color_system=None, record=False)
    console.print(render_workflow_state(_state()))
    output = buf.getvalue()
    out_dir = Path("docs/tui")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"baseline_snapshot_{width}cols.txt"
    target.write_text(output, encoding="utf-8")
    print(f"Wrote {target}  ({len(output)} chars, {width} cols)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
