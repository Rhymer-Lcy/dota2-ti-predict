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
| Fantasy - period 0 (Group Stage) | 5 fixed choices + unresolved emblem slots | open now | 2026-08-13T02:00:00Z (to confirm) | this track |
| Fantasy - period 1 (The International) | same | 2026-08-13T02:00:00Z (when period 0 begins) | unresolved | this track |
| In-game predictions | 0 | - | - | disabled for TI2026 |

## 2. What is blocking, and exactly what is needed

The Fantasy **question structure** is established. Fantasy **rule closure** is not: the client fills
key values in at runtime from values that appear in no shipped file. Ten groups of facts block
optimisation and are listed in `fantasy_rules.json` under `blocking_unknowns`. Nothing may be
back-filled from a previous year's scoring table; `ti_predict/fantasy/questions.py` refuses a
ruleset that tries.

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

1. **PHASE 1 - inventory: BLOCKED.** The 30 prediction slots and the two-period Fantasy structure
   are exhaustively enumerated, but the runtime Fantasy numbers, configurable emblem slot count,
   candidate dropdown restrictions and lock countdowns still require the live client.
2. **PHASE 2 - data feasibility: NOT STARTED.** The OpenDota field mapping is a preliminary schema,
   not a coverage result. Do not pull or bless a player-stat dataset until PHASE 1 closes.
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
