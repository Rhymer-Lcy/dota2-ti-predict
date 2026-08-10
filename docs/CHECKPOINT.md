# AUTHORITATIVE PROJECT CHECKPOINT (updated 2026-08-10, post-round-1)

Single source of truth for the frozen state. Do not reinterpret, reopen, or silently modify a frozen
decision. Git history and committed documents govern.

## Status
Pipeline built, validated, hard-gated, adversarially re-validated (backtest2/results-adversarial.md,
2026-08-09) and now advanced to the POST-ROUND-1 state (backtest2/results-post-r1.md, 2026-08-10):
- **Round 1 is official and ingested.** Valve's league feed published all eight pairings; they are
  parsed by ti_predict/league_feed.py into data/ti2026/inputs/draw.json and every team id resolves
  through canonical_identity.csv. The same feed's scheduled_time upgrades the lock time to a second
  independent Tier-1 confirmation of 2026-08-13T02:00:00Z.
- **The pod split is still unpublished** and may not exist (the feed shows one undivided 16-team
  Swiss). The official run FAILS CLOSED on pods_status="unresolved"; the structure is marginalized in
  research instead, and both structural families give the same slate.
- **One lock-period roster change** (LGD position 2, TaiLung banned -> Topson), recorded with full
  provenance in data/ti2026/inputs/roster_events.csv; the other 15 lineups are confirmed unchanged
  and the Team Liquid source conflict is resolved from match data (Nisha).
- **Two more real pipeline defects found and fixed** during the refresh (see Code state).
- The model, half-life, calibration, solver and refinement are UNCHANGED; nothing was re-tuned.
No OFFICIAL prediction emitted; the provisional slate under backtest2/post_r1.py is research. On the
day, follow docs/lockday-runbook.md.

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
- 2026-08-09 challenger round: logit ensembles with A-elo / B-eloTD / C-glicko2 (fixed and
  prequential weights) are ALL out-of-sample WORSE than pure B-bt (blocked CIs exclude 0); the
  no-lookahead adaptive selector chose pure B-bt in 23/23 folds. No challenger reached the promotion
  gate; the model freeze stands on evidence, not inertia.
- Decision layer (2026-08-09, adversarially audited): the Hungarian max-expected-correct slate plus
  a VERIFIED expected-points refinement - a swap search proposes a slate, adopted only if an
  independent verification archive shows a paired points gain > 2 bootstrap se. Corrected evidence:
  true effect about +6.5 +/- 1.0 points on fresh archives (the originally reported +18.3 was a
  winner's-curse-typical high draw); 0 harmful adoptions in 30 end-to-end replications; the
  manifest's recorded gain is adoption-conditioned (about 1.7x optimistic). Official run uses
  --sims 120000 for ~94% gate power. Fail-safe default is the Hungarian slate.
- Official constants are centralized in ti_predict/contest_rules.py.

## Prediction target (group stage)
Full 16-slot classification: 4-0 x1, 4-1 x2, decider_win x5, decider_loss x5, 1-4 x2, 0-4 x1. Scored
by number correct; the points curve is convex, with no wrong-answer penalty, no underdog weighting,
and no crowd percentages (the client exposes none). Verified rules: docs/contest-official-ti15.md.

## Code state
- ti_predict/swiss.py: rules-based Swiss + decider simulator; structural invariant asserted per run;
  common-random-numbers D4 sensitivity.
- ti_predict/assign.py: Hungarian max-expected-correct 16-slot solver.
- ti_predict/predict_ti15.py: hard-gated entry (dry-run vs official) with provenance manifest; the
  gate now also blocks an unresolved pod structure and an unresolved roster audit, and records the
  freshness-gate override in the manifest instead of allowing a silent one.
- ti_predict/league_feed.py: parses the official league feed into the posted draw; never infers pods.
- ti_predict/rosters.py + inputs/roster_events.csv: the tracked 16-team roster audit.
- ti_predict/swiss.py: also simulates the OPEN 16-team structure (pods=(teams,)).
- backtest2/post_r1.py: R1-fixed / pods-latent provisional prediction (research).
- backtest2/roster_sensitivity.py: bootstrap-calibrated roster-uncertainty study.
- backtest2/market_check.py: market anomaly check, diagnostic only.
- backtest2/compare_policies.py: model-conditional policy study (max-correct equals max-points here).
- Pipeline defects fixed 2026-08-10 (both would have corrupted a lock-day run):
  (1) resolve_identity.py overwrote raw/promatches_scan.json with its own 30-page scan, truncating
      the rating universe from 9146 maps (2026-02-27..) to 3000 (2026-05-17..) -- the same silent
      truncation seen on 2026-08-09, whose real cause was this module, not scan_promatches.py. It now
      MERGES and refuses to write on any coverage regression.
  (2) resolve_identity.py also wrote the tracked inputs/canonical_identity.csv in its intermediate
      schema, so a partial run (an OpenDota 5xx burst emptied 14 of 16 rosters) erased every
      source_team_ids mapping -- the column through which the rating universe resolves TI
      organizations. It now writes only processed/identity_resolved.csv and exits non-zero on an
      incomplete resolution; build_canonical.py is the single writer of the tracked table.
  Also corrected: inputs/folds.csv and universe_maps.csv is_target had been generated against a stale
  dataset_maps.csv (11 folds instead of 23). Rebuilt to a verified fixed point. Production strengths
  are provably unaffected -- is_target is used only to build the fold table, and refitting from the
  pre-refresh universe reproduces all 16 strengths bit-identically.
- Current code: the post-round-1 commit on main (this file's commit); prior freeze 825c68c.

## Tests (pytest) - all passing
tests/ holds 43 tests: official constants; map_pn side-neutral symmetry; structural 1/2/5/5/2/1
invariant; probability row and column sums; fixed-seed reproducibility; CRN D4 sensitivity capacities;
assignment capacity and expected-correct accounting; cutoff format and timezone gate; draw-file valid
and invalid boundaries; manifest required fields (incl. points_refinement); JSON/Markdown consistency;
pre-draw pod-sampling validity; simulation-archive/P consistency; ensemble mixing endpoints; the
refinement adopt/reject/no-move rules; failure modes (corrupt/non-object draw JSON, repeated team in
round 1, missing pods, missing universe, CLI-level official block); B-bt 16-team mapping
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
python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 120000

## External inputs still required
1. The official pods and round-1 pairings (draw.json), expected ~2026-08-11 (TI2025 lead ~47 h; not
   yet published as of 2026-08-09). Machine-readable source: the league feed (league_id 19719, see
   ti_predict/contest_rules.LEAGUE_FEED_URL) - poll until round-1 nodes carry team ids.
2. The exact in-client lock timestamp (a timezone-aware ISO value; Tier-1-supported estimate
   2026-08-13T02:00:00Z = 10:00 UTC+8, graded in docs/contest-official-ti15.md sec 5; the in-client
   countdown is the final authority).
3. A universe refreshed through the cutoff (rehearsed 2026-08-09: takes ~25 min; the freshness gate
   blocks a stale run, and scan truncation now fails closed). The final Aug 10-13 matches still need
   one incremental scan on lock day. Boundary slots that the refit will decide: Falcons/BetBoom vs
   Yandex (top), OG vs GamerLegion (bottom), Nigma (middle).

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
