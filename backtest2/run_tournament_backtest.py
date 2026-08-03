"""Phase 2 - real-format tournament replay (SKELETON -> D3, needs historical data).

For each event manifest with `phases_supported` including 2, replay the event under ITS OWN real
format (events/SCHEMA.md): its official groups, first-round draw, advancement rules and tiebreakers -
NOT the 2026 Swiss. Predict advancement / elimination / final standings before lock; score against
the manifest `results` answer key (loaded by the scorer only, never by training). Report per event
and aggregate; years without a reconstructable format stay Phase-1-only.

Contract (to implement in D3):
    replay(event_manifest, strength_fn) -> advancement_probs, placement_probs, scored_metrics
Not implemented yet - requires the historical-data acquisition + per-year format reconstruction
(docs/validation-plan-v2.md sec 6-7). Approve scope before fetching.
"""
import sys


def main():
    sys.exit("run_tournament_backtest is a D3 skeleton: needs historical data + per-year format "
             "reconstruction. Approve the data scope (docs/validation-plan-v2.md sec 6) first.")


if __name__ == "__main__":
    main()
