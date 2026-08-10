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

The 18 base coefficients, the Deaths credit and the Teamfight Participation maximum sit at
**user-screenshot corroborated**, carried as `points_status: PARTIAL`. They are promotable to
CONFIRMED only by a direct read of the live client, and `ti_predict/fantasy/questions.py` enforces
that: a coefficient must name its `points_source_type`, and only `client_ui` may be CONFIRMED.

Twelve facts still block optimisation, listed in `fantasy_rules.json` under `blocking_unknowns` and
prioritised P0/P1. Until the P0 group is closed, `readiness()` reports every Fantasy question as not
candidate-ready and no Fantasy team, banner or coach recommendation may be produced. That is the
intended behaviour, not a defect.

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

- **The period score is a maximum, not a sum - held directionally, not frozen.** A role's period
  score is the score of its *best series*, not the total over the period, so expected maps played
  times expected points per map is the wrong estimator. This follows from the shipped wording and is
  not in doubt in direction; the exact estimator stays open until `top_two_aggregation` and
  `best_series_eligibility` are closed. The final model must keep four levels distinct: the per-game
  score distribution, the top-two-within-series aggregation, the best-series-within-period maximum,
  and the number of eligible series as the count of extreme-value draws. More series helps as extra
  draws from a distribution whose maximum is taken, not as accumulation.
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
  ordering of emblems on a banner matters, not just the set.
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

1. **PHASE 1 - inventory: BLOCKED, reduced.** The 30 prediction slots and the two-period Fantasy
   structure are exhaustively enumerated, and as of 2026-08-10 the 18 base coefficients are
   populated at user-screenshot grade. What still requires the live client: the four P0 scoring
   semantics, the current banner state, the coach title percentages, the selection legality, and the
   period-0 lock countdown.
2. **PHASE 2 - data feasibility: IN PROGRESS.** The OpenDota field mapping for all 18 stats is
   recorded and probed: 15 retrievable, 2 blocked (Watchers, Lotuses), 1 partial (Tormentor). Still
   to do: parse-coverage rate over TI-tier matches and whether STRATZ supplies the two blocked
   stats. Permitted to continue while PHASE 1 is blocked, since none of it depends on the
   coefficients.
3. **PHASE 3 - baselines: NOT STARTED.** Planned: role-level and team-level per-map distributions
   with event-blocked bootstrap intervals.
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
python -m ti_predict.fantasy.questions      # validate the inventory and print the readiness gate
python -m pytest tests/test_fantasy_questions.py -q
```

When the default system temp folder is not writable, use a workspace-local temporary base:

```
python -m pytest tests/test_fantasy_questions.py -q -p no:cacheprovider --basetemp=.pytest-tmp
```

## 7. Exact live-client captures still required

1. **Compendium -> Fantasy -> How to Play -> Scoring / Emblem Stats.** Capture the entire rules
   pane from its heading through all 18 stat rows. It must show every numeric coefficient, the
   Deaths starting credit, and the wording immediately around “top two scoring games.”
2. **Compendium -> Fantasy -> Core, Mid, Support War Banners.** One full-resolution capture per
   banner. Include every emblem slot in left-to-right order, colour, stat, quality, trait, the roll
   token count, all three current roll options, and the lock countdown.
3. **Open “Choose Team” on each of the three War Banners.** Capture the complete dropdown including
   disabled entries or restriction text. The images must establish the candidate universe and
   whether the same team may be selected for more than one role.
4. **Compendium -> Fantasy -> Coaching Titles.** Capture the complete prefix and suffix choices,
   each displayed percentage, and the same lock countdown.
5. **Compendium -> Rewards -> Fantasy.** Capture all nine percentile rows and their point values.
6. **After Fantasy period 1 unlocks.** Capture its period label, countdown, candidate dropdown and
   any newly granted roll tokens or upgrade choices.

The previously referenced long screenshot is not available as an image payload or repository file
in this run. Its prose description was used only to discover modules; no OCR-derived number has been
accepted as fact.
