# research/ — NOT the official prediction

Everything in this directory is clearly-labeled research output. The OFFICIAL group-stage slate is
the pair `../ti15_group_prediction.{json,md}`, produced only by
`python -m ti_predict.predict_ti15 --official ...` once every gate passes
(docs/lockday-runbook.md). Nothing here is submitted.

| file | what it is |
|---|---|
| `ti15_post_r1_provisional.json` | R1-fixed / membership-latent provisional slate (`backtest2/post_r1.py`). The eight posted round-1 matches are fixed; the two-pod structure is the official rule, and the unpublished pod MEMBERSHIP is marginalized over all 35 round-1-compatible partitions. The open-16 pool is reported alongside as a sensitivity comparator only. Carries `r1_status`, `structure`, `structure_status`, `pod_membership_status` and the evidence behind each. |
| `roster_sensitivity_lgd_gaming.json` | How far LGD's strength would have to move before the slate changes (`backtest2/roster_sensitivity.py`), with the bootstrap that calibrates the scale. Scenarios are simulated on the open-16 comparator for cost; the measured structural effect (<= 0.0056 per cell, zero slate changes) is far below the perturbations studied, and `--structure two-pod` reruns the check under the official format. No strength is edited in production. |
| `market_diagnostic.json` | Market anomaly check (`backtest2/market_check.py`). Diagnostic only: never fused, never a promotion input, no validated out-of-sample market signal exists in this repo. |

These files exist so the reasoning behind the eventual official slate is auditable, and so a
post-mortem can separate a bad strength estimate from a bad structural assumption from bad luck.
