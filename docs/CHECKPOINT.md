# AUTHORITATIVE PROJECT CHECKPOINT (frozen 2026-08-10, pre-lock-day)

Single source of truth for the frozen state. Do not reinterpret, reopen, or silently modify a frozen
decision. Git history and committed documents govern.

## Status
The repository is FROZEN until the lock-day final run. A submission-grade candidate has passed every
production gate, and the only work left is the lock-day re-verification listed at the bottom.

## Frozen production specification
- Model: identity side-neutral Bradley-Terry (B-bt); ridge lambda = 1.
- Time-decay half-life: 90 days (`contest_rules.PRODUCTION_HALF_LIFE_DAYS`), applied explicitly.
- Map probability: side-neutral `0.5*(sigmoid(d+c) + sigmoid(d-c))`, `d = strength_a - strength_b`,
  `c` = train-only radiant coefficient at the cutoff (currently +0.0932).
- Calibration: none (no Platt, no temperature).
- Solver: Hungarian max-expected-correct, then the independently verified `points_refinement`
  (adopted only if a separate verification archive shows a paired gain > 2 bootstrap se).
- D4 opponent choice: strategic primary; noisy / random reported as common-random-numbers sensitivity.
- Market odds: diagnostic only, never fused, never a promotion input.
- LGD / Topson: no manual signed strength adjustment; a player-aware production adjustment remains
  inadmissible before TI2026.
- Selection evidence and the closed challenger rounds: `docs/validation-plan-v2.md`,
  `backtest2/results-adversarial.md`, `backtest2/results-post-r1.md`.

## Event facts as of the freeze
- **Round 1: OFFICIAL.** All eight pairings from Valve's league feed (league_id 19719), every team id
  resolved through `canonical_identity.csv` `source_team_ids`; parsed into
  `data/ti2026/inputs/draw.json` by `ti_predict/league_feed.py`.
