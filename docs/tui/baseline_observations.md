# TUI — Baseline observations

> Captured 2026-05-20 against `dolphi/tui/live.py` (126 LOC). End-to-end run:
> `printf '50000\n5000\nUSD\ngrowth\nModerate\nstocks,etfs\n' | dolphi --mock-data --seed-symbol NVDA --top-k 5`
> Snapshots in `docs/tui/baseline_snapshot_{80,100,140}cols.txt`.
>
> This is the **work list for the Bloomberg-style rebuild** (Workstream B).
> Numbered worst → least bad. Items 1–6 are demo-killers — they have to land
> before a 60-sec screencap is worth recording.

## What's broken or weak today

1. **The Pre-Mortem panel only shows 1 of 3 falsifiers per symbol.**
   `live.py:75-82` reads `falsifiers[0]` only. With `top_k=5` that means
   **10 falsifiers are hidden** behind ellipsis. The falsifiers are the
   whole product — invisible falsifiers = invisible wedge. *Fix: per-symbol
   drill-down on hotkey `[1-5]` showing all 3 falsifiers + their named
   broken assumption + horizon + leading indicator.*

2. **Bull's load-bearing assumptions never render anywhere.**
   `bull_assumptions` is in `AgentState` (`models.py:183`) and is the
   intellectual innovation — the falsifier targets a *named* assumption,
   not a vibes-based risk. Currently the TUI throws this field away. *Fix:
   first-class panel listing the 3-5 extracted assumptions with a
   "broken-by" badge counting how many falsifiers target each.*

3. **Allocation rationale truncates at 50 chars** (`live.py:95`).
   Real rationale strings are 200-400 chars and contain *the attribution*
   ("fragility 0.32, debate delta +0.20") — exactly what an analyst wants
   to verify. *Fix: separate columns for `weight %`, `base score`,
   `× fragility`, `+ debate delta`, `rationale`. Numbers as bars, not
   percentages.*

4. **Theme column truncates at 24 chars** (`live.py:43, 49`).
   At 100 cols the table shows "NVIDIA Related Opportun…" five times in a
   row — the rank order is invisible because every theme looks identical.
   *Fix: wider theme column at ≥120 cols; at < 120 cols show only the
   delta from the previous row.*

5. **No color signal for fragility.**
   `live.py:80` prints `f"{fragility:.2f}"` as plain text. A user can't
   distinguish 0.22 (safe) from 0.62 (collapse risk) at a glance. *Fix:
   color gradient green < 0.3 ≤ yellow < 0.6 ≤ red, plus a
   `▁▂▃▄▅▆▇█` block-char bar.*

6. **No conviction-delta visualisation for the judge.**
   `live.py:69` shows only the rationale text. The actual delta
   (`+0.20`, bull-win) is the headline number — it's what the allocator
   actually consumes. *Fix: per-symbol gauge: dim-grey baseline,
   green-tinted bar to the right if bull won, red-tinted to the left if
   bear won, width proportional to |delta|.*

## Layout & polish issues

7. **Five vertically-stacked panels = 53 lines at 100 cols.**
   The user scrolls. A demo GIF cannot show "everything at once." *Fix:
   `rich.layout.Layout` with header / sidebar (agent timeline) / main
   pane / footer (hotkeys). Cycle panes with `tab`. Demo recording then
   shows three discrete frames in sequence rather than one 53-line dump.*

8. **No agent-progress timeline.**
   `_stage_label()` (`live.py:20-33`) renders a single text label like
   `pre_mortem ✓`. You can't see *what's currently running* and *what's
   queued*. *Fix: sidebar listing all 8 agents in graph order, each row
   shown as one of `▷ queued`, `▶ running`, `✓ done`, with an animated
   spinner on the running row.*

9. **No ETA / wall-clock indicator.**
   The actual workflow took ~2 minutes on DeepSeek V4-Flash; the user
   sees nothing change between `bear_researcher` finishing and
   `pre_mortem` starting. *Fix: timer per agent in the sidebar; total
   elapsed in the footer.*

10. **At 80 cols the falsifier table wraps to 2 lines per row.**
    See `baseline_snapshot_80cols.txt:30-31`. Wrapping breaks the
    column alignment and confuses the eye. *Fix: minimum viable width
    enforced at 100 cols; below that, switch to a single-column "card"
    layout instead of tables.*

11. **`refresh_per_second=4` and `screen=True`** (`live.py:122`)
    means the entire alt-screen is repainted 4×/sec for the full
    ~120-second run. Diff-aware updates would be cheaper but Rich
    Live re-renders everything. *Acceptable for now — flag for revisit
    if we hit visible flicker in the recording.*

## Demo-recording blockers

12. **CLI prompts for profile interactively before the TUI even
    starts** (`cli.py:296-297`). Cannot produce a deterministic
    recording without stdin piping. *Fix: `--profile-preset
    moderate-growth-50k` flag that bypasses `_prompt_user()` with a
    canned `UserProfile`. Three presets: `aggressive-growth`,
    `moderate-growth`, `conservative-income`. Used by the recorder
    and by tests.*

13. **No record-mode flag.**
    `asciinema` recording is doable manually but not reproducible.
    *Fix: `--tui-record path/to/run.cast` flag wrapping the run.
    Combined with `--profile-preset` this makes the README GIF a
    one-liner.*

14. **No deterministic LLM mode.**
    With `--mock-data` the universe/prices are mocked but LLM calls
    still go to whichever provider is configured. The actual analyst
    reasoning, debate text, and falsifier text vary run to run. *Fix:
    an optional `--mock-llm` flag that loads canned responses from
    `dolphi/tui/fixtures/mock_llm_responses.json` so the demo GIF is
    bit-identical on every record. Lower priority than the layout
    rebuild but essential before final recording.*

## What's already good (keep)

- **State-driven render** (`render_workflow_state(state)`) is the right
  pattern. The new dashboard should reuse this — `Dashboard(state)`
  returns a `Layout`, and the streaming loop in
  `stream_graph_with_tui` (`live.py:118-126`) stays unchanged.
- **`_truncate()` and `_stage_label()`** helpers are sound; move to
  `dolphi/tui/_format.py` and reuse in every new pane.
- **No threading, no async** — the LangGraph `stream_mode="values"`
  iteration is simple and the right primitive. Don't replace with a
  custom event loop.
- **`tests/test_tui.py` headless pattern** — passing a
  `rich.console.Console(file=io.StringIO())` works for unit tests
  without a real TTY. New panes should use the same fixture.

## Out of scope for Workstream B (defer)

- Mouse support, scrolling history, themes/light-mode, save-to-HTML
  export. Not on the critical path to viral demo.
- A real web dashboard (Next.js / Streamlit). Considered in
  clarifying-questions; rejected in favour of TUI polish to keep
  surface area small.
