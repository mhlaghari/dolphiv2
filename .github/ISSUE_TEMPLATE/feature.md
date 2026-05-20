---
name: Feature request
about: Propose a new agent, source, falsifier prompt, ranker factor, or doc
title: "feat: "
labels: enhancement
---

## What you want

One or two sentences describing the change.

## Why it matters

Which user does this help, and how does it fit Dolphi's "falsification-first"
positioning? Be specific — abstract features that don't sharpen the wedge
usually don't land.

## Sketch of the implementation

Which module(s) would change? See `CONTRIBUTING.md` for the canonical
extension points:

- New research source → `dolphi/research/sources.py`
- New falsifier prompt → `dolphi/agents/pre_mortem.py`
- New ranking factor → `dolphi/scoring/`
- New universe slice → `dolphi/universe/loader.py`
- New eval fixture → `dolphi/eval/fixtures.py`

## Alternatives considered

Anything you ruled out, and why.
