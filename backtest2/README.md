# backtest2 - historical rolling-origin validation framework

Design + pre-registration: [`../docs/validation-plan-v2.md`](../docs/validation-plan-v2.md).
Event manifest schema: [`events/SCHEMA.md`](events/SCHEMA.md).

Strict rolling-origin / prequential protocol: each historical event is a pure out-of-sample test at
its own lock cutoff; hyperparameters are chosen from EARLIER events only (nested tuning); the answer
key (`results`) is used for scoring only, never for training or tuning.

```
backtest2/
  events/            one manifest JSON per historical target event (SCHEMA.md + example)
  compare_policies.py   Phase 3: A/B/C 2026 slot-policy comparison (RUNNABLE now; no history needed)
  run_match_backtest.py     Phase 1: match-model rolling backtest + variant sweep (skeleton -> D2)
  run_tournament_backtest.py Phase 2: real-format tournament replay (skeleton -> D3, needs data)
  tune_rolling.py            nested inner-loop hyperparameter selection (skeleton -> D2)
  reports/           generated per-event + aggregate reports (gitignored)
```

Status: **D1** - plan + schema + skeleton + runnable Phase 3. Phase 1 for the 2026 events already
exists in `ti_predict/backtest.py` + `robustness.py`; the variant sweep (D2) and historical-TI
acquisition + Phase 2 (D3) are staged pending client approval (see the plan, sec 6-7).

Run Phase 3 (model-conditional strategy simulation, dry-run only):
```
python -m backtest2.compare_policies --strengths bt --cutoff 2026-08-01 --sims 20000
```
