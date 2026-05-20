from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sidecar_path(markdown_path: Path) -> Path:
    """Return a sibling .jsonl path next to the markdown decision log."""
    return markdown_path.with_suffix(".jsonl")


def _write_sidecar(
    path: Path,
    timestamp: str,
    profile: dict[str, Any],
    ranked_ideas: list[dict[str, Any]],
    recommendation: dict[str, Any],
    debate_judgments: list[dict[str, Any]] | None,
    pre_mortem_findings: list[dict[str, Any]] | None,
) -> None:
    record = {
        "timestamp": timestamp,
        "decision_date": timestamp[:10],
        "profile_risk": profile.get("risk_tolerance"),
        "profile_goal": profile.get("goal"),
        "allocations": [
            {
                "symbol": item.get("symbol"),
                "allocation_pct": float(item.get("allocation_pct", 0.0)),
            }
            for item in recommendation.get("allocations", [])
            if item.get("symbol")
        ],
        "ranked_ideas": [
            {
                "symbol": item.get("symbol"),
                "score": item.get("score"),
                "theme": item.get("theme"),
            }
            for item in ranked_ideas[:5]
        ],
        "debate_judgments": [
            {
                "symbol": item.get("symbol"),
                "winner": item.get("winner"),
                "conviction_delta": item.get("conviction_delta"),
            }
            for item in (debate_judgments or [])
        ],
        "pre_mortem_summary": [
            {
                "symbol": item.get("symbol"),
                "fragility": item.get("overall_fragility"),
            }
            for item in (pre_mortem_findings or [])
        ],
        # v0.2.0+ — full falsifier data so `dolphi --check` can revisit indicators
        # without parsing the markdown log. Older runs may omit this field.
        "pre_mortem_findings": [
            {
                "symbol": item.get("symbol"),
                "overall_fragility": item.get("overall_fragility"),
                "falsifiers": [
                    {
                        "failure_mode": f.get("failure_mode", ""),
                        "probability": float(f.get("probability", 0.0)),
                        "leading_indicator": f.get("leading_indicator", ""),
                        "breaks_assumption": f.get("breaks_assumption", ""),
                        "horizon": f.get("horizon", ""),
                    }
                    for f in (item.get("falsifiers") or [])
                ],
            }
            for item in (pre_mortem_findings or [])
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")


def append_decision_log(
    path: Path,
    profile: dict[str, Any],
    ranked_ideas: list[dict[str, Any]],
    theme_clusters: list[dict[str, Any]],
    recommendation: dict[str, Any],
    pre_mortem_findings: list[dict[str, Any]] | None = None,
    debate_judgments: list[dict[str, Any]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_sidecar(
        _sidecar_path(path),
        timestamp,
        profile,
        ranked_ideas,
        recommendation,
        debate_judgments,
        pre_mortem_findings,
    )
    lines = [
        f"## Run {timestamp}",
        "",
        f"- Risk: {profile.get('risk_tolerance', 'unknown')}",
        f"- Goal: {profile.get('goal', 'unknown')}",
        "",
        "### Discovered Ideas",
    ]
    for idea in ranked_ideas[:10]:
        lines.append(
            f"- {idea.get('rank')}. {idea.get('symbol')} | theme={idea.get('theme')} "
            f"| score={idea.get('score')} | confidence={idea.get('confidence')}"
        )

    lines.extend(["", "### Theme Chains"])
    for cluster in theme_clusters[:5]:
        related = ", ".join(item.get("symbol", "") for item in cluster.get("related_symbols", [])[:8])
        lines.append(f"- {cluster.get('seed_symbol')}: {cluster.get('theme')} -> {related or 'no validated related symbols'}")
        if cluster.get("thesis"):
            lines.append(f"  - Thesis: {cluster.get('thesis')}")
        if cluster.get("source_urls"):
            lines.append(f"  - Sources: {', '.join(cluster.get('source_urls', [])[:5])}")
        for relation in cluster.get("related_symbols", [])[:5]:
            if relation.get("evidence"):
                lines.append(
                    f"  - Evidence for {relation.get('symbol')}: "
                    f"{relation.get('evidence')}"
                )

    if debate_judgments:
        lines.extend(["", "### Debate Verdicts"])
        for item in debate_judgments:
            delta = float(item.get("conviction_delta", 0))
            sign = "+" if delta > 0 else ""
            lines.append(
                f"- {item.get('symbol')}: winner={item.get('winner')} "
                f"delta={sign}{delta:.2f} :: {item.get('rationale', '')}"
            )

    if pre_mortem_findings:
        lines.extend(["", "### Pre-Mortem (Falsifiers)"])
        for finding in pre_mortem_findings:
            falsifiers = finding.get("falsifiers", []) or []
            lines.append(
                f"- {finding.get('symbol')} (fragility "
                f"{float(finding.get('overall_fragility', 0)):.2f}):"
            )
            for item in falsifiers[:3]:
                horizon = item.get("horizon", "")
                horizon_tag = f" [{horizon}]" if horizon else ""
                lines.append(
                    f"  - p={float(item.get('probability', 0)):.2f}{horizon_tag} — "
                    f"{item.get('failure_mode', '')}"
                )
                breaks = item.get("breaks_assumption", "")
                if breaks:
                    lines.append(f"    breaks: {breaks}")
                indicator = item.get("leading_indicator", "")
                if indicator:
                    lines.append(f"    watch:  {indicator}")

    lines.extend(["", "### Final Allocation"])
    for allocation in recommendation.get("allocations", []):
        lines.append(f"- {allocation.get('symbol')}: {allocation.get('allocation_pct')}%")
    if recommendation.get("notes"):
        lines.extend(["", f"Notes: {recommendation.get('notes')}"])
    lines.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")
