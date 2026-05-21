"""Test that write_reports emits a reproducibility manifest in the JSON output."""

from __future__ import annotations

import json

from dolphi.eval.harness import EvalReport, ModelResult
from dolphi.eval.report import write_reports


def test_audit_json_contains_manifest(tmp_path):
    report = EvalReport(
        results=[ModelResult(model="stub:stub-model")],
        judge_label="stub:judge",
        fixture_slugs=["ai-capex"],
        repeats=1,
    )
    paths = write_reports(report, tmp_path)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))

    assert "manifest" in payload
    manifest = payload["manifest"]
    assert "judge_prompt_sha256" in manifest
    assert len(manifest["judge_prompt_sha256"]) == 12
    assert "git_commit" in manifest
    assert "dolphi_version" in manifest
    assert "command" in manifest
