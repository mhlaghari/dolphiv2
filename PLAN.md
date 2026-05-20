# Dolphi — Sharpening Plan

> Dolphi is the multi-agent investment researcher that **proves itself wrong before it
> recommends anything**.

This document is the single source of truth for where the project is going, why,
and what each phase ships. It is meant to be read top to bottom in five minutes.

For research and education only. Not financial advice.

---

## Positioning

| | TradingAgents | Dolphi |
|---|---|---|
| Question answered | "Should I buy `<ticker>` on `<date>`?" | "What should I even consider, and where is the thesis weakest?" |
| Input | Ticker the user already chose | User's risk profile + open universe |
| Output | Buy / hold / sell on that ticker | Ranked ideas + allocation + **explicit falsifiers per idea** |
| Unique step | Bull/bear debate | Bull/bear debate **+ Pre-Mortem Agent** (cheapest event that kills the thesis) |
| Deployment story | Lots of LLM providers, lots of data sources | Local-first (Ollama default), free data sources by default |

The viral wedge is the **Pre-Mortem Agent**: a dedicated node whose only job
is to break each thesis by naming the cheapest, fastest, most observable event
that would falsify it. Bull/bear is forecasting against forecasting.
Pre-mortem is forecasting against reality.

---

## Architecture (target)

```
User profile
    │
    ▼
Universe loader  ◄──── NASDAQ/NYSE listings (cached, liquidity-filtered)
    │
    ▼
Research sources (RSS, NewsAPI, Brave, SearXNG, static)
    │
    ▼
Narrative discovery   ◄── Phase 1: LLM-driven clustering replaces keyword buckets
    │
    ▼
Theme graph           ◄── Phase 1: LLM proposes beneficiaries → validated → evidence pass
    │
    ▼
Candidate ranker (deterministic, transparent score breakdown)
    │
    ▼
Analyst team — PER TICKER
    ├── Technical    → {SYM: {reasoning, score, details}, ...}
    ├── Fundamental  → {SYM: {...}, ...}
    └── Sentiment    → {SYM: {...}, ...}
    │
    ▼
Bull ⇄ Bear debate (Phase 1: real multi-round, judge node emits conviction delta)
    │
    ▼
Pre-Mortem Agent   ◄── THE WEDGE
    For each idea: 3 cheapest falsifiers, each with probability + leading indicator
    │
    ▼
Risk evaluators (Aggressive | Conservative) — review full thesis incl. pre-mortem
    │
    ▼
Portfolio Manager
    Deterministic allocator + LLM rationale, per-position pre-mortem column
    │
    ▼
Decision log + closed-loop reflection (Phase 1: fetch realized return vs SPY next run)
```

---

## Phase 0 — Credibility (this milestone)

Foundational. Nothing in Phase 1 is worth doing until these are in place,
because each one is a credibility-killer on its own. None of it is risky;
all of it is mechanical.

**P0.1 — Brand & rename**
- Rename Python package `portfolio_agent` → `dolphi`.
- Console script `portfolio-agent` → `dolphi`.
- `pyproject.toml` project name `portfolio-agent` → `dolphi`.
- All imports across `dolphi/` and `tests/` updated.

**P0.2 — Open universe**
- New `dolphi/universe/loader.py`:
  - Pulls NASDAQ-listed and NYSE/AMEX-listed files from
    `ftp.nasdaqtrader.com/SymbolDirectory` (HTTPS mirror), pipe-delimited,
    no API key required.
  - Liquidity filter: keep symbols with 90-day avg dollar volume above a
    configurable floor (default $5M).
  - Bundled fallback CSV under `dolphi/universe/data/us_listed.csv` so the
    first run works offline.
  - Resulting universe replaces the hardcoded 27-symbol allowlist except in
    `--mock-data` mode, where the curated list remains the demo universe.
- `universe()` is the only entry point; callers stop seeing the underlying source.

**P0.3 — Per-ticker analyst outputs**
- `AgentState` gains a new field:
  ```python
  per_ticker_analysis: dict[str, dict[str, AnalystOutput]]
  # symbol → {"technical": ..., "fundamental": ..., "sentiment": ...}
  ```
