# AUTHORITATIVE PROJECT CHECKPOINT (group stage LOCKED 2026-08-12)

Single source of truth for the frozen state. Do not reinterpret, reopen, or silently modify a frozen
decision. Git history and committed documents govern.

## Status at a glance
| Track | State | Artifact |
|---|---|---|
| Group-stage prediction (16 slots) | **LOCKED** | `predictions/ti2026/group-stage/ti15_group_prediction.{json,md}` |
| Fantasy period 0 | **OPERATIONALLY SET / BEST-KNOWN PROVISIONAL** | states: `account_state_operator_20260812b.json`, `account_state_target_20260812d.json` |
| Main event / period 1 | **NOT STARTED** - next phase, deliberately not opened | - |

---

# 1. Group stage - LOCKED

## Frozen production specification
- Model: identity side-neutral Bradley-Terry (B-bt); ridge lambda = 1.
- Time-decay half-life: 90 days (`contest_rules.PRODUCTION_HALF_LIFE_DAYS`), applied explicitly.
- Map probability: side-neutral `0.5*(sigmoid(d+c) + sigmoid(d-c))`, `d = strength_a - strength_b`,
  `c` = train-only radiant coefficient at the cutoff (+0.0932).
- Calibration: none (no Platt, no temperature).
- Solver: Hungarian max-expected-correct, then the independently verified `points_refinement`
  (adopted only if a separate verification archive shows a paired gain > 2 bootstrap se).
- D4 opponent choice: strategic primary; noisy / random reported as common-random-numbers sensitivity.
- Market odds: diagnostic only, never fused, never a promotion input.
- LGD / Topson: no manual signed strength adjustment; a player-aware production adjustment remains
  inadmissible before TI2026.
- Selection evidence and the closed challenger rounds: `docs/validation-plan-v2.md`,
  `backtest2/results-adversarial.md`, `backtest2/results-post-r1.md`.

## The locked run
- `predictions/ti2026/group-stage/ti15_group_prediction.{json,md}` - JSON is the fact source, the
  Markdown is rendered from it.
- Mode `official`, generated from a clean tree at commit `db16aa9`
  (`git_dirty_at_start = false`), cutoff 2026-08-13T02:00:00Z, seed 20260813,
  **280000 simulations** over 35 admissible pod memberships, E[correct] **5.249**.
- **Slate:** 4-0 PARIVISION; 4-1 Team Yandex, BetBoom Team; decider_win Team Falcons, Aurora Gaming,
  Team Spirit, Team Liquid, Nigma Galaxy; decider_loss Xtreme Gaming, Vici Gaming, Tundra Esports,
  LGD Gaming, Team Resilience; 1-4 HULIGANI, GamerLegion; 0-4 OG.
- Client display names differ from canonical organisations: PARIVISION = TEAM VISION,
  BetBoom Team = BOOMBOYS, Tundra Esports = **IRON WING**. `teams.csv` still records Tundra's
  `ti_alias` as `1w Team`, which is stale against both the official feed and the client. The field is
  display-only (`build_canonical`, `resolve_identity`, manifest) and never enters strength
  estimation, so it was deliberately NOT edited on lock day. Fix it in the next phase.

## Lock-day audit (2026-08-12), all negative
Re-ran the full input audit and the production pipeline; **NO MATERIAL INPUT CHANGE**.
- `teams_sha256`, `canonical_identity_sha256`, `universe_sha256`, `draw_sha256`: all four identical
  to the 2026-08-10 submission-grade candidate.
- A complete re-scan (92 pages, 9200 pro matches, `coverage_complete = true`, latest
  2026-08-12T15:40Z) found 26 matches newer than the universe's last map, **all** in EPL Masters 2026
  (league 19944) between eight non-TI organisations. Rebuilding produced a **byte-identical**
  `universe_maps.csv`. The earlier override note ("no professional match exists before the cutoff")
  was therefore corrected to "matches exist, none within the universe's scope".
- Official feed `sha256` changed (`41b53f0e` -> `dd129ecd`) from `prize_pool` only; the eight round-1
  pairings, `scheduled_time`, `advancing`, and `win_loss_limit` are unchanged.
- The feed carries TI-branded team ids (`10150413` Iron Wing, `9572001` TEAM VISION, `5017210`,
  `8261500`) where `teams.csv` deliberately uses the re-resolved ids that carry the recent maps.
  Same organisations, verified individually.
