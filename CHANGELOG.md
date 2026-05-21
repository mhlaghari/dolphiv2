# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-21

### Added

- **`dolphi.api` library facade** — `from dolphi import evaluate, check_falsifiers, list_falsifiers, get_decision_log` exposes the engine as a Python library so other trading agents can call Dolphi directly. Pydantic v2 models (`EvaluateResult`, `Falsifier`, `RankedIdea`, `DebateJudgment`, `Allocation`, `CheckResult`, `UserProfile`). Sync API; `mock=True` runs offline without API keys.
- **`dolphi-mcp` server** — stdio MCP server exposing four tools (`dolphi_evaluate`, `dolphi_check_falsifiers`, `dolphi_list_falsifiers`, `dolphi_get_decision_log`) to Claude Desktop, Cursor, and any MCP client. Install with `pip install "dolphi[mcp]"`. Wiring guide at `docs/mcp.md`.
- **Cookbook notebook** — `examples/01_evaluate_a_ticker.ipynb` runs the full pipeline offline in ~2 seconds (bull/bear debate, falsifiers, fragility, allocation, falsifier-check loop).
- **One-command demo** — `bash examples/quickstart.sh` installs and runs Dolphi in mock mode end-to-end.
- **First real falsifier-quality leaderboard** — `docs/eval/falsifier_quality.{md,csv,json}` benchmarks `deepseek-v4-pro` and `deepseek-v4-flash` across all 8 fixtures, judged by `deepseek-v4-pro`. Flash beats Pro on aggregate (0.838 vs 0.787). Audit JSON includes a `manifest` block (judge prompt SHA, git commit, dolphi version, exact command) for independent reproducibility.
- **OSS hygiene** — `SECURITY.md` (disclosure policy + response SLA), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).

### Changed

- **README reframed** as a thesis-interrogation primitive (library + MCP + CLI) rather than as a trading-agent-adjacent tool. New Glossary section, "Why this exists" surfaced before the changelog.
- `dolphi.check.compute_adjustments(decision, feedback)` extracted as a pure function so the CLI and the library share the same falsifier-adjustment math.

### Deprecated

- `alpha_vantage` data source — moved to `dolphi/experimental/`, removed from `Config`, `DataFetcher`, and the CLI. yfinance is now the sole price/financials source; the yfinance→alpha_vantage fallback is gone. Module will be removed in 0.4.

### Removed

- `Config.alpha_vantage_key` field and the `ALPHA_VANTAGE_KEY` environment-variable plumbing.

## [0.2.0] - 2026-05-21

### Added

- `dolphi --check` retention loop — loads the most recent decision, walks every leading indicator the pre-mortem named, prompts `[S]till safe / [T]riggered / [U]nsure` per falsifier, then suggests position-size adjustments per symbol.
- Colourful CLI — DOLPHI ASCII banner at every entry point; Rich-styled portfolio table with fragility-graded weight column (green/yellow/red) and bull/bear conviction-delta cells.
- UAE markets — 28 of the largest DFM + ADX listings (IHC, FAB, TAQA, ADNOC Gas/Dist, EMAAR, DEWA, ENBD, …) ranked alongside US names via `dolphi --include-uae`.
- Falsifier-quality eval harness — `python -m dolphi.eval` benchmarks LLMs on horizon observability, assumption coherence, indicator specificity, and probability calibration, emitting markdown / CSV / JSON leaderboards.
- Saved investor profile at `~/.dolphi/profile.json` with hotkey prompts (`[U]SD / [E]UR / [G]BP / [A]ED / …`) and a `[Y]es / [E]dit / [N]ew` flow on every run.
- `investment_percentage` field — choose what fraction of savings to deploy; the rest stays as cash buffer outside the strategy and shows up as a separate line.

### Deprecated

- `alpha_vantage` data source — `yfinance` provides equivalent coverage; will be removed in 0.3.

## [0.1.0]

### Added

- Initial release.
- Open universe loader.
- Per-ticker analyst outputs.
- Pre-Mortem stub.
- Rebrand to dolphi.
