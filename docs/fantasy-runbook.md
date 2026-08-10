# TI2026 Compendium track: Fantasy and Predictions runbook

Scope: everything the TI2026 client asks the entrant to answer that is **not** the 16-slot group-stage
prediction. The group-stage track is frozen; this document never changes it. The only thing that
crosses between the two is schedule exposure (which teams play how many series), and it crosses one
way: the frozen Swiss simulator is read as an input here and is not re-tuned to serve this track.

Fact source: `data/ti2026/inputs/prediction_questions.json` and
`data/ti2026/inputs/fantasy/fantasy_rules.json`. This document is prose about them; where the two
disagree, the JSON wins. Validate both with `python -m ti_predict.fantasy.questions`.

## 1. What exists

The Compendium has five tabs: Rewards, Fantasy, Predictions, Team Bundles, Talent Bundles.

Two of them carry scoring, and they are **separate tracks, not two halves of one**:

- **Predictions** holds exactly **two out-of-game prediction sets** - the 16-slot Group Stage and the
  14-slot main-event bracket - scored on a correct-count curve in Compendium Points.
- **Fantasy** is an **independent scoring track** with its own two periods, its own fantasy-point
  scale and its own percentile-banded reward table. It is not a third prediction set.

The overall Compendium rank is a function of both scores (`DOTA_Score2026_Predictions` and
`DOTA_Score2026_Fantasy`), which is why they must be modelled separately and summed at the end
rather than treated as one activity.

Valve's shipped compendium definition for league 19719 enumerates every out-of-game prediction slot,
so the absence of hero predictions, player-stat predictions, or "most kills at the event" questions
is established by enumeration rather than by failing to find them.

| Item | Slots | Opens (UTC) | Locks (UTC) | Where it is handled |
| --- | --- | --- | --- | --- |
| Predictions - Group Stage | 16 | 2026-07-15T07:00:00Z | 2026-08-13T02:00:00Z | frozen group-stage track |
| Predictions - The International (bracket) | 14 | 2026-08-17T01:00:00Z | 2026-08-20T02:00:00Z | this track, after the group stage |
| Fantasy - period 0 (Group Stage) | 5 fixed choices + unresolved emblem slots | open now | 2026-08-13T02:00:00Z (to confirm) | this track |
| Fantasy - period 1 (The International) | same | 2026-08-13T02:00:00Z (when period 0 begins) | unresolved | this track |
| In-game predictions | 0 | - | - | disabled for TI2026 |

## 2. What is blocking, and exactly what is needed

The Fantasy **question structure** is established, and as of the 2026-08-10 reconciliation the **base
scoring coefficients are populated** from an operator reading of the in-client scoring panel. What is
still missing is the *semantics* around those numbers and the *current state* of the banners.

Evidence grades used throughout (`fantasy_rules.evidence_grades`):

| Grade | Meaning |
| --- | --- |
| tier-1 confirmed | from a Valve-shipped file or an official Valve publication |
| user-screenshot corroborated | read by the operator from an in-client panel in a user-supplied image; consistent with the Tier-1 templates, but a guide article does not inherit Tier-1 by transitivity |
| partial | structure established, at least one semantic or numeric component is not |
| unresolved | not established by any source available |

Every unknown carries a second, independent axis. `fact_status` is what the evidence supports;
`decision_status` is what the unknown does to the answer. They are not the same question, and
conflating them is what kept this track blocked longer than the evidence justified:

| decision_status | Meaning |
| --- | --- |
| BLOCKING | switching the unknown changes what should be chosen |
| ROBUST | measured across its candidate readings and the choice does not move |
| SCALE_ONLY | it multiplies every score by one constant, so nothing can see it |
| IRRELEVANT | it does not enter the decision at all |

A rule graded ROBUST or SCALE_ONLY is still an unresolved rule. `sensitivity.py` measures the
decision axis on real data; nothing there promotes a fact.

