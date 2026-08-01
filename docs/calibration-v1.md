# v1 fixed calibration (side-neutral + strictly-rolling OOS Platt)

Mean per-fold radiant coefficient c = **+0.088** (range +0.013..+0.119).
logit(0.53) = +0.12 for reference: c is small, so it CANNOT explain intercept ~ +0.5 —
the intercept-as-radiant idea is rejected as the sole cause; the Platt layer does the real work.

| variant | log-loss | Brier | intercept a | slope b | ECE |
|---------|-----:|-----:|-----:|-----:|-----:|
| raw B-bt | 0.6518 | 0.2298 | +0.403 | 0.697 | 0.0971 |
| side-neutral | 0.6518 | 0.2298 | +0.403 | 0.698 | 0.0972 |
| side-neutral + OOS Platt | 0.6432 | 0.2255 | +0.320 | 0.567 | 0.0484 |

## Read
- side-neutral ~ raw here (eval fixes team_a = radiant, so averaging over sides barely
  shifts it) -> confirms side alone does not fix the intercept.
- the **OOS Platt layer** is what corrects intercept and slope; its parameters use only
  pre-fold predictions (no leakage). **This is the absolute probability frozen for Track-2
  EV.** Ranking is unchanged (calibration is monotone).
- Platt is identity for the earliest folds (<50 prior obs); later folds are recalibrated.
