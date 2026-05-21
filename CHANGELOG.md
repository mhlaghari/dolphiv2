# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
