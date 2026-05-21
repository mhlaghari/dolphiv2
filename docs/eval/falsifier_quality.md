# Falsifier-quality leaderboard

*Generated 2026-05-21T08:13:36+00:00. Judge: `deepseek:deepseek-v4-pro`. Fixtures: 8 (`ai-capex, china-adr-overhang, defence-procurement, energy-transition, glp-1, regional-banking, reit-rate-sensitivity, semi-pricing-power`). Repeats per (model, fixture): 1.*

Each falsifier was graded on four axes (0–1 each). Aggregate is the mean. See `docs/technical-note.md` § 6 for the rubric.

| Rank | Model | Aggregate | Horizon | Assumption | Indicator | Probability | Falsifiers | Latency (s) | Errors |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `deepseek:deepseek-v4-flash` | **0.838** | 0.948 | 0.676 | 0.857 | 0.871 | 21 | 172.3 | 1 |
| 2 | `deepseek:deepseek-v4-pro` | **0.787** | 0.869 | 0.779 | 0.783 | 0.719 | 24 | 509.9 | 0 |

## Reproducibility

```bash
python -m dolphi.eval --models deepseek:deepseek-v4-flash,deepseek:deepseek-v4-pro --fixtures all --judge deepseek:deepseek-v4-pro --repeats 1 --out docs/eval/
```

Raw per-falsifier rows: `falsifier_quality.csv`. Full prompt audit trail + raw model outputs: `falsifier_quality.json`.
