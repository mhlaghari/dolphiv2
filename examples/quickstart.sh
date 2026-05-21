#!/usr/bin/env bash
set -euo pipefail
# Dolphi quickstart — runs offline, no API keys, ~30 seconds.
# See README.md for the full guide.

cd "$(dirname "$0")/.."

echo "==> Installing dolphi in editable mode..."
pip install -e ".[dev]" >/dev/null

echo "==> Running mock-data evaluation on NVDA..."
dolphi --new-profile --mock-data --seed-symbol NVDA --top-k 5 | tee examples/sample_output.txt

echo
echo "==> Done."
echo "    Decision log written to: ~/.dolphi/decision_log.jsonl"
echo "    Sample output saved to:  examples/sample_output.txt"
echo "    Re-run the falsifier check with: dolphi --check"
