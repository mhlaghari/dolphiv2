---
name: Bug report
about: Something Dolphi did that it shouldn't have, or didn't do that it should have
title: "bug: "
labels: bug
---

## What happened

A clear, concise description of the bug.

## Reproduction

The exact command, ideally runnable with `--mock-data` so no API keys are needed:

```bash
dolphi --mock-data --seed-symbol NVDA --top-k 5
```

If reproducing requires a non-mock LLM, note the provider and model.

## Expected behaviour

What you expected to happen.

## Actual behaviour

Paste the output (or the relevant section). For pre-mortem or debate bugs,
include the raw `~/.dolphi/decision_log.jsonl` line if you can.

## Environment

- Dolphi version (`pip show dolphi`):
- Python version (`python --version`):
- OS:
- LLM provider/model:

## Additional context

Anything else: stack trace, screenshot of the TUI, related issues.
