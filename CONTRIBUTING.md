# Contributing

Thanks for helping improve Dolphi.

## Development setup

```bash
git clone https://github.com/mhlaghari/dolphi
cd dolphi
pip install -e ".[dev]"
python -m pytest tests
ruff check .
```

CI runs `ruff check .` + `python -m pytest tests` on Python 3.10 / 3.11 / 3.12.
Both must be green before a PR can merge.

Use mock mode for local development whenever possible:

```bash
dolphi --mock-data --seed-symbol NVDA --top-k 5
```

This runs the full agent graph end-to-end with synthetic prices and a curated
26-symbol universe; no network access required.

## Project principles

- Local-first, useful without paid APIs.
- Validate every LLM-suggested ticker against the universe before analysis.
- Deterministic code for scoring, constraints, and allocation sizing.
- LLMs for interpretation, debate, synthesis, and narrative — and for trying to
  **break** the thesis (the Pre-Mortem agent).
- Outputs always make clear that this is research and education, not financial
  advice.

## Testing expectations

- Add or update tests for every behaviour change.
- Prefer mock-data tests over live-network tests so CI stays reliable.
- Per-agent tests live in `tests/test_*.py`; render-only tests for the TUI use
  the `rich.console.Console(file=io.StringIO())` pattern (see
  `tests/test_tui.py`).
- All tests must pass with `--mock-data`; agents that depend on a live API are
  out of scope.

## High-value contributions

Each block below points at the exact module to extend and the contract the new
code must satisfy.

### Add a new research source

Module: `dolphi/research/sources.py`. Sources implement a `fetch(query: str,
limit: int) -> list[ResearchDocument]` callable and are registered in
`dolphi/research/pipeline.py`. Add a unit test that asserts deterministic
output on a captured fixture (network-free).

### Add a new falsifier prompt variant

Module: `dolphi/agents/pre_mortem.py`. The system prompt is
`_PRE_MORTEM_SYSTEM_PROMPT` (around line 53) and the assumption-extraction
prompt is `_ASSUMPTION_SYSTEM_PROMPT` (around line 43). When you change either,
add a fixture in `tests/test_pre_mortem.py` showing the new prompt holds the
falsifier contract (3 falsifiers, ≤ 12-month horizon, weekly-checkable
indicator, names one of the extracted assumptions).

### Add a universe slice

Module: `dolphi/universe/loader.py`. The loader exposes `default_universe()`
and `open_universe()`; new slices (e.g. a sector ETF allow-list, an ADR list)
plug in via `dolphi/universe/`. Liquidity-filter + validate every symbol; the
allocator will silently drop anything it can't price.

### Add a ranking factor

Module: `dolphi/scoring/`. Factors emit a `dict[str, float]` `score_breakdown`
per `RankedIdea` (`dolphi/models.py:102`). Keep contributions transparent — the
final score must remain the sum of weighted breakdown components.

### Add an eval fixture

Module: `dolphi/eval/fixtures.py` (in progress for v0.2.0). Each fixture is a
frozen dataclass `(bull_thesis, bull_assumptions, expert_falsifiers)` for a
real macroeconomic theme. Coverage we want: GLP-1, defence, China/ADR overhang,
regional banking, REIT rate-sensitivity — see `docs/eval/` for the rubric and
existing fixtures.

## Commit + PR style

- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`).
- One topic per PR. Bundling unrelated changes makes review slow.
- Update `CHANGELOG.md` (when present) and `PLAN.md` if your change is
  roadmap-relevant.
- PRs against `main` only; no long-lived feature branches.

## Code of conduct

Be kind, be honest, and assume good faith. Dolphi takes research integrity
seriously — if you spot a methodological hole, open an issue rather than
papering over it.
