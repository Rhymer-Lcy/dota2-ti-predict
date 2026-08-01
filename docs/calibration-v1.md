# v1 fixed calibration (side-neutral + strictly-rolling OOS Platt)

Mean per-fold radiant coefficient c = **+0.088** (range +0.013..+0.119).
logit(0.53) = +0.12 for reference: c is small, so it CANNOT explain intercept ~ +0.5 —
the intercept-as-radiant idea is rejected as the sole cause; the Platt layer does the real work.

| variant | log-loss | Brier | intercept a | slope b | ECE |
|---------|-----:|-----:|-----:|-----:|-----:|
| raw B-bt | 0.6518 | 0.2298 | +0.403 | 0.697 | 0.0971 |
| side-neutral | 0.6518 | 0.2298 | +0.403 | 0.698 | 0.0972 |
| side-neutral + OOS Platt (diag) | 0.6432 | 0.2255 | +0.320 | 0.567 | 0.0484 |
| side-neutral + OOS temperature (production) | 0.6573 | 0.2324 | +0.437 | 0.619 | 0.1029 |

## Warm-up accounting (OOF Platt needs >=50 prior obs)
- identity (warm-up) folds: **2** (133 obs); Platt-calibrated folds: **21** (1044 obs). The aggregate improvement above is driven by the 1044 Platt-calibrated obs.

## Reproducibility (frozen spec, not frozen numbers)
1. **What is frozen is the Track-2 probability PIPELINE (spec)** — the B-bt model, the
   side-neutral step, and the OOS-Platt recipe — **not the final TI2026 numbers**. The
   final numbers come from an **as-of-cutoff refit** using this frozen model + calibration.
2. Warm-up above: only the Platt-calibrated obs benefit; identity folds are uncorrected.
3. **Production calibration status: UNVALIDATED -> default IDENTITY.** The full-Platt ECE
   gain (0.097->0.048) is a fixed-team_a-side (radiant) eval artifact; the production-safe
   symmetric temperature does NOT reproduce it on this side-confounded eval (LL 0.6573 >
   0.6518 raw). So production = raw side-neutral B-bt for now; the temperature is stored as
   an unvalidated candidate (`inputs/production_platt.json`, cutoff + commit, pre-cutoff OOF
   only; **refit at TI cutoff; never update from crowd%/odds/results**).

## Read (correction to the earlier 'materially improves' claim)
- side-neutral ~ raw (eval fixes team_a = radiant; radiant c=+0.088 cannot explain +0.5).
- The full-Platt ECE drop is **largely a fixed-side eval artifact** (its intercept absorbs
  the radiant bias) and does NOT transfer to symmetric production.
- The production-safe temperature (a=0) does **not** improve the side-confounded eval, so
  **production calibration is NOT yet validated** -> default to identity (raw side-neutral
  B-bt). A valid test needs a side-aware eval; recorded as the next calibration step to run
  when unparked (a measurement fix, not a hyperparameter search). Ranking is unaffected.
