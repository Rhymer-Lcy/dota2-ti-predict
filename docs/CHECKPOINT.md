# AUTHORITATIVE PROJECT CHECKPOINT (group stage LOCKED 2026-08-12; main event SERVED 2026-08-16)

Single source of truth for the frozen state. Do not reinterpret, reopen, or silently modify a frozen
decision. Git history and committed documents govern.

## Status at a glance
| Track | State | Artifact |
|---|---|---|
| Group-stage prediction (16 slots) | **LOCKED** - realized 6/16 (descriptive only, see below) | `predictions/ti2026/group-stage/ti15_group_prediction.{json,md}` |
| Main-event bracket (14 slots) | **READY TO SUBMIT** - lock 2026-08-20T02:00Z | `predictions/ti2026/playoffs/ti15_main_event_prediction.{json,md}` |
| Fantasy period 0 | **OPERATIONALLY SET / BEST-KNOWN PROVISIONAL** | states: `account_state_operator_20260812b.json`, `account_state_target_20260812d.json` |
| Fantasy period 1 | **NOT STARTED** - deliberately not opened | - |

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

# 1b. Main-event bracket - SERVED 2026-08-16, ready to submit

## What changed and what did not
The estimator is the **same frozen B-bt / h90 / lambda=1 / no-calibration specification** used for
the group stage; `gates.pipeline_identity_vs_locked_group_run` in the artifact proves it by refitting
the pre-TI state and reproducing the locked run's 8690 training maps and `c = +0.0932` exactly. What
changed is the DATA: the 39 completed Swiss series and the 5 Elimination Round series enter as
ordinary map-level observations. Frozen hyperparameters never meant frozen strengths.

## Three auditable states
| State | Cutoff | Train maps | Data |
|---|---|---:|---|
| A pre-TI | 2026-08-13T02:00Z | 8690 | historical universe only (reproduces the locked run) |
| B post-Swiss | 2026-08-15T18:00Z | 8787 | + 39 Swiss series (97 maps) |
| C serve | 2026-08-16T18:00Z | 8799 | + 5 Elimination series (12 maps) |
| control | 2026-08-16T18:00Z | 8690 | historical only at the serve decay origin - isolates decay from data |

A 2-0 expands to two map rows and a 2-1 to three, all sharing one `series_id`, so every series
carries total weight 1.0 exactly once (`w = 1/series_size`, the frozen convention). Round-1
timestamps are Tier 1 from Valve's league feed and reconcile with the reported round-1 pairings;
rounds 2-5 and the Elimination Round are placed on a labelled two-blocks-per-day cadence, and the
whole TI15 block collapsed onto one instant moves strengths by <= 0.0013 and does not change the
slate.

## Bracket topology - read, not typed
`ti_predict/bracket.py` reads the 14 playoff nodes out of the saved official league feed, rebuilds
each node's inputs from the winner/loser edges, cross-checks them against the feed's own
`incoming_node_id_*`, and fails closed on any mismatch. Verified shape: 4 UBQF + 2 UBSF + 1 UBF +
2 LBR1 + 2 LBR2 + 1 LBSF + 1 LBF + 1 GF, crossed lower bracket (a semi-final loser never meets the
quarter-final losers from its own half), Bo3 everywhere except a Bo5 Grand Final. The
`MAIN_EVENT_SCORE` vector is confirmed against the client-transcribed scoring rule.

## The optimization is exact
14 binary nodes give exactly 2^14 = 16,384 complete outcomes, and a COHERENT slate is itself one of
those outcomes, so the candidate set and the outcome space are the same 16,384 objects. Every
candidate is scored against every outcome - no Monte Carlo, no seed, no convergence argument.
Parameter uncertainty is integrated by averaging the outcome distribution over 1000 series-blocked
bootstrap draws before optimizing, which is exact because expected score is linear in that
distribution. Series-blocked means a Bo3 is one block; three maps never pose as three draws.

## Result
- Primary slate E[official score] **2287.5**, E[correct] 5.107, against greedy-favourite 2221.3.
- Champion probabilities: PARIVISION 0.348, Team Falcons 0.158, Team Yandex 0.138, BetBoom 0.113,
  Team Spirit 0.079, Team Liquid 0.067, Nigma Galaxy 0.062, Tundra Esports 0.036.
- **Slot 810 is a decision-theoretic tie, resolved quantitatively rather than asserted.** The
  runner-up differs only there (Nigma Galaxy vs Team Liquid). A 40,000-draw PAIRED bootstrap
  (`ti_predict/slate_compare.py`, both slates scored on the same draw) gives plug-in delta +5.25,
  bootstrap mean **+0.40** (MC SE 0.31, and by linearity that mean IS the delta under the
  bootstrap-averaged distribution the slate was chosen on), median +1.76, SD 62.9, 90% CI
  [-105.9, +101.5], 95% CI [-127.0, +120.4], **P(delta > 0) = 0.511**. MC SE falls at the 1/sqrt(n)
  rate across n = 1k..40k (2.01 -> 0.31) while the mean wanders inside +/-2.5, so the estimate has
  converged and the two slates are statistically indistinguishable: the interval is wider than a
  whole correct node in each direction and the mean is under 0.4% of one. **The client pick stays
  Nigma Galaxy** - the official-score objective still has a unique argmax, so a tie in evidence is
  not an abstention. Detail: `research/slot810_tiebreak_20260816.json`. The full slate is also
  identical under an independent bootstrap seed (20260817).
