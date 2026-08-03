"""Phase 1 - match win-probability rolling backtest + pre-registered variant sweep (SKELETON -> D2).

The 2026-event rolling backtest already exists in ti_predict/backtest.py + robustness.py (event-level
log-loss, event-blocked bootstrap, A-elo / B-eloTD / B-bt / C-glicko2). This module will extend it
with the pre-registered variants (docs/validation-plan-v2.md sec 3) under NESTED tuning: for each
outer event E, hyperparameters are selected from events earlier than E only, frozen, then applied to
E. Metrics per event: log-loss (primary), Brier, calibration/ECE, series accuracy; aggregates with an
event-blocked bootstrap. Extending outer folds to historical TIs (2022-2025) is D3 and needs the
historical-data project (sec 6).

Contract (to implement in D2):
    run(events, variants, seed) -> per_event_metrics, aggregate, selection
Not implemented yet - staged pending client approval of the plan and the data scope.
"""
import sys


def main():
    sys.exit("run_match_backtest is a D2 skeleton: approve the plan (docs/validation-plan-v2.md) "
             "and the data scope first. The 2026-event Phase-1 backtest already lives in "
             "ti_predict/backtest.py + robustness.py.")


if __name__ == "__main__":
    main()