The 18 base coefficients, the Deaths credit and the Teamfight Participation maximum sit at
**user-screenshot corroborated**, carried as `points_status: PARTIAL`. They are promotable to
CONFIRMED only by a direct read of the live client, and `ti_predict/fantasy/questions.py` enforces
that: a coefficient must name its `points_source_type`, and only `client_ui` may be CONFIRMED.

Blockers are split by whether they are **generic** (identical for every entrant, so public research
is the right tool) or **account-specific** (a function of this account's random rolls, so no amount
of research reaches them). The split is recorded in `fantasy/generic_evidence.json`.

The 2026-08-10 deep-research round closed most of the generic set from Valve's own protobuf and
Source 2 schema, the shipped package listing, and independent public tooling. What survives is in
`fantasy_rules.json` under `blocking_unknowns`, and `closed_this_round` records what was withdrawn
and at what grade.

**Why the rest cannot be closed publicly.** The remaining generic numbers live in
`FantasyCraftSetupData_t`, and the shipped package listing contains no fantasy crafting data
resource - only textures match. Those values are compiled into the client or delivered by the game
coordinator, so further public research does not reach them. That is a negative result, and it is
the useful kind: it bounds the search rather than inviting more of it.

Until the P0 group is closed, `readiness()` reports every Fantasy question as not candidate-ready
and no Fantasy team, banner or coach recommendation may be produced. That is the intended behaviour,
not a defect.

### What Valve's own definitions settle

Read-only: only definitions were consulted. No GC request was issued, and no state-mutating message
(`PerformOperation`, `RerollOptions`, `SelectPlayer`, `SelectTeam`, `GenerateTablets`,
`UpgradeTablets`) was sent or will be.

| Finding | Source | Consequence |
| --- | --- | --- |
| `Fantasy_Scoring` values 0-17 are exactly the helpstat ordering | `dota_shared_enums.proto` | the stat-to-index mapping is Tier-1, independently of where the coefficients came from |
| a gem is `(type, slot, shape, quality, stat)` | `dota_gcmessages_client_fantasy.proto` | emblem **order** is real state, so adjacency traits are a genuine ordering decision |
| a tablet carries `tablet_level` and `best_series` | same | Valve's own model names the best-series selection this project inferred from help text |
| gem slots carry `m_nRequiredTabletLevel`; a period carries `m_nTabletLevel` | `FantasyCraftingGemSlotData_t`, `FantasyPeriodData_t` | the three-slot banner is the **period-0** layout; period 1 raises the level and unlocks more slots |
| `EFantasyShapeBehavior` has exactly six behaviours | schema dump | the trait taxonomy is closed; there is no hidden seventh |
| a title is a thresholded predicate over a stat vector at player/team/game scope, paying one integer bonus | `FantasyCraftingTitleData_t`, `FantasyCraftingTrackedStat_t` | every suffix condition in the list is explained by scope plus threshold direction |
| `FantasyCraftOperation_t` has no cost field | schema dump | corroborates the flat one-token cost: the budget problem is about the *number* of operations, not their mix |
| operations come from weighted buckets | `FantasyCraftOperationBucket_t` | the roll board is a random draw, so crafting is sequential decision-making under randomness |
| `FantasyPlayerData_t.m_bIsValid` | schema dump | Valve carries a per-player league-validity flag; an ineligible player leaves the pool at source |

### The 18 base coefficients

Grade: user-screenshot corroborated. Each value fills exactly one `{f:helpstat_N}` placeholder in the
shipped localization, with none left unfilled and none left over, and each value's *form* matches its
template (a per-second rate for Stuns, a cap for Teamfight Participation, a credit-and-debit for
Deaths, a bare multiplier for GPM). The Deaths credit is exactly ten times the per-death debit.