- Six late-bracket nodes are flagged fragile (806, 810, 811, 812, 813, 814); the four quarter-finals
  and the PARIVISION line are not.

## Auxiliary assimilation diagnostic - DOWNGRADED, and not a playoff replay
`ti_predict/sequential_assimilation.py` (formerly mislabelled `stage_replay.py`). **This is not a
group/Swiss-to-playoff replay and must never be reported as one.** The rating universe has no stage
field, so there is no local record of which series were group and which were playoff and no stage
boundary exists to replay. Each league is split CHRONOLOGICALLY at a fraction of its own series, the
fraction is swept (0.4/0.5/0.6/0.7) and never tuned, and the question asked is only the weak one:
does assimilating a league's earlier results improve prediction of its later results.

Two populations are reported side by side, because the broad one is not a tournament population:

| population | leagues @ f=0.6 | what it is |
|---|---:|---|
| `all` | 39 | every league passing the structural minimums. Includes **season-long leagues** (Destiny 808 series, Ultras 815, Space League 349) and streamer/exhibition events, none of which has a group-to-playoff arc. The three largest supply about **half** the map weight. |
| `folds` | 19 | only `inputs/folds.csv` leagues - the preregistered set, i.e. discrete tournaments. The relevant population for a TI-like event. |

- **Supported:** on `all`, assimilation improves later-league prediction by 0.009-0.020 nats of
  side-aware log-loss, significant at every fraction under **both** map and event weighting.
- **NOT established:** the same effect on discrete tournaments alone. On `folds` it is positive in
  direction at all four fractions (11-15 of 16-19 leagues improve) but significant under **both**
  weightings at only **1 of 4** (f=0.5). f=0.4 clears the bar map-weighted only; **f=0.6 and f=0.7
  clear it under neither** - and those two are the shapes nearest TI15's own long-Swiss-then-bracket
  structure.
- **Therefore no empirical warrant is claimed** for "observing the TI15 Swiss improves Main Event
  prediction". Production assimilates the 44 series because that is what the frozen sequential
  estimator does, not because this diagnostic validated it.

Selection rule, fixed before any arm was scored and referring only to structure: a valid
chronological split; >= 6 early series; >= 10 late maps whose both teams appeared early; non-empty
pre-league training data. No criterion touches a league's outcomes or the model's error on it, and a
test rebuilds the included set from counts alone to prove it. Full manifest of the 39 included and
18 excluded leagues: `predictions/ti2026/playoffs/research/sequential_assimilation_20260816.json`.

The one load-bearing finding is negative and it holds everywhere: the **audit-predeclared**
shrinkage diagnostic (kappa 0.25/0.50/0.75 against the plain refit) **never beats** kappa=1. Where the family separates at
all it is significantly *worse*, and kappa=0.75 flips sign between weightings. **Production is the
plain frozen sequential refit, unchanged.** TI15 is excluded from the diagnostic by construction.

## Model vs standings tension - reported, never overridden
The estimator ranks Team Yandex 3rd on strength while the Swiss table ranks them 11th. That is not a
defect and was not corrected: Yandex carry a 0.666 decayed map win rate over 114 maps against LGD,
Tundra, Liquid, PARIVISION, Aurora, BetBoom, Spirit and Falcons, and all three of their Swiss losses
were 1-2. Nigma Galaxy run the other way (Swiss 3rd, model 7th) on the thinnest record in the field,
68 maps, which is also why they carry the largest bootstrap SD (0.202) and the largest TI15 update
(+0.174). A manual override here is exactly what the freeze forbids.

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
- Main-event track: `ti15_results.py` (the 44 verified series + map expansion), `bracket.py`
  (feed-verified topology, exact enumeration, coherent-slate search),
  `sequential_assimilation.py` (auxiliary diagnostic), `slate_compare.py` (paired near-tie
  resolution), `predict_main_event.py` (the end-to-end run).
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

1. **Submit the bracket** before 2026-08-20T02:00Z (10:00 Asia/Shanghai). The client opens the
   question at 2026-08-17T01:00Z. Reconfirm the in-client countdown, as on group-stage lock day.
   Re-running `predict_main_event` before submitting is free and changes nothing unless the local
   universe changes - no Main Event match may enter the fit.
2. Fantasy period 1 - new roster lock, new banner, tokens carry over
   (`future_stage_tokens = 30` on the friend's account). Re-run `coach_optimize` against
   `account_state_target_20260812d.json` first; the committed pricing describes a superseded banner.
3. Carry-forward chores: fix Tundra's stale `ti_alias`; resolve
   `stat_reroll_outcome_distribution` (the friend has spent 32 tokens against it
   unmodelled, and 6 remain).

# 5. Discipline

Conventional Commits, subject <= 72 characters and ASCII (hook-enforced). Production is never
updated from crowd percentages, odds, or results, and is not re-tuned on TI2024/TI2025 outcomes.
JSON is the machine fact source; Markdown is rendered from it. One fact, one place.
