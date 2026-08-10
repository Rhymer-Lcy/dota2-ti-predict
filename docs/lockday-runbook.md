# Lock-day runbook - TI15 group-stage prediction (2026-08-13)

Production model is FROZEN: B-bt, half-life 90 (applied explicitly in the production path), identity
side-neutral, no calibration layer, no crowd% fusion (docs/CHECKPOINT.md, validation-plan-v2.md).

**Lock = the first group-stage match = 2026-08-13T02:00:00Z (10:00 UTC+8).** Tier-1 confirmed twice
over: Valve's blog wording and, since 2026-08-10, the league feed's own `scheduled_time` on every
round-1 node (docs/contest-official-ti15.md sec 5). Still reconfirm the in-client countdown and
submit >= 1 h early - a published schedule can move.

## State entering lock day (2026-08-10)
- **Round 1 is posted and ingested.** `data/ti2026/inputs/draw.json` is generated from the league
  feed; `r1_status = official`.
- **The pod split is not published anywhere** and may not exist (the feed shows one undivided
  16-team Swiss). `pods_status = unresolved`, and the official run FAILS CLOSED on it by design.
- **One roster change:** LGD position 2, TaiLung (banned) -> Topson, recorded in
  `data/ti2026/inputs/roster_events.csv`. The other 15 lineups are confirmed unchanged.
- Latest professional map in the universe: 2026-08-09T19:02Z. No pro match is scheduled between then
  and the lock, so the freshness gate will need an explicit, verified override (step 4).

## Steps
1. **Refresh the pro-match universe.**
   `python -m ti_predict.scan_promatches` (deep scan, merges, fails closed on coverage regression)
   -> `python -m ti_predict.resolve_identity` (re-resolves ids/rosters; merges the scan, writes only
   `processed/identity_resolved.csv`, exits non-zero unless all 16 five-player rosters resolve)
   -> `roster_coverage` -> `build_canonical` -> `universe` -> `build_dataset` -> `universe` again.
   The final `universe` re-run is required: it stamps `is_target` and the fold table from the JUST
   rebuilt dataset, and skipping it leaves both stale (found 2026-08-10).
   Verify: universe row count and window printed by `universe`, and the merged scan window printed
   by `scan_promatches`. Coverage must never shrink.
   Do NOT stop the chain half-way: `build_canonical` is the only writer of the tracked
   `inputs/canonical_identity.csv`, and the rating universe resolves organizations through its
   `source_team_ids` column.
2. **Re-check the 16 rosters** and update `data/ti2026/inputs/roster_events.csv`. Status must be
   CONFIRMED or CHANGED for all 16; a CONFLICT or UNRESOLVED row blocks the official run on purpose.
   A CHANGED row needs the full provenance (role, both nicknames, both numeric account ids, reason,
   eligibility, announcement time, evidence tier, source). Never infer an account id from a nickname.
   `python -m ti_predict.rosters` prints the summary.
3. **Re-pull the draw and check whether pods appeared.**
   `python -m ti_predict.league_feed --fetch --write-draw`
   - If a pod split is published (in-client, feed, or an official post): add `podA`/`podB` (8 teams
     each, names exactly as in teams.csv) to `draw.json` and set `"pods_status": "confirmed"`.
   - If no pod split is published anywhere by lock time, decide EXPLICITLY between two paths, and
     record which one you took:
     (a) accept Valve's league feed - a single undivided 16-team Swiss node group - as the published
         format, and declare it: `"pods_status": "confirmed", "structure": "open-16"`. That is a
         positive, evidenced claim, it is recorded in the manifest, and it unblocks the official run.
     (b) leave it `unresolved`; the official run stays blocked and the decision rests on
         `python -m backtest2.post_r1` (R1-fixed, pod structure marginalized), whose slate is then
         submitted by hand.
     Both currently give the SAME 16 slots - the open and two-pod families agree - so this choice is
     about what the artifact claims, not about the picks. What is NOT allowed is inventing a pod
     split, or leaving the file saying "confirmed two-pod" when nothing published one.
4. **Confirm the exact lock time** from the in-client countdown (hour:minute, timezone). Expected
   2026-08-13T02:00:00Z.
5. **Run the official slate** (only once every gate is satisfied):
   `python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 120000`
   120000 simulations: the points-refinement gate has about 94% power there vs about 80% at the 40000
   default (backtest2/results-adversarial.md).
   **Freshness override.** If no professional match is played between the universe's latest map and
   the lock, the 3-day freshness gate will block a genuinely up-to-date universe. Only then append
   `--allow-stale`, and only after re-running step 1 and confirming the scan found nothing newer.
   The manifest records `provenance.freshness_gate.overridden = true`, so the override is never
   silent.
6. **Read + submit.** Outputs at `predictions/ti2026/group-stage/ti15_group_prediction.{json,md}`.
   Fill the client's 16 slots from the slate: 4-0 x1, 4-1 x2, decider_win x5, decider_loss x5,
   1-4 x2, 0-4 x1. Buckets flagged [selection-sensitive] are the least certain (mid-table). Submit
   in-client before the lock.

## After the group stage (deferred)
- Main-event (14-series) prediction opens ~2026-08-16: build the bracket track (reuse
  simulate.double_elim) under the POSTED main-event seeding + official rules verification, then emit
  its own slate. Not started yet by design.

## Safety gates enforced by --official (not just runbook discipline)
- cutoff must be a timezone-aware ISO timestamp with a time (date-only is rejected);
- the draw file must carry complete round-1 pairings AND a confirmed pod structure; `pods_status`
  other than `confirmed` blocks the run;
- when pods are published they must be a valid two-pod partition of the 16 and round 1 must not
  cross them;
- the roster audit must have no CONFLICT / UNRESOLVED team;
- the local universe must be fresh: latest map within 3 days of the cutoff, else blocked (override
  with `--allow-stale`, which is recorded in the manifest);
- the run records provenance in the manifest: universe rows + latest-map time, SHA-256 of
  teams.csv / canonical_identity.csv / universe_maps.csv / draw.json, git commit + dirty flag,
  draw publication status, and the roster audit.

## Notes
- The official pipeline maximizes expected number correct (Hungarian) and then applies a VERIFIED
  expected-points refinement automatically: a swap search may propose a boundary-pair change, adopted
  only if an independent verification archive confirms a paired points gain > 2 se (evidence:
  backtest2/results-prelock-research.md sec 4, corrected in results-adversarial.md). The manifest
  records proposed moves, the paired gain/se, and whether the refinement was adopted - submit the
  slate exactly as printed.
- No crowd pick-share exists in the client, so there is no anti-crowd / fusion step.
- Boundary watch after the posted round 1 (backtest2/results-post-r1.md): the 4-1 pair
  (Yandex / BetBoom / Falcons), OG vs GamerLegion vs HULIGANI at the bottom, and Nigma in the middle.
