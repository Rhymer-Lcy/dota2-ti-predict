"""Nested inner-loop hyperparameter selection (SKELETON -> D2).

Implements the anti-leakage tuning rule (docs/validation-plan-v2.md sec 1): to predict outer event E,
choose hyperparameters (time-decay half-life, event weights, roster penalties, model family) using
ONLY events strictly earlier than E, freeze them, then hand the frozen config to the outer backtest.
This guarantees no parameter is chosen with knowledge of the test event.

Contract (to implement in D2):
    select(prior_events, variant_grid, metric='logloss') -> frozen_config
Not implemented yet - staged with run_match_backtest (D2).
"""
import sys


def main():
    sys.exit("tune_rolling is a D2 skeleton (see run_match_backtest).")


if __name__ == "__main__":
    main()
