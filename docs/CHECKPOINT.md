# AUTHORITATIVE PROJECT CHECKPOINT (final freeze, 2026-08-04)

Single source of truth for the frozen state. Do not reinterpret, reopen, or silently modify a frozen
decision. Git history and committed documents govern.

## Status
Pipeline built, validated, hard-gated, and audited. No TI15 probabilities emitted. Awaiting the
official group draw (~2026-08-13); on the draw, follow docs/lockday-runbook.md.

## Frozen model and parameters
- Production model: identity side-neutral Bradley-Terry (B-bt).
- Time-decay half-life: 90 days (ti_predict/contest_rules.PRODUCTION_HALF_LIFE_DAYS), applied
  explicitly in the production path (not an implicit default).
- Map probability: side-neutral 0.5*(sigmoid(d+c) + sigmoid(d-c)), d = strength_a - strength_b,
  c = train-only radiant coefficient at the cutoff (about +0.09).
- No Platt or temperature calibration layer.
- Selection basis: event-frozen rolling backtest (B-bt beats plain Elo in 17/23 folds). The D2 nested
  half-life sweep found no significant out-of-sample gain over 90 (pooled -0.0014, event-blocked 95%
  CI includes 0, 12/23 fold-wins); D3 (TI2024/TI2025 outer validation) was deferred on cost. hl=90 is
  locked as production.
- Official constants are centralized in ti_predict/contest_rules.py.

## Prediction target (group stage)
Full 16-slot classification: 4-0 x1, 4-1 x2, decider_win x5, decider_loss x5, 1-4 x2, 0-4 x1. Scored
by number correct; the points curve is convex, with no wrong-answer penalty, no underdog weighting,
and no crowd percentages (the client exposes none). Verified rules: docs/contest-official-ti15.md.

## Code state
- ti_predict/swiss.py: rules-based Swiss + decider simulator; structural invariant asserted per run;
  common-random-numbers D4 sensitivity.
- ti_predict/assign.py: Hungarian max-expected-correct 16-slot solver.
- ti_predict/predict_ti15.py: hard-gated entry (dry-run vs official) with provenance manifest.
- backtest2/compare_policies.py: model-conditional policy study (max-correct equals max-points here).
- Current code: the audit-freeze commit on main (this file's commit); prior baseline 98f2079.

## Tests (pytest) - all passing
tests/ holds 27 tests: official constants; map_pn side-neutral symmetry; structural 1/2/5/5/2/1
invariant; probability row and column sums; fixed-seed reproducibility; CRN D4 sensitivity capacities;
assignment capacity and expected-correct accounting; cutoff format and timezone gate; draw-file valid
and invalid boundaries; manifest required fields; JSON/Markdown consistency; B-bt 16-team mapping
(auto-skipped without the local universe).
Run: python -m pytest -q
Also: python -m ti_predict.swiss ; python -m ti_predict.assign ; python -m ti_predict.predict_ti15 --dry-run

## Public-repo reproducibility boundary
- A clean clone reproduces: install (requirements.txt), imports, simulator/solver self-tests, the
  synthetic dry-run, and the full pytest suite (data-dependent tests auto-skip).
- The real B-bt path needs the gitignored processed universe
  (data/ti2026/processed/universe_maps.csv), regenerated per docs/lockday-runbook.md
  (fetch_opendota -> resolve_identity / roster_coverage -> build_canonical -> universe ->
  build_dataset). Without it the bt path raises a clear error; the public repo alone cannot
  reconstruct unpublished match data.

## Lock-day single command
After refreshing data through the cutoff and entering the posted draw (docs/lockday-runbook.md):
python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z

## External inputs still required
1. The official two-pod split and round-1 pairings (draw.json), posted around 2026-08-13.
2. The exact in-client lock timestamp (a timezone-aware ISO value).
3. A universe refreshed through the cutoff (the official freshness gate blocks a stale run).

## Residual assumptions (documented and sensitivity-checked)
- C5 pairing tie-break: sample among rule-legal pairings (fewest rematches, then the gap objective,
  then random) - the organizer's exact tie-break is unpublished.
- D4 decider opponent choice: strategic (strongest available opponent) is primary; noisy and random
  are reported as common-random-numbers sensitivity.
- Ranking tiebreaker 6 (average game duration) is unmodeled and folded into the coin toss; the
  measured rate at which it would decide anything is negligible.
- The simulator is structural/property-tested; it does not claim to replicate the organizer's
  unpublished pairing decisions.
- The main-event (14-series) track is deferred until the group draw is set.
- Historical D3 (TI2024/TI2025) is archived: manifests, framework, and the pre-registered switch rule
  are retained for a possible future run.

## Discipline
Conventional Commits, subject <=72 characters and ASCII (hook-enforced). Production is never updated
from crowd percentages, odds, or results, and is not re-tuned on TI2024/TI2025 outcomes.
