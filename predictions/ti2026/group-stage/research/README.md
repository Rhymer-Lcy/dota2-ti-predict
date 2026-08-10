# research/ — NOT the official prediction

Everything in this directory is clearly-labeled research output. The OFFICIAL group-stage slate is
the pair `../ti15_group_prediction.{json,md}`, produced only by
`python -m ti_predict.predict_ti15 --official ...` once every gate passes
(docs/lockday-runbook.md). Nothing here is submitted.

| file | what it is |
|---|---|
| `ti15_post_r1_provisional.json` | R1-fixed / pods-latent provisional slate (`backtest2/post_r1.py`). The eight posted round-1 matches are fixed; the unpublished pod structure is marginalized over the open 16-team Swiss and all 35 admissible two-pod partitions. Carries `r1_status`, `pods_status`, the pod evidence source and the pod uncertainty assumptions. |
| `roster_sensitivity_lgd_gaming.json` | How far LGD's strength would have to move before the slate changes (`backtest2/roster_sensitivity.py`), with the bootstrap that calibrates the scale. No strength is edited in production. |
| `market_diagnostic.json` | Market anomaly check (`backtest2/market_check.py`). Diagnostic only: never fused, never a promotion input, no validated out-of-sample market signal exists in this repo. |

These files exist so the reasoning behind the eventual official slate is auditable, and so a
post-mortem can separate a bad strength estimate from a bad structural assumption from bad luck.