| helpstat | colour | stat | client label (zh) | coefficient | OpenDota field |
| --- | --- | --- | --- | --- | --- |
| 0 | red | Kills | 击杀 | +107.00 per kill | `kills` |
| 1 | red | Deaths | 死亡 | 1950.00 start, -195.00 per death | `deaths` |
| 2 | red | Creep Score | 正反补 | +3.00 per last hit or deny | `last_hits + denies` |
| 3 | red | GPM | GPM | GPM x 2.00 | `gold_per_min` |
| 4 | red | Tower Kills | 摧毁防御塔 | +352.00 | `towers_killed` |
| 13 | red | Madstone Collected | 狂石收集数量 | +13.00 | `neutral_tokens_log` |
| 7 | blue | Wards Placed | 放置守卫 | +117.00 | `obs_placed` |
| 8 | blue | Camps Stacked | 堆叠野怪 | +234.00 | `camps_stacked` |
| 9 | blue | Runes Grabbed | 拾取神符 | +141.00 | `rune_pickups` |
| 12 | blue | Smokes Used | 开雾次数 | +293.00 | `item_uses.smoke_of_deceit` |
| 14 | blue | Watchers Taken | 占领观察者 | +147.00 | none - blocked |
| 15 | blue | Lotuses Grabbed | 采集莲花 | +176.00 | none - blocked |
| 5 | green | Roshan Kills | 击杀肉山 | +1172.00 | `roshans_killed` |
| 6 | green | Teamfight Participation | 参与团战 | maximum 2124.00 | `teamfight_participation` |
| 10 | green | First Blood | 第一滴血 | +1934.00 | `firstblood_claimed` |
| 11 | green | Stuns | 眩晕时间 | +10.00 per second | `stuns` |
| 16 | green | Tormentor Kills | 消灭痛苦魔方 | +879.00 | objective event, attribution unverified |
| 17 | green | Courier Kills | 杀害信使 | +703.00 | `courier_kills` |

Reading the scale, not the strategy: the coefficients span three orders of magnitude, from 3.00 per
creep to 2124.00 for a single capped stat. Green stats are large and rare, blue stats are mid-sized
and role-structural, and red stats are mostly small and accumulative except for the Deaths credit and
Tower Kills. That shape is why the emblem choice cannot be made by picking whichever stat a player
happens to lead: a banner slot spent on Creep Score and one spent on First Blood are not comparable
without the underlying rate distributions, which is the work of PHASE 3.

## 3. Modelling notes that follow from the confirmed rules

These are consequences of the ruleset, recorded now so the modelling phase does not re-derive them.

- **The period score is a maximum, not a sum.** A role's period score is the score of its *best
  series*, not the total over the period, so expected maps played times expected points per map is
  the wrong estimator. The model keeps four levels distinct: the per-game score distribution, the
  top-two-within-series aggregation, the best-series-within-period maximum, and the number of
  eligible series as the count of extreme-value draws. More series helps as extra draws from a
  distribution whose maximum is taken, not as accumulation.
- **Summing versus averaging the top two maps is a scale factor, not a decision.** For any series
  contributing at least two maps - the TI best-of-three condition - `mean = sum / 2` identically, and
  a positive constant cannot reorder anything. Measured: ratio 0.499994 to 0.500006 across every
  organisation and role, with byte-identical rank order. The only mechanism that breaks it is a
  series shorter than two maps, which cannot occur at TI but makes up a quarter of the training
  window; the baseline therefore excludes best-of-ones by default. A nonlinearity audit confirms
  nothing downstream restores a decision effect: coach titles, quality, traits, the Deaths credit
  and the Teamfight cap all act per player-game *before* the aggregation, the best-series step is a
  maximum, the role scores are summed, and the reward tiers are percentiles over all entrants, which
  a common factor leaves unchanged.
- **A banner scores from one series, so the stat set and the series are chosen together.** Taking
  each emblem's best series separately and adding them is a sum of maxima, which is unreachable.
  Every legal stat set is enumerated and scored as a unit instead (75 for core, 120 for mid, 30 for
  support once the unobtainable stats are removed).
