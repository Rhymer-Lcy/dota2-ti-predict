# Lock-day runbook - TI15 group-stage prediction (~2026-08-13)

Production model is FROZEN: B-bt, half-life 90 (applied explicitly in the production path), identity
side-neutral, no calibration layer, no crowd% fusion (docs/CHECKPOINT.md, validation-plan-v2.md).
Lock = first group-stage match, best-supported estimate **2026-08-13 10:00 UTC+8 = 02:00 UTC**
(docs/contest-official-ti15.md sec 5; the older 15:00 UTC figure is graded a timezone-conversion
error). CONFIRM the exact in-client countdown and submit >= 1h early.

## Steps
1. **Refresh data through the cutoff.** Current universe ends 2026-08-01; re-pull and rebuild so the
   Aug 2-13 matches (ongoing events + any warmups) are included:
   `python -m ti_predict.fetch_opendota` -> `resolve_identity` / `roster_coverage` ->
   `build_canonical` -> `universe` -> `build_dataset` (same order B0 used).
2. **Re-check the 16 rosters for last-minute stand-ins / swaps.** Compare each org's as-of-lock lineup
   to data/ti2026/inputs/teams.csv + canonical_identity.csv; update source ids only if a roster
   actually changed. Do NOT inherit strength across a roster change.
3. **Enter the official draw.** Copy data/ti2026/inputs/draw.example.json to draw.json; fill podA/podB
   (8 each) and r1_pairings from the POSTED draw (team names must match teams.csv 'team' exactly).
4. **Confirm the exact lock time** from the client countdown (hour:minute, timezone).
5. **Run the official slate** (use the exact confirmed lock time as a timezone-aware ISO timestamp so
   pre-lock same-day matches are included; 02:00:00Z below is the current best estimate - replace it
   with the confirmed in-client time):
   `python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z`
   The gate refuses unless the draw file (validated two-pod partition AND round-1 pairings), bt
   strengths, and cutoff are all present.
6. **Read + submit.** Outputs at predictions/ti2026/group-stage/ti15_group_prediction.{json,md}. Fill
   the client's 16 slots from the slate: 4-0 x1, 4-1 x2, decider_win x5, decider_loss x5, 1-4 x2,
   0-4 x1. Buckets flagged [selection-sensitive] are the least certain (mid-table). Submit in-client
   before lock.

## After the group stage (deferred)
- Main-event (14-series) prediction opens ~2026-08-16: build the bracket track (reuse
  simulate.double_elim) under the POSTED main-event seeding + official rules verification, then emit
  its own slate. Not started yet by design.

## Safety gates enforced by --official (not just runbook discipline)
- cutoff must be a timezone-aware ISO timestamp with a time (date-only is rejected);
- the local universe must be fresh: its latest map within 3 days of the cutoff, else the run is
  blocked (override with `--allow-stale` only if there truly are no pre-lock games);
- the draw file must be a valid two-pod partition of the 16 with complete round-1 pairings;
- the run records provenance in the manifest: universe rows + latest-map time, SHA-256 of
  teams.csv / canonical_identity.csv / universe_maps.csv / draw.json, git commit + dirty flag.

## Notes
- The official pipeline maximizes expected number correct (Hungarian) and then applies a VERIFIED
  expected-points refinement automatically: a swap search may propose a boundary-pair change, adopted
  only if an independent verification archive confirms a paired points gain > 2 se (evidence:
  backtest2/results-prelock-research.md sec 4). The manifest records proposed moves, the paired
  gain/se, and whether the refinement was adopted - submit the slate exactly as printed.
- No crowd pick-share exists in the client, so there is no anti-crowd / fusion step.
- Boundary watch from the pre-draw study: (BetBoom Team, Team Falcons) trade 4-1 / decider_win
  depending on the draw; expect the real draw + refreshed data to resolve it.
