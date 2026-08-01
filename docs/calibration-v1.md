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
3. **This file is the side-neutral DIAGNOSTIC; the production decision lives in**
   **`calibration-sideaware.md`** (the side-aware eval removes the orientation confound).
   Temperature form: q = sigmoid(b*logit(p)); b<1 softens, b>1 sharpens.

## Read (superseded for the production decision by the side-aware eval)
- side-neutral ~ raw (this eval fixes team_a = radiant; train radiant c=+0.088).
- The full-Platt ECE drop is an **orientation-specific base-rate offset absorbed by its
  intercept** in this fixed-orientation eval; its decomposition (radiant advantage /
  ordering / base rate / model centering) is **unresolved** and does not transfer to
  symmetric production.
- The side-aware eval (`calibration-sideaware.md`) is definitive: the intercept persists
  after orientation correction, symmetric temperature does not help -> **production = identity side-neutral B-bt**. Ranking unaffected.