- Pod membership **still unpublished**: no `node_group` carries a team list. Marginalisation over 35
  memberships stands.
- Rosters: no change since the LGD position-2 TaiLung -> Topson substitution
  (`data/ti2026/inputs/roster_events.csv`).
- Result: every bucket identical to the 2026-08-10 candidate, E[correct] identical to four decimals.
  **KEEP CURRENT SUBMISSION - NO CHANGES.**

## Event facts
- **Round 1: OFFICIAL**, eight pairings from Valve's league feed (league_id 19719), parsed into
  `data/ti2026/inputs/draw.json` by `ti_predict/league_feed.py`.
- **Lock time: 2026-08-13T02:00:00Z** (10:00 UTC+8). The in-client countdown is the final authority.
- **Two-pod structure: CONFIRMED** by the official rules page. **Pod membership: UNRESOLVED.**
  `open-16` is a sensitivity comparator and is refused in official mode.

## Simulation count doctrine (not a model constant, not a gate)
- Pod membership CONFIRMED: `--sims 120000`. UNRESOLVED: 140000 calibrated minimum, **280000
  recommended and used**.

## Freshness override: strict conditions
`--allow-stale` is a request to check, not a claim. Gated modes read
`processed/scan_provenance.json` and refuse unless it is present, well-formed,
`coverage_complete = true`, no older than `STALE_MAX_DAYS`, and describes at least the data the
universe holds. Data-coverage freshness and latest-eligible-match recency stay separate fields.

## Provenance semantics
`provenance.git_commit_at_start` / `git_dirty_at_start` are sampled BEFORE any work. The locked
official run carries `git_dirty_at_start = false`.

---

# 2. Fantasy period 0 - OPERATIONALLY SET

## Two accounts, never interchangeable
**Current operational state - these two files, nothing earlier:**

| File | Account | Teams (core / mid / support) | Coach | Tokens |
|---|---|---|---|---|
| `account_state_operator_20260812b.json` | **operator's own** | Xtreme / **Team Falcons** / Xtreme | Elemental + the Tormented | 10 |
| `account_state_target_20260812d.json` | friend's TARGET ACCOUNT | Xtreme / Team Yandex / Xtreme | Elemental + the Tormented | 6 |

Both are graded `user_runtime_observation` from client screenshots (2026-08-12T16:00Z).

History is append-only and complete: `account_state_target_*` runs states 1-7 and
`account_state_operator_*` states 1-2. Every earlier file is referenced by
`tests/test_fantasy_account_state.py`; none may be moved or deleted, and none is a current pointer.

Changes captured in this sync:
- Friend: roll tokens 38 -> 6, spent rerolling. **Seven of nine slots changed** (all nine stats are
  the same; only qualities and traits moved): core gpm 1.8->1.5, roshan 1.2->2.1, cs 1.8->3.2;
  mid stuns 1.4->1.7; support runes 1.8->2.9, first blood 1.3->1.5, watchers 1.3->1.8. The state-6
  coach grading is upgraded from `reported_by_operator` to `user_runtime_observation`.
- Operator: **Mid changed Team Yandex -> Team Falcons**, which was the standing recommendation, so
  it is now recorded as applied rather than issued. Free and banner-preserving: all nine multipliers
  re-verified unchanged against `banner_model.slot_weights` at write time.

**Known staleness, deliberately not resolved in this sync.** `coach_pricing_20260812.json` was
computed on the state-6 banner. Seven of the friend's nine slots have since changed, so its joint
gains describe a superseded banner. The Coach choice was NOT re-derived here, by instruction. Before
those numbers are used again, re-run:
`python -m ti_predict.fantasy.coach_optimize --state predictions/ti2026/fantasy/account_state_target_20260812d.json --draws 4000 --out <path>`.
The generator has no default state - `--state` is required - so nothing silently reads an old one.
The friend's state-7 slots record only stat and displayed multiplier, so `banner_model` cannot
re-derive them; supply tier/trait/colour to restore that check.

## Frozen scoring chain
player-game -> role mean -> top two maps in a series -> best series in the period -> **event-equal
block estimator** -> frozen TI exposure. Banner composition is
`multiplier = 1 + quality_bonus + net_trait_bonus`, validated on 18 emblems across two accounts plus
two before-the-fact predictions, and re-validated on all nine of the operator's slots.

## Settled facts
- Coach titles change for **0 roll tokens** and reversibly (`coach_titles.confirmed`).
- Team change via the War Banner button is free and preserves the banner; duplicate teams across
  roles are allowed.