- **Lock time: 2026-08-13T02:00:00Z** (10:00 UTC+8), Tier-1 from two independent Valve channels
  (blog wording and the feed's `scheduled_time` on every round-1 node). The in-client countdown is
  still the final check on the day.
- **Two-pod structure: CONFIRMED** by the official TI15 rules page (round 1 splits the field into two
  initial groups and pairs within them; rounds 2-3 pair inside a team's group; round 4 pairs across).
- **Pod membership: UNRESOLVED.** No source publishes the eight-team split; the feed's lack of a pod
  field is a gap in the feed, not evidence about the format. The official run marginalizes over the
  35 memberships compatible with round 1. `open-16` is a sensitivity comparator and is refused in
  official mode.
- **LGD Gaming position 2: TaiLung (banned for tournament integrity) -> Topson**, recorded with full
  provenance in `data/ti2026/inputs/roster_events.csv` (account ids 1026694469 -> 94054712). The
  other 15 lineups are CONFIRMED unchanged; the Team Liquid Nisha / Miracle! source conflict is
  resolved (Nisha, from match data). Note `canonical_identity.csv` is the OBSERVED five from match
  data, so it still lists TaiLung by construction - `roster_events.csv` is the roster of record.

## Current submission-grade candidate
- Artifact: `predictions/ti2026/group-stage/candidates/ti15_group_candidate_20260810T095746Z.{json,md}`
  (JSON is the fact source; the Markdown is rendered from it).
- Generated at commit `7a767c7`, cutoff 2026-08-13T02:00:00Z, seed 20260813, **280000 simulations**
  over 35 admissible pod memberships, E[correct] 5.249.
- Gates: all passed. Membership agreement 14/35 identical slates, max held-out regret 0.0199 against
  the 0.05 limit; `points_refinement` proposed no move (Hungarian stands); D4 zero slot changes.
- **Slate (0 slot changes from the post-round-1 provisional):** 4-0 PARIVISION; 4-1 Team Yandex,
  BetBoom Team; decider_win Team Falcons, Aurora Gaming, Team Spirit, Team Liquid, Nigma Galaxy;
  decider_loss Xtreme Gaming, Vici Gaming, Tundra Esports, LGD Gaming, Team Resilience; 1-4 HULIGANI,
  GamerLegion; 0-4 OG.
- The candidate is NOT the final run and never occupies the official path or label.

## Simulation count doctrine (not a model constant, not a gate)
- Pod membership CONFIRMED: `--sims 120000` (the floor set by points-refinement gate power).
- Pod membership UNRESOLVED: **140000 is the calibrated minimum** (4000 per membership; below that
  the membership gate blocks on Monte-Carlo noise) and **280000 is the recommended lock-day value**
  (8000 per membership). `POD_MEMBERSHIP_REGRET_MAX` and the refinement threshold are unchanged.

## Freshness override: strict conditions
`--allow-stale` is a request to check, not a claim. In gated modes the run reads
`processed/scan_provenance.json` (written by `scan_promatches`) and refuses the override unless it is
present, well-formed, `coverage_complete = true`, no older than `STALE_MAX_DAYS`, and describing at
least the data the universe holds. The manifest then records `stale_override_used` plus a reason
built from those facts, and keeps **data-coverage freshness** and **latest-eligible-match recency**
as separate fields.

## Provenance semantics
`provenance.git_commit_at_start` / `git_dirty_at_start` are sampled BEFORE any work: they describe
the tree the run started from, and nothing the run writes can change them. Start the final official
run from a clean tree so the emitted manifest carries `git_dirty_at_start = false`. A dirty start is
a warning, not a hard block - that policy is unchanged.

## Code state
- `ti_predict/`: `swiss.py` (rules-based Swiss + decider; admissible-membership enumeration; the
  open-16 comparator), `assign.py` (Hungarian), `predict_ti15.py` (three gated modes: dry-run /
  candidate / official), `league_feed.py` (official draw ingest), `rosters.py` (roster audit),
  `contest_rules.py` (all official constants), plus the data layer.
- `backtest2/`: `post_r1.py` (membership-marginalized research), `roster_sensitivity.py`,
  `market_check.py`, and the closed study modules.
- Pipeline defects found and fixed during the lock-period rounds, all of the same class (a partial
  result being written silently): `resolve_identity` overwriting the deep pro-match scan;
  `resolve_identity` overwriting the tracked canonical identity table on a partial run;
  `roster_coverage` dropping organizations on transient API errors; a stale fold table; and a
  cross-drive `relpath` crash after a successful `--out` run. Each now fails closed, with tests.

## Tests
`python -m pytest -q` -> **85 passed** (data-dependent tests auto-skip on a clean clone). Coverage
includes: official constants; simulator structure and both pod structures; assignment; the three
gated modes; draw structure / membership semantics; roster audit; scan provenance and the freshness
override (missing, malformed, incomplete-coverage, stale); git provenance field naming; membership
marginalization and its regret measurement; failure modes.
Also: `python -m ti_predict.swiss`, `... .assign`, `... .league_feed`, `... .rosters`,
`... .predict_ti15 --dry-run`.

## Lock-day final run - the only remaining work
1. Confirm the exact in-client lock countdown (expected 2026-08-13T02:00:00Z).
2. Re-check whether the pod membership has been published; if so fill `podA`/`podB` and set
   `pod_membership_status = confirmed`.
3. Run the full fail-closed data refresh (`docs/lockday-runbook.md` step 1) so any 2026-08-10..13
   matches are included and the scan provenance is current.
4. Re-verify all 16 rosters and update `roster_events.csv`.
5. Run `--official` from a clean tree with the sims count for the membership state, then submit the
   slate exactly as printed, at least an hour before the lock.

## Discipline
Conventional Commits, subject <= 72 characters and ASCII (hook-enforced). Production is never updated
from crowd percentages, odds, or results, and is not re-tuned on TI2024/TI2025 outcomes.