- **Schedule exposure is nearly flat, so it barely moves the ranking.** Expected series runs from
  5.23 to 5.64 across the field, because both the strongest and the weakest teams finish in four or
  five series while the middle of the table reaches six. Going from four draws to six is worth
  +2.4% to +6.7% of period score, but the *differential* between teams moves the ranking by at most
  one position. Exposure is read from the frozen track's published bucket probabilities and never
  recomputed here.
- **The unit of choice is a team, not a player.** Core and support banners score the *average* of
  the team's two players in that role. Averaging halves the idiosyncratic variance of a single
  player and makes team style, not individual reputation, the dominant signal.
- **Only the stats on the banner score at all.** A player who is excellent at something the banner
  does not carry contributes nothing from it. Player quality and banner composition are not
  separable, so they have to be optimised jointly.
- **The banner is partly stochastic.** Emblems are rerolled with a limited token budget, not chosen.
  The decision is a sequential one under randomness with a budget constraint, and its value depends
  on the token budget, which is currently unknown.
- **Adjacency is part of the decision.** Benevolent and Vampiric act on neighbouring emblems, so the
  ordering of emblems on a banner matters, not just the set. Valve's gem message carries an explicit
  `slot`, which is what makes that ordering well defined rather than cosmetic.
- **The banner grows between periods, so period 0 is not a rehearsal for period 1.** Gem slots are
  gated by `m_nRequiredTabletLevel` and the tablet level is set per period. A three-emblem banner in
  the group stage becomes a larger one at the main event, on the *same* carried-over roster. Tokens
  do not roll over, so the period-0 budget must be spent against the period-0 layout and cannot be
  saved for the bigger banner.
- **Two-thirds of the coach title pool is unpriced.** Eight prefix bonuses are known and they range
  from 6 to 11 percent, so the choice is worth real points and is not uniform. The other eleven
  prefixes and all twenty suffixes have no published value.
- **Rewards are percentile-banded.** Nine tiers, from 100th to 10th percentile. Clearing a threshold
  is what pays, which is not the same objective as maximising expected score. Which to optimise
  cannot be settled until the tier values are known.
- **Low-frequency stats must be shrunk.** First blood, Roshan, Tormentor, courier and smoke are rare
  or zero-inflated. A raw player mean over a handful of maps is not an estimate of anything; these
  need shrinkage towards a role-level and team-level prior with the sample size carried through.
- **Two stats are not obtainable from OpenDota.** Watchers Taken and Lotuses Grabbed have no player
  field and no objective event on a parsed match. Tormentor Kills exists as an objective event but
  per-player attribution is unverified. Everything else needs a *parsed* match, so parse coverage is
  a hard gate on the data layer.

## 4. Phase plan

1. **PHASE 1 - inventory: BLOCKED, much reduced.** The 30 prediction slots and the two-period
   Fantasy structure are exhaustively enumerated. After the 2026-08-10 deep-research round the
   generic set is nearly closed; what remains is three generic scoring semantics that live in
   client-side data, plus the account's own banner state.
2. **PHASE 2 - data feasibility: DONE for the public window.** All 18 stats are mapped to columns
   and probed: 15 retrievable, 2 unobtainable (Watchers, Lotuses), 1 partial (Tormentor, no
   per-player attribution). Everything except six base columns requires a *parsed* match, so
   `parsed` is carried on every row and the baseline filters on it.
3. **PHASE 3 - baselines: STARTED.** `fetch_player_stats` pulls per-player per-map rows for the 16
   TI rosters over the five-event window already present in the frozen track's universe;
   `baseline.py` applies the real four-level aggregation and reports under both unresolved
   hypotheses. Output is explicitly PRELIMINARY.
4. **PHASE 4 - modelling: NOT STARTED.** Planned: hierarchical shrinkage per stat class, joined to
   the frozen Swiss simulator only for series exposure, then a maximum-over-series aggregation.
5. **PHASE 5 - validation: NOT STARTED.** Planned: as-of validation on prior LANs using strictly
   pre-event features.
