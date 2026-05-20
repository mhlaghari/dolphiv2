# Example: NVDA theme discovery (captured, deterministic)

Captured 2026-05-20 from a real `--mock-data` run. Reproduce locally with:

```bash
printf '50000\n5000\nUSD\ngrowth\nModerate\nstocks,etfs\n' \
    | dolphi --mock-data --seed-symbol NVDA --top-k 5
```

The output below is verbatim from that run (DeepSeek V4-Flash as the LLM).
With a different model the prose will vary, but the workflow shape — five
ranked ideas, multi-round debate with judge verdicts, three falsifiers per
symbol grounded in named bull assumptions, deterministic allocation — is
invariant.

---

## Discovered top ideas

```
1. NVDA  (NVIDIA Related Opportunity Chain)  score=0.66
2. CEG   (NVIDIA Related Opportunity Chain)  score=0.56
3. ETN   (NVIDIA Related Opportunity Chain)  score=0.56
4. NEE   (NVIDIA Related Opportunity Chain)  score=0.56
5. VST   (NVIDIA Related Opportunity Chain)  score=0.56
```

NVDA is the seed; CEG / ETN / NEE / VST are LLM-proposed beneficiaries
(data-centre power, electrical infrastructure, utilities) that were
universe-validated against the US-listed allow-list before ranking.

## Portfolio recommendation

| Asset | Allocation | Rationale |
|---|---|---|
| NVDA | 16.6% | Semis leadership; pre-mortem fragility 0.32; bull won debate (+0.20) |
| CEG  | 14.8% | Data-centre power supplier; fragility 0.23; bull won (+0.15) |
| ETN  | 15.0% | Electrical infrastructure; fragility 0.22; bull won (+0.15) |
| NEE  | 13.9% | Renewable utility; fragility 0.30; bull won (+0.15) |
| VST  | 14.6% | Power producer; fragility 0.25; bull won (+0.15) |
| BND  | 25.1% | Defensive ballast for the Moderate risk profile |

The 25.1% bond sleeve is set by the deterministic allocator's
risk-profile cap, not by the LLM.

## Debate verdicts

```
NVDA: winner=bull (delta +0.20) — Bull's focus on tech sector strength and forward
                                  P/E of 22x with 15% earnings growth directly
                                  supports NVDA as a leader in AI accelerators.
CEG : winner=bull (delta +0.15) — Bull's emphasis on energy sector tailwinds and
                                  infrastructure spending benefits CEG as a
                                  data-centre power supplier.
ETN : winner=bull (delta +0.15) — Continued industrial and electrical
                                  infrastructure investment supports ETN.
NEE : winner=bull (delta +0.15) — Positive view on energy and utilities aligns
                                  with NEE as a renewable utility.
VST : winner=bull (delta +0.15) — Strong fundamentals in energy and growth in
                                  power production support VST.
```

Conviction delta is bounded to [-0.3, +0.3] and is added to the score
*before* the fragility multiplier applies.

## Pre-Mortem — what would kill this?

### NVDA — fragility 0.32

```
p=0.30 [6 months]  NVDA's forward P/E contracts as earnings growth forecast falls
                   below 10% due to softening AI chip demand from hyperscalers.
                   breaks: "Forward P/E of 22x is consistent with 15% earnings
                            growth and high ROEs to justify current market levels."
                   watch:  Weekly change in consensus EPS estimate for NVDA's next
                           fiscal year (Refinitiv I/B/E/S) — decline > 5% in a month.

p=0.40 [3 months]  Sentiment shifts from bullish to extreme optimism, followed by
                   a correction when earnings fail to meet high expectations.
                   breaks: "Current sentiment level of 0.85 is not a contrarian
                            extreme given earnings growth and valuation."
                   watch:  Weekly NVDA put/call ratio (OCC) falling below 0.5 for
                           two consecutive weeks.

p=0.25 [12 months] A major customer announces a reduction in AI infrastructure
                   spending or a shift to in-house alternatives, eroding NVDA's
                   pricing power.
                   breaks: "Tech and energy firms have structural pricing power
                            and cost efficiencies that maintain margins despite
                            normalization."
                   watch:  Weekly Google Trends ratio for 'AI chip competition'
                           relative to 'NVIDIA' — exceeds 0.8.
```

The other four symbols each have three analogous falsifiers; the full
output is in `~/.dolphi/decision_log.md`.

## What the user actually walks away with

Every position comes with three **named, dated, weekly-monitorable
failure modes** plus the bull assumption each one would break. The point
isn't to predict the future — it's to pre-register what evidence would
change the position size, so the decision is repeatable.
