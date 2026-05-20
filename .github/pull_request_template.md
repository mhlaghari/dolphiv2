## Summary

<!-- One paragraph: what changed and why. Keep it tight. -->

## Type of change

<!-- Conventional-commit prefix; tick the one that matches. -->

- [ ] `feat:` new capability
- [ ] `fix:` bug fix
- [ ] `refactor:` no behaviour change
- [ ] `docs:` documentation only
- [ ] `test:` tests only
- [ ] `chore:` deps / tooling / CI

## How this was verified

```bash
ruff check .
python -m pytest tests
dolphi --mock-data --seed-symbol NVDA --top-k 5
```

<!-- Add any extra reproduction steps the reviewer needs. -->

## Falsification-first hygiene

<!-- If this PR touches the pre-mortem, debate, or allocator paths,
     describe what would falsify the change. What evidence in the
     decision log would tell you it made the agent worse? -->

## Checklist

- [ ] Tests added or updated
- [ ] Mock-data path still works (`dolphi --mock-data`)
- [ ] No new live-network calls in tests
- [ ] `PLAN.md` updated if roadmap-relevant
- [ ] No secrets, API keys, or user-specific paths committed