- All eight suffix bonuses agree four ways (client, Kadadji, MyKa322, ruleset). Seven suffixes are
  scored exactly; the Tormented is counted directly off `npc_dota_miniboss` in `killed_by`.
- Data coverage: `match_extras.csv` and `death_positions.csv` are both 623/623, 0 failed.

## Operator recommendation - APPLIED
Core Xtreme Gaming (kept) - Mid **Team Yandex -> Team Falcons, executed** (+4.03% over Aurora; the
previously held team ranked 13th at 0.649 relative) - Support Xtreme Gaming (kept, +14.08%) - Coach
kept Elemental + the Tormented. Computed on the operator's banner, which this sync confirms
unchanged.

## Remaining unknowns (all SCALE_ONLY or bounded; none blocks period 0)
- `elemental_predicate_completeness` - our flag is `isaquatic`, the condition is Aquatic/Fiery/Icy;
  no source recovers the rest. Stressed to 50% of eligible player-games under adversarial placement
  without flipping the winner.
- `fountain_death_positions` - `deaths_pos` exists in `teamfights[].players[]` (41.0% of deaths) but
  is a per-fight histogram, so no death can be tied to its killer and the fountain cannot be
  calibrated. Corner upper bound 0.0000-0.0016 at any fountain-sized radius.
- `historical_event_aggregation` / `historical_event_recency_weighting` - estimator choices, not
  facts. Event-equal is selected; recency half-lives 180/90/60/30 do not flip the winner.
- `cross_role_predictive_dependence` - default `by_organization` (Core and Support are the same club
  and play the same series). The predictive tail is NOT a usable discriminator.
- `title_stacking` - still UNRESOLVED as a fact, ROBUST for the decision.
- `stat_reroll_outcome_distribution` - still BLOCKING; green stat rerolls stay untouched.
- Scoring coverage gaps: Watchers Taken, Lotuses Gained, Tormentor Kills have no public per-map
  source. On the operator's Support banner this leaves only Wards Planted scoreable, 1.20 of 6.30.

## Withdrawn claims - traceable, never live
Ten superseded conclusions are recorded under `withdrawn_claims` in
`coach_pricing_20260812.json` with the reason each failed. They must not reappear in any live
recommendation. A regression test asserts no superseded prose survives outside that block.

---

# 3. Code and tests

- `ti_predict/`: `swiss.py`, `assign.py`, `predict_ti15.py` (dry-run / candidate / official),
  `league_feed.py`, `rosters.py`, `contest_rules.py`, plus the data layer.
- `ti_predict/fantasy/`: `banner_model.py` (exact three-slot evaluator), `account_state.py`,
  `baseline.py`, `preselection.py`, `coach_optimize.py` (joint pricing, Cartesian scenario family,
  nested adversarial search), `cruel_bound.py`, and the four fetchers.
- `backtest2/`: closed study modules.
- Tests: `python -m pytest -q` -> **349 passed**. The suite takes ~4 minutes because the artifact
  rebuild test re-runs the full nested adversarial search; that is deliberate.
- Pipeline defects found and fixed, all of the same class (a partial or duplicated fact written
  silently): `resolve_identity` overwriting the deep scan and the canonical table; `roster_coverage`
  dropping organisations on transient errors; a stale fold table; a cross-drive `relpath` crash;
  a hand-typed `SUFFIX_BONUS` copy that had three wrong values; cross-event pooling behind a
  docstring that claimed the opposite; a player-map denominator on match-level events; a shared RNG
  stream across roles; and a hardcoded coach prefix in the generator.

# 4. Where the next phase starts

Main event / period 1. Nothing below has been opened, and none of it should be started before the
group stage resolves:
1. Bracket predictions (14 slots, ids 801-814) - the second out-of-game prediction set.
2. Fantasy period 1 - new roster lock, new banner, tokens carry over
   (`future_stage_tokens = 30` on the friend's account).
3. Carry-forward chores: fix Tundra's stale `ti_alias`; resolve
   `stat_reroll_outcome_distribution` (the friend has spent 32 tokens against it
   unmodelled, and 6 remain).

# 5. Discipline

Conventional Commits, subject <= 72 characters and ASCII (hook-enforced). Production is never
updated from crowd percentages, odds, or results, and is not re-tuned on TI2024/TI2025 outcomes.
JSON is the machine fact source; Markdown is rendered from it. One fact, one place.