6. **PHASE 6 - candidate: BLOCKED.** It may begin only when `readiness()` reports the Fantasy
   questions candidate-ready. Current fill instruction is `NO RELIABLE EDGE / INSUFFICIENT EVIDENCE`.
7. **PHASE 7 - freeze: NOT STARTED.** The operational checkpoints below are provisional until the
   two Fantasy countdowns are captured.

## 5. Lock-day procedure

**Fantasy period 0 - provisional deadline 2026-08-13T02:00:00Z.** First capture the in-client
countdown and all blocking runtime values. Only after the gate closes: refresh the data, confirm the
roster of record for the three chosen teams against `roster_events.csv`, generate the three team
choices and two coach titles, allocate the known token budget, and screenshot the final banner state.

**Bracket - between 2026-08-17T01:00:00Z and 2026-08-20T02:00:00Z.** The candidate set only exists
once the group stage seeds the bracket. Re-run the frozen team-strength model as an input, map the
14 `league_node_id` values to the actual matchups, and fill top-down. Submit at least an hour early.

**Fantasy period 1 - lock unresolved.** Confirm the countdown in the client when period 0 ends.

Nothing in this track re-runs, re-tunes, or re-reports the frozen group-stage slate.

## 6. Commands

```
python -m ti_predict.fantasy.questions          # validate the inventory, print the readiness gate
python -m ti_predict.fantasy.fetch_player_stats # per-player per-map rows; resumable, fail-closed
python -m ti_predict.fantasy.baseline            # PRELIMINARY envelope ranking, per role
python -m ti_predict.fantasy.sensitivity        # fact_status / decision_status, measured
python -m ti_predict.fantasy.exposure           # schedule exposure from the frozen track
python -m pytest tests/test_fantasy_questions.py tests/test_fantasy_baseline.py \
                tests/test_fantasy_exposure.py -q
```

`sensitivity` switches one unresolved rule at a time and reports how far the ranking and the stat
choices move. Change one factor per comparison: an earlier round of this project compared a setting
that changed the aggregation *and* the Deaths floor together and attributed the result to the
aggregation alone.

When the default system temp folder is not writable, use a workspace-local temporary base:

```
python -m pytest tests/test_fantasy_questions.py -q -p no:cacheprovider --basetemp=.pytest-tmp
```

## 7. What still has to come from the live client

The generic ruleset has been pushed as far as public material goes. Requests for generic panels are
**withdrawn**; see `prediction_questions.screenshot_reconciliation.withdrawn_requests`. Asking again
for something the shipped schema already answers wastes the operator's time and is the failure this
section exists to prevent.

**Account-specific, and unreachable by any other means.** `CMsgDotaFantasyCraftingUserData` and
`CMsgDotaFantasyCraftingTabletPeriodData` are per-account messages; their contents exist nowhere
public by construction.

1. **The three War Banners in one capture** - Core, Mid and Support. For each emblem: colour, stat,
   quality tier, trait, and its left-to-right position, because adjacency traits make order part of
   the state. The same capture should show the roll-token balance and the lock countdown.
2. **One capture of the roll board** - the three operations currently offered.

**Generic, still open, and worth a capture only because it is cheap while the operator is already
in the panel.** Not a blocker for PHASE 3: the Scoring pane's exact wording around "the top two
scoring games", and the Rewards table's nine percentile point values.

### Can this be read automatically instead?

Not safely. The data arrives in the GC response to `k_EMsgClientToGCFantasyCraftingGetData`, which
requires an authenticated Steam session speaking the GC protocol. Doing that means running a
third-party client against the account during a live event, and the same session carries the
state-mutating operations. The client keeps a `CMsgDotaFantasyCraftingDataCache`, but it is not an
exposed file with a documented location, and reading it would still mean parsing an undocumented
private cache. A screenshot of two panels costs the operator a minute and carries none of that risk,
so it is the right trade here - not a fallback.
