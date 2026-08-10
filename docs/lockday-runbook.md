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
- **The two-pod structure is an official rule; only the pod MEMBERSHIP is unpublished.**
  `structure = two_pod` / `structure_status = confirmed` / `pod_membership_status = unresolved`. An
  official run marginalizes over the 35 memberships compatible with round 1 rather than assuming one.
- **One roster change:** LGD position 2, TaiLung (banned) -> Topson, recorded in
  `data/ti2026/inputs/roster_events.csv`. The other 15 lineups are confirmed unchanged.
- Latest professional map in the universe: 2026-08-09T19:02Z. No pro match is scheduled between then
  and the lock, so the freshness gate will need an explicit, verified override (step 4).

## Steps
1. **Refresh the pro-match universe.**
   `python -m ti_predict.scan_promatches` (deep scan, merges, fails closed on coverage regression;
   also writes `processed/scan_provenance.json`, which the freshness override in step 5 requires)
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
3. **Re-pull the draw and check whether the pod membership appeared.**
   `python -m ti_predict.league_feed --fetch --write-draw`
   - If the membership is published (in-client, feed, or an official post): add `podA`/`podB`
     (8 teams each, names exactly as in teams.csv) and set `"pod_membership_status": "confirmed"`.
     Round 1 must not cross the pods; the gate checks it.
   - If it is still unpublished: leave `"pod_membership_status": "unresolved"`. The official run then
     marginalizes over all 35 round-1-compatible memberships and records that in the manifest.
     **Never** invent a membership, and never downgrade the structure: `open-16` is a sensitivity
     comparator, not the official format, and official mode refuses it.
4. **Confirm the exact lock time** from the in-client countdown (hour:minute, timezone). Expected
   2026-08-13T02:00:00Z.
5. **Run the official slate** (only once every gate is satisfied):
   - pod membership **CONFIRMED** -> `--sims 120000`
     `python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 120000`
   - pod membership **UNRESOLVED** -> `--sims 280000` (the recommended lock-day value)
     `python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 280000`

   `--sims` is the TOTAL simulation count, split evenly across the admissible memberships.
   **120000** is the floor set by points-refinement gate power (about 94% there vs about 80% at the
   40000 default, backtest2/results-adversarial.md) and is sufficient once there is a single
   structure. With the membership unresolved, **140000 (4000 per membership) is the calibrated
   MINIMUM** - the membership gate compares 35 held-out regret estimates and below roughly 4000 each
   it blocks on Monte-Carlo noise rather than on a real effect (measured 2026-08-10: 0.206 at
   500/membership, 0.064 at 1000, 0.032 at 4000, against the 0.05 limit) - and **280000 (8000 per
   membership) is the RECOMMENDED lock-day value**, which took the same measurement to 0.020 and cuts
   per-cell Monte-Carlo error on the thin top and bottom boundaries. Neither number is a model
   constant or a gate: `POD_MEMBERSHIP_REGRET_MAX` and the refinement threshold are unchanged.
   **Freshness override.** If no professional match is played between the newest eligible match and
   the lock, the 3-day recency gate will block a genuinely up-to-date universe. Only then append
   `--allow-stale`. It is not an assertion the operator makes: the run reads
   `processed/scan_provenance.json` (written by step 1) and refuses the override unless that file is
   present, well-formed, `coverage_complete = true`, no older than 3 days, and describing at least
   the data the universe holds. The manifest then records `stale_override_used` together with a
   reason built from those recorded facts, and keeps data-coverage freshness and latest-match
   recency as separate fields.
   **On the git fields.** `provenance.git_commit_at_start` / `git_dirty_at_start` are sampled
   BEFORE any work, so they describe the tree the run started from and nothing the run writes can
   change them. Start the final official run from a clean tree: `git_dirty_at_start` must be
   `false` in the emitted manifest. A `true` there means real uncommitted code or inputs - commit or
   stash them and re-run rather than explaining it away.
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
- the draw file must carry complete round-1 pairings AND `structure_status = confirmed`; an assumed
  structure, or the `open-16` comparator, is refused;
- a published membership must be a valid two-pod partition of the 16 that round 1 does not cross;
- an unresolved membership is marginalized, and the run is blocked if the worst admissible
  membership would beat the marginalized slate by more than
  `contest_rules.POD_MEMBERSHIP_REGRET_MAX` expected correct (held-out);
- the roster audit must have no CONFLICT / UNRESOLVED team;
- the newest eligible professional match must be within 3 days of the cutoff, else blocked;
  `--allow-stale` is accepted only when `processed/scan_provenance.json` records a complete, current
  scan, and the manifest then carries `stale_override_used` plus a reason built from that record;
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
