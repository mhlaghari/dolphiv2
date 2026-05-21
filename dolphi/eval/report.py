"""Eval report writers — markdown leaderboard + CSV + JSON audit trail."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import dolphi

from .harness import EvalReport
from .judge import _JUDGE_SYSTEM_PROMPT


def write_reports(report: EvalReport, output_dir: Path | str) -> dict[str, Path]:
    """Write all three report artifacts under ``output_dir``.

    Returns a dict ``{"markdown": ..., "csv": ..., "json": ...}`` mapping
    artifact kind to the path it was written to.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_path = out / "falsifier_quality.md"
    csv_path = out / "falsifier_quality.csv"
    json_path = out / "falsifier_quality.json"

    md_path.write_text(_render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    json_path.write_text(json.dumps(_as_audit_dict(report), indent=2), encoding="utf-8")

    return {"markdown": md_path, "csv": csv_path, "json": json_path}


def _render_markdown(report: EvalReport) -> str:
    rows = report.leaderboard()
    lines: list[str] = []
    lines.append("# Falsifier-quality leaderboard")
    lines.append("")
    lines.append(
        f"*Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
        f"Judge: `{report.judge_label}`. "
        f"Fixtures: {len(report.fixture_slugs)} (`{', '.join(report.fixture_slugs)}`). "
        f"Repeats per (model, fixture): {report.repeats}.*"
    )
    lines.append("")
    lines.append(
        "Each falsifier was graded on four axes (0–1 each). Aggregate is the mean. "
        "See `docs/technical-note.md` § 6 for the rubric."
    )
    lines.append("")
    lines.append("| Rank | Model | Aggregate | Horizon | Assumption | Indicator | Probability | Falsifiers | Latency (s) | Errors |")
    lines.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for i, row in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{row['model']}` | **{row['mean_aggregate']:.3f}** | "
            f"{row['horizon_observability']:.3f} | {row['assumption_coherence']:.3f} | "
            f"{row['indicator_specificity']:.3f} | {row['probability_calibration']:.3f} | "
            f"{row['n_falsifiers']} | {row['total_latency_seconds']:.1f} | {row['errors']} |"
        )
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("```bash")
    lines.append(
        f"python -m dolphi.eval --models {','.join(r['model'] for r in rows)} "
        f"--fixtures all --judge {report.judge_label} --repeats {report.repeats} "
        f"--out docs/eval/"
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "Raw per-falsifier rows: `falsifier_quality.csv`. "
        "Full prompt audit trail + raw model outputs: `falsifier_quality.json`."
    )
    lines.append("")
    return "\n".join(lines)


def _write_csv(report: EvalReport, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "model", "fixture_slug", "failure_mode", "horizon", "probability",
            "leading_indicator", "targeted_assumption",
            "horizon_observability", "assumption_coherence",
            "indicator_specificity", "probability_calibration",
            "aggregate", "comment",
        ])
        for result in report.results:
            for sf in result.scored_falsifiers:
                writer.writerow([
                    sf.model,
                    sf.fixture_slug,
                    sf.falsifier.get("failure_mode", ""),
                    sf.falsifier.get("horizon", ""),
                    sf.falsifier.get("probability", ""),
                    sf.falsifier.get("leading_indicator", ""),
                    sf.targeted_assumption,
                    f"{sf.score.horizon_observability:.3f}",
                    f"{sf.score.assumption_coherence:.3f}",
                    f"{sf.score.indicator_specificity:.3f}",
                    f"{sf.score.probability_calibration:.3f}",
                    f"{sf.score.aggregate:.3f}",
                    sf.score.comment,
                ])


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return "unknown"


def _build_manifest() -> dict:
    prompt_sha = hashlib.sha256(_JUDGE_SYSTEM_PROMPT.encode()).hexdigest()[:12]
    return {
        "judge_prompt_sha256": prompt_sha,
        "git_commit": _git_commit(),
        "dolphi_version": dolphi.__version__,
        "command": "python " + " ".join(sys.argv) if sys.argv else "python",
    }


def _as_audit_dict(report: EvalReport) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": _build_manifest(),
        "judge_label": report.judge_label,
        "fixture_slugs": report.fixture_slugs,
        "repeats": report.repeats,
        "leaderboard": report.leaderboard(),
        "per_model": [
            {
                "model": r.model,
                "fixtures_run": r.fixtures_run,
                "total_latency_seconds": round(r.total_latency_seconds, 3),
                "errors": r.errors,
                "scored_falsifiers": [
                    {
                        "fixture_slug": sf.fixture_slug,
                        "falsifier": dict(sf.falsifier),
                        "targeted_assumption": sf.targeted_assumption,
                        "score": sf.score.as_dict(),
                        "latency_seconds": round(sf.latency_seconds, 3),
                    }
                    for sf in r.scored_falsifiers
                ],
            }
            for r in report.results
        ],
    }
