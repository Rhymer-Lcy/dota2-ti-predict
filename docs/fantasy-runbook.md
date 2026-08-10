# TI2026 Compendium track: Fantasy and Predictions runbook

Scope: everything the TI2026 client asks the entrant to answer that is **not** the 16-slot group-stage
prediction. The group-stage track is frozen; this document never changes it. The only thing that
crosses between the two is schedule exposure (which teams play how many series), and it crosses one
way: the frozen Swiss simulator is read as an input here and is not re-tuned to serve this track.

Fact source: `data/ti2026/inputs/prediction_questions.json` and
`data/ti2026/inputs/fantasy/fantasy_rules.json`. This document is prose about them; where the two
disagree, the JSON wins. Validate both with `python -m ti_predict.fantasy.questions`.

## 1. What exists

The Compendium has five tabs: Rewards, Fantasy, Predictions, Team Bundles, Talent Bundles. Only two
of them score: **Predictions** and **Fantasy**. Valve's shipped compendium definition for league
19719 enumerates every out-of-game prediction slot, so the absence of hero predictions, player-stat
predictions, or "most kills at the event" questions is established by enumeration rather than by
failing to find them.

| Item | Slots | Opens (UTC) | Locks (UTC) | Where it is handled |
| --- | --- | --- | --- | --- |
| Predictions - Group Stage | 16 | 2026-07-15T07:00:00Z | 2026-08-13T02:00:00Z | frozen group-stage track |
| Predictions - The International (bracket) | 14 | 2026-08-17T01:00:00Z | 2026-08-20T02:00:00Z | this track, after the group stage |
| Fantasy - period 0 (Group Stage) | 3 team choices + 2 coach titles + banner crafting | open now | 2026-08-13T02:00:00Z (to confirm) | this track |
| Fantasy - period 1 (The International) | same | 2026-08-13 (when period 0 begins) | unresolved | this track |
| In-game predictions | 0 | - | - | disabled for TI2026 |

## 2. What is blocking, and exactly what is needed

The Fantasy **structure** is fully established. The Fantasy **numbers** are not: the client fills
them in at runtime from values that appear in no shipped file. Eight of them block optimisation and
are listed in `fantasy_rules.json` under `blocking_unknowns`. Nothing may be back-filled from a
previous year's scoring table; `ti_predict/fantasy/questions.py` refuses a ruleset that tries.

Until they are resolved, `readiness()` reports every Fantasy question as not candidate-ready, and no
submission-grade Fantasy candidate may be produced. That is the intended behaviour, not a defect.

## 3. Modelling notes that follow from the confirmed rules

These are consequences of the ruleset, recorded now so the modelling phase does not re-derive them.

- **The period score is a maximum, not a sum.** A role's period score is the score of its *best
  series*, not the total over the period. Expected maps played times expected points per map is
  therefore the wrong estimator. More series still helps, but as additional draws from a
  distribution whose maximum is taken - an extreme-value problem, not an accumulation problem.
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

1. **PHASE 1 - inventory.** Done. Every question, slot, rule and lock time is in the JSON.
2. **PHASE 2 - data feasibility.** Partly done: the OpenDota field mapping for all 18 stats is
   recorded, with three stats flagged BLOCKED or PARTIAL. Remaining: parse-coverage rate over TI-tier
   matches, and whether STRATZ supplies watchers and lotuses.
3. **PHASE 3 - baselines.** Role-level and team-level per-map stat means with event-blocked
   bootstrap intervals. Cannot be scored into fantasy points until the coefficients are known.
4. **PHASE 4 - modelling.** Hierarchical shrinkage per stat class (rate-like, opportunity-count,
   rare event, team-controlled, role-structural), joined to the frozen Swiss simulator for series
   exposure, then a maximum-over-series aggregation.
5. **PHASE 5 - validation.** As-of validation on prior LANs using strictly pre-event features.
6. **PHASE 6 - candidate.** Only when `readiness()` reports the question candidate-ready.
7. **PHASE 7 - freeze.** Lock-day procedure below.

## 5. Lock-day procedure

**Fantasy period 0 - by 2026-08-13T02:00:00Z.** Confirm the in-client countdown; confirm the roster
of record for the three chosen teams against `roster_events.csv`; set the three team choices and the
two coach titles; spend the period's roll tokens; screenshot the final banner state.

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