- Each analyst now emits a structured per-ticker dict in a single LLM call.
  Prompt enumerates each candidate symbol; system prompt forces the
  per-symbol JSON shape.
- The global `technical_analysis` / `fundamental_analysis` / `sentiment_analysis`
  fields are kept (computed as the mean per-ticker score) for backward
  compatibility and as a market-context summary.
- Bull, bear, risk, and portfolio_manager prompts gain per-ticker context.

**P0.4 — Pre-Mortem agent stub**
- New node `dolphi/agents/pre_mortem.py` and a `pre_mortem_findings`
  field on `AgentState`.
- For Phase 0 the prompt is intentionally simple ("list 3 falsifiers per
  recommended symbol"). Phase 1 turns it into the real wedge.

**P0.5 — README rewrite**
- New tagline.
- Mermaid architecture diagram (not ASCII).
- "vs TradingAgents" comparison table (the one in this doc).
- "Local-first, free by default" install block.
- Mock-data quickstart that produces a deterministic example output.

**P0.6 — Tests + CI green**
- Update existing tests to the new import path and per-ticker shape.
- `pytest` must pass before declaring Phase 0 done.

**Done when:** `pipx install -e .` followed by `dolphi --mock-data --seed-symbol NVDA --top-k 5` runs end-to-end, prints per-ticker analyst reasoning, prints a Pre-Mortem stub block per recommended symbol, and `pytest` is green.

---

## Phase 1 — The viral wedge ✅ shipped

All four lanes landed. 111 tests pass; ruff clean. The agent now:

**P1.1 — Real Pre-Mortem agent** (`dolphi/agents/pre_mortem.py`).
- Step 1: one LLM call extracts the 3-5 *load-bearing assumptions*
  implicit in the bull thesis. The thesis itself is never shown to the
  per-symbol falsifier prompt, so the attacker is not contaminated by
  the defender's framing.
- Step 2: for each of the top-K ranked ideas, a per-symbol LLM call
  produces exactly 3 falsifiers. Each falsifier is forced to
  (a) name one assumption it breaks from the extracted list, (b) name
  a horizon ≤ 12 months, and (c) name a weekly-checkable leading
  indicator. Unmatched `breaks_assumption` strings are coerced to the
  closest extracted assumption rather than dropped.
- The allocator down-weights ideas by their average falsifier
  probability (`fragility`) as a multiplier on score.

**P1.2 — LLM-driven theme graph** (`dolphi/research/beneficiaries.py`).
- The hard-coded `_RELATION_KEYWORDS` table is kept as a fallback;
  when an LLM is available, the mapper now asks the model to propose
  5-8 US-listed beneficiary tickers per narrative.
- Every proposed ticker is universe-validated (unknown tickers and
  asset-class-disallowed tickers are silently dropped) and confidence
  is clamped and scaled by the narrative's own confidence.
- Falls back to the keyword path per-narrative on LLM error so a
  flaky model never wipes out the discovery layer.

**P1.3 — Multi-round debate + judge** (`dolphi/agents/debate.py`,
`dolphi/agents/debate_judge.py`).
- After the opening bull/bear pass, the `debate` node runs N
  configurable rebuttal rounds (default 2). Each round writes a new
  `ResearcherOutput` into `bull_case`/`bear_case` so every turn is
  preserved.
- The `debate_judge` node reads the full transcript and emits a
  per-symbol `DebateJudgment` with `winner ∈ {bull, bear, tie}` and a
  bounded `conviction_delta ∈ [-0.3, 0.3]`. Ties are coerced to delta=0.
- The deterministic allocator adds the delta to each idea's score
  *before* applying the fragility multiplier, so debate and pre-mortem
  compose. Cost: `2 * rounds + 1` extra LLM calls (5 for `rounds=2`).

**P1.4 — Closed-loop reflection** (`dolphi/memory/reflection.py`,
`dolphi/memory/decision_log.py`).
- Every decision now writes a machine-readable `.jsonl` sidecar next
  to the human-readable `.md` decision log.
- On run start, the CLI loads up to 5 prior decisions older than 14
  days (and younger than 540 days), refetches realised closes for each
  allocated symbol plus SPY, and computes per-symbol and
  portfolio-level alpha. The summary is injected into the portfolio
  manager's prompt under `=== PRIOR DECISION OUTCOMES ===` so the
  agent must address its own track record before issuing new calls.
- Cash positions are skipped; symbols whose prices can't be fetched
  are dropped silently per-decision.

**Done when:** ✅ `pytest` shows 111 passing tests covering every new
agent and the new allocator behaviour; ✅ `ruff` is clean.

---

## Phase 1 — Costs to be aware of

Per discovery run with `top_k = 5` and `debate_rounds = 2`:

| Step | Approx LLM calls | Notes |
|---|---|---|
| Per-ticker analysts | 3 | Tech/Fund/Sent each produce one structured call |
| Bull + Bear opening | 2 | Unchanged from Phase 0 |
| Debate rebuttals | 4 | `2 * rounds` |
| Debate judge | 1 | One global judgment call |
| Pre-Mortem assumptions | 1 | Skipped if no bull case is present |
| Pre-Mortem per symbol | 5 | One per top-K idea |
| Risk (aggressive / conservative) | 2 | Unchanged |
| Theme beneficiaries | ≤ 7 | One per discovered narrative, capped at 5-8 ideas |
| Portfolio manager | 1 | Final synthesis |
| **Total typical** | **~26** | Trivial on local Ollama; budget ~$0.05 on cheap APIs |

If you want the cheaper Phase 0 behaviour, set
`config.debate_rounds = 0` to disable rebuttals (the judge still runs
on the opening cases) or pass `--mock-data` for end-to-end zero-cost
testing.

---

## Phase 2 — Proof (final milestone)

**P2.1 — Walk-forward backtester** ✅ shipped (`dolphi/backtest/`).
- Monthly (or configurable) rebalance marks from decision-log JSONL
  sidecar; forward-fills the latest allocation before each period.
- Compounds hold-period returns vs SPY buy-and-hold; writes
  `walk_forward_metrics.json`, `equity_curve.svg`, and
  `walk_forward_summary.md` under `docs/benchmarks/`.
- CLI: `dolphi --backtest` (live prices) or
  `dolphi --backtest --mock-data` (bundled demo fixture + synthetic
  anchor prices, fully offline).
- 7 dedicated tests in `tests/test_walk_forward.py`.

**P2.2 — Rich live TUI** ✅ partial (`dolphi/tui/live.py`).
- `dolphi --tui` uses LangGraph `stream_mode="values"` + Rich Live to
  show discovered ideas, debate turns, pre-mortem findings, allocation,
  and prior-outcome reflection as the workflow progresses.
- 60-second GIF for README still TODO (manual recording).

**P2.3 — Writeup** ✅ draft (`docs/technical-note.md`).

**Done when:** README has equity-curve chart ✅, TUI available ✅, writeup ✅;
60-second GIF still optional.

---

## Out of scope (deliberately)

- Live brokerage integration. Dolphi is a research tool; it does not place
  orders, and the README must say so loudly.
- Crypto. The universe is US-listed equities and ETFs (incl. ADRs). Crypto
  can come later but it's a distraction from the wedge.
- Realtime data. End-of-day is enough for everything in Phases 0–2.
- Beating a benchmark. The product claim is "more honest research" via
  falsification, not "highest alpha." The backtest is a sanity check, not
  the pitch.

---

## Conventions

- Python ≥ 3.10, ruff for lint, pytest for tests.
- Pure-Python stdlib + small dependencies; no heavyweight ML libraries
  beyond `chromadb` and `sentence-transformers`.
- All file system writes go under `~/.dolphi/`.
- Every LLM call routes through `dolphi/llm/factory.py`; never instantiate
  a client directly in an agent.
- Every agent must be runnable with `--mock-data` and no network access.
