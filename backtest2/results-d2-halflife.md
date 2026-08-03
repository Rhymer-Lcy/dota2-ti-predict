# D2 result - B-bt half-life sweep on 2026 events (inner tuning)

Pre-registered grid {45,60,90,120,180} days, 23 2026 folds, nested (no-lookahead) selection.
Reproduce: `python -m backtest2.run_match_backtest`. Primary metric: event-weighted log-loss.

## Pooled weighted log-loss (lower better)
| half-life | 45 | 60 | 90 (frozen) | 120 | 180 | nested (no-lookahead) |
|---|---:|---:|---:|---:|---:|---:|
| log-loss | 0.6578 | 0.6548 | 0.6518 | 0.6503 | **0.6488** | 0.6504 |

Pooled Brier: fixed90 0.2298, nested 0.2292.

## Reading it (disciplined)
- Within the frozen grid, **longer half-life monotonically improves** 2026 log-loss; hl=180 is best
  (0.6488 vs frozen-90 0.6518, -0.0030). More history helps on the 2026 window (rosters were fairly
  stable across Feb-Aug 2026).
- BUT the honest no-lookahead **nested benefit over frozen-90 is NOT significant**: pooled
  -0.0014 with an **event-blocked 95% CI of (-0.0052, +0.0012) that includes 0**, and only **12/23
  fold-wins** (~half). So on strictly out-of-sample 2026 evidence, adaptive half-life does not clearly
  beat 90.
- hl=180 is the grid BOUNDARY. A longer optimum may exist, but extending the grid now would be
  post-hoc overfitting (protocol violation). Grid stays as pre-registered; 180 is its winner.

## Decision (per the plan's selection rule)
- **Do NOT change production now.** Frozen B-bt (hl=90) remains production.
- Carry a minimal candidate set to the TI2024/TI2025 OUTER held-out test (D3):
  **{ frozen B-bt hl=90, candidate B-bt hl=180 }**.
- The inner set (2026) SELECTED hl=180; the outer test VALIDATES it. Per the client rule: if the two
  outer TIs conflict or their sample is insufficient, KEEP frozen B-bt (hl=90). No re-tuning on
  TI24/25 outcomes.
- A very long half-life that looks best on the stable 2026 window is exactly the kind of choice that
  can fail at a real TI with roster churn - which is why the outer test exists.
