# v1 screening backtest — results (2026-08-01)

Event-frozen rolling backtest per `backtest-protocol.md` (+ Addenda A/B) and `model-implementation.md`.
Rating universe **8544** pro maps; evaluation **1177** target maps; **23** event folds. Untuned v1.

## Pooled (primary = map log-loss; 0.6931 = coin-flip)
| candidate | log-loss | Brier | folds beat A-elo | boot 90% CI (cand−A) | ECE |
|-----------|---------:|------:|:---:|:---:|----:|
| A-elo | 0.6625 | 0.2348 | — | — | 0.118 |
| B-eloTD | 0.6645 | 0.2357 | 11/23 | +0.0020 [−0.0002,+0.0049] | 0.118 |
| **B-bt (Bradley-Terry)** | **0.6518** | **0.2298** | **17/23** | **−0.0106 [−0.0157,−0.0055]** | **0.097** |
| C-glicko2 | 0.6717 | 0.2387 | 11/23 | +0.0098 [−0.0045,+0.0273] | 0.116 |

LOEO pooled log-loss (drop one event): A-elo 0.6585–0.6768 · B-eloTD 0.6609–0.6772 ·
**B-bt 0.6466–0.6647** · C-glicko2 0.6606–0.6860. B-bt's whole LOEO band sits below A-elo's.

## Verdict (screening rule)
**B-bt is a clear, calibrated winner** and advances: beats A-elo in a 17/23 fold majority, the
event-blocked CI on the pooled log-loss difference **excludes 0**, and it has the best Brier and the
best calibration. B-eloTD is statistically tied with A-elo (inactivity decay didn't help);
C-glicko2 is worse (overconfident on several events). No tie/universal-failure, so nested-tuning v2
is **optional**, not forced (it may still lift B-bt further).

## Gate status for emitting TI2026 probabilities
- (a) beats plain Elo consistently on log-loss — **PASS** (B-bt).
- (b) acceptable calibration — **PASS** (B-bt ECE 0.097, best of the four).
- (c) adds increment over market, out of sample — **NOT YET TESTED**: we have no timestamped
  historical odds to backtest fusion. Per the frozen protocol this leg must be checked before
  shipping, so **TI2026 probabilities remain WITHHELD**.

## Next
1. Obtain timestamped odds (a bookmaker feed, or the contest's in-client win% / crowd% from the
   friend's screenshots) to run the market-only / model-only / fused comparison with alpha fit
   strictly out of sample.
2. Optional v2: nested-tuning of B-bt (half-life, ridge) strictly inside each outer training fold.
3. Only after (c) passes: produce TI2026 map/series/bracket probabilities from B-bt (market-anchored
   where odds exist), with heavy shrinkage/uncertainty for the flagged thin/flux rosters
   (Nigma 28 maps, OG 21 core, Resilience under-connected).

Reproduce: `python -m ti_predict.universe && python -m ti_predict.build_dataset && python -m ti_predict.backtest`.
