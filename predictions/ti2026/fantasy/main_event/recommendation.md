# TI15 Fantasy - period 1 (Main Event) recommendation

Generated 2026-08-17T12:30:33+00:00 from commit `8c6b715` (dirty at start: False). Information cutoff 2026-08-17T00:00:00Z; Main Event results used: False.

JSON is the fact source. Numbers are not duplicated here beyond what a decision needs: `team_rankings.json`, `banner_value_tables.json`, `coach_value_tables.json`, `reroll_offer_evaluation.json` and `interactive_policy.json` are authoritative.

## Deadline

The roster is snapshotted when Main Event matches begin. Recorded lock **2026-08-20T02:00:00Z**; the in-client countdown read *2 days until lineup lock* on 2026-08-17. Team and coach changes are free, so there is no reason to submit late, and no reason to trust post-start editability.

## Client actions

```
OPERATOR  (40 roll tokens)
  CORE     CHANGE -> PARIVISION   (current team is eliminated)
  MID      KEEP   -> Team Falcons
  SUPPORT  CHANGE -> Team Falcons   (current team is eliminated)
  COACH    CHANGE -> Otherworldly + the Clutch
  REROLL   see the offer table below; nothing is recommended blind

TARGET  (36 roll tokens)
  CORE     CHANGE -> PARIVISION   (current team is eliminated)
  MID      CHANGE -> Team Falcons
  SUPPORT  CHANGE -> Team Yandex   (current team is eliminated)
  COACH    CHANGE -> Crimson + the Clutch
  REROLL   see the offer table below; nothing is recommended blind

NEXT REVIEW  before 2026-08-20T02:00:00Z (roster snapshot), and after every reroll
```

## Team selection

### operator account (40 roll tokens)

| role | current | action | recommended | label | E[score] | 90% interval | P(best) | runner-up gap | survives shrinkage sweep | unscored |
|---|---|---|---|---|---:|---|---:|---:|---|---:|
| core | Xtreme Gaming | **CHANGE (eliminated)** | **PARIVISION** | ROBUST | 19,921 | [19,280, 20,312] | 0.90 | 3.77% | yes | 0% |
| mid | Team Falcons | keep | **Team Falcons** | BANNER-DEPENDENT | 14,542 | [13,617, 15,226] | 0.29 | 0.11% | NO | 14% |
| support | Xtreme Gaming | **CHANGE (eliminated)** | **Team Falcons** | BANNER-DEPENDENT | 13,910 | [13,060, 14,559] | 0.35 | 1.20% | NO | 17% |

- `mid` is BANNER-DEPENDENT: 19 of 71 single-emblem changes move the best team. Examples: slot1.stat->tower_kills -> PARIVISION; slot2.quality->I -> PARIVISION; slot2.stat->wards_placed -> PARIVISION; slot2.stat->camps_stacked -> PARIVISION; slot2.stat->smokes_used -> PARIVISION; slot2.stat->watchers_taken -> PARIVISION
- `support` is BANNER-DEPENDENT: 6 of 67 single-emblem changes move the best team. Examples: slot2.stat->roshan_kills -> PARIVISION; slot2.stat->first_blood -> PARIVISION; slot2.stat->stuns -> Team Spirit; slot2.stat->courier_kills -> Team Yandex; slot4.quality->V -> PARIVISION; slot4.stat->first_blood -> PARIVISION

### target account (36 roll tokens)

| role | current | action | recommended | label | E[score] | 90% interval | P(best) | runner-up gap | survives shrinkage sweep | unscored |
|---|---|---|---|---|---:|---|---:|---:|---|---:|
| core | Xtreme Gaming | **CHANGE (eliminated)** | **PARIVISION** | ROBUST | 23,037 | [20,780, 24,758] | 0.69 | 5.86% | yes | 21% |
| mid | Team Yandex | **change** | **Team Falcons** | BANNER-DEPENDENT | 12,414 | [11,339, 13,296] | 0.48 | 3.23% | yes | 0% |
| support | Xtreme Gaming | **CHANGE (eliminated)** | **Team Yandex** | BANNER-DEPENDENT | 15,026 | [14,376, 15,510] | 0.37 | 0.77% | yes | 12% |

- `mid` is BANNER-DEPENDENT: 5 of 71 single-emblem changes move the best team. Examples: slot1.stat->tower_kills -> Team Yandex; slot3.stat->roshan_kills -> BetBoom Team; slot4.stat->tower_kills -> Team Yandex; slot5.stat->roshan_kills -> BetBoom Team; slot5.stat->courier_kills -> Nigma Galaxy
- `support` is BANNER-DEPENDENT: 12 of 67 single-emblem changes move the best team. Examples: slot1.quality->I -> PARIVISION; slot1.stat->smokes_used -> PARIVISION; slot1.stat->lotuses_grabbed -> Tundra Esports; slot2.stat->roshan_kills -> Team Falcons; slot2.stat->stuns -> Team Falcons; slot2.stat->tormentor_kills -> Team Falcons

## Coach

One prefix and one suffix apply to all three roles, so the pair is scored on the SUM over roles and chosen jointly with the teams. Both are free and reversible, so there is no switching cost to trade against.

| account | recommended | incumbent | gain over incumbent | same winner under multiplicative stacking |
|---|---|---|---:|---|
| operator | **Otherworldly + the Clutch** | Elemental + the Tormented | 2.39% | yes |
| target | **Crimson + the Clutch** | Elemental + the Tormented | 3.02% | yes |

Prefix evidence is not uniform: Crimson, Cerulean and Emerald score off exact hero-colour flags; Elemental and Otherworldly score off a strict subset of their condition, so their numbers are lower bounds; Royal, Golden and Heroic have no hero-category table and cannot be scored at all.

## Roll tokens

| account | tokens | headroom on the three banners | implied shadow value per token |
|---|---:|---:|---:|
| operator | 40 | 56,460 | 1,412 |
| target | 36 | 55,126 | 1,531 |

Tokens do not roll over and period 1 is the last period, so an unspent token is worth exactly zero after the lock. See `reroll_offer_evaluation.json` for the current three offers on each account, enumerated as outcome sets rather than expectations: Valve publishes no reroll weights, so an improving fraction here is combinatorial and is not a probability.

## What the model cannot see

Three stats have no per-player value anywhere in the public data. Their weight is set to zero and reported, never scored as if the players produced none. Because adding a constant per player-game shifts a period score by exactly twice that constant, the flip condition is closed form.

| account | role | unscored stat | multiplier | points per +1 per player-game | runner-up needs |
|---|---|---|---:|---:|---|
| operator | mid | madstone | 1.10 | 29 | PARIVISION needs +0.56/game |
| operator | support | lotuses_grabbed | 1.50 | 528 | PARIVISION needs +0.32/game |
| target | core | madstone | 2.10 | 55 | Team Falcons needs +24.72/game |
| target | support | watchers_taken | 1.10 | 323 | Team Falcons needs +0.36/game |

The client's Runes wording is also unresolved: OpenDota's `rune_pickups` excludes wisdom runes, which are 20.3% of all runes taken at TI15, while its `runes` histogram includes them. Both definitions were run end to end; see `interactive_policy.json -> rune_definition_sensitivity` for whether the team choice moves.

## The three offers currently on each board

Evaluated on the RECOMMENDED team, not the eliminated one currently equipped. No expectation is quoted: Valve publishes no reroll weights, so what follows is the outcome set and its combinatorial spread.

| account | banner | offer | semantics | reading | outcomes | worst | median | best | improving |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| operator | mid | OP1 quality_multi | TARGET_SELECTION_SEMANTICS_UNKNOWN | one_tier_step_assumed | 30 | -1,059 | +1,038 | +2,759 | 77% |
| operator | mid | OP2 stat | TARGET_RESOLVED | resolved | 4 | +644 | +1,292 | +4,818 | 100% |
| operator | mid | OP3 quality | TARGET_SELECTION_SEMANTICS_UNKNOWN | all_of_colour | 25 | -2,639 | -1,184 | +1,513 | 20% |
| operator | mid | OP3 quality | TARGET_SELECTION_SEMANTICS_UNKNOWN | single_unknown_slot | 10 | -2,639 | +0 | +1,513 | 10% |
| target | core | TG1 trait | TARGET_SELECTION_SEMANTICS_UNKNOWN | all_of_colour | 216 | -2,229 | -766 | +2,300 | 28% |
| target | core | TG1 trait | TARGET_SELECTION_SEMANTICS_UNKNOWN | single_unknown_slot | 18 | -1,821 | -17 | +1,603 | 28% |
| target | core | TG2 quality | TARGET_RANDOM_ONE | random_one_of_colour | 15 | -5,674 | +0 | +3,935 | 20% |
| target | core | TG3 stat | TARGET_RESOLVED | resolved | 4 | +45 | +315 | +2,644 | 100% |

## Emblem diagnostic

Full per-emblem numbers are in `banner_value_tables.json`. Summary of the classification of all 30 live emblems:

| account | role | slot | stat | mult | class | share of banner value | best same-colour swap |
|---|---|---:|---|---:|---|---:|---|
| operator | core | 1 | tower_kills | 1.60 | HIGH-PRIORITY REROLL TARGET | 20.7% | creep_score (+10.7%) |
| operator | core | 2 | teamfight_participation | 1.50 | PROTECT | 21.9% | none better |
| operator | core | 3 | deaths | 1.10 | GOOD | 17.2% | creep_score (+4.1%) |
| operator | core | 4 | roshan_kills | 1.30 | GOOD | 11.9% | none better |
| operator | core | 5 | gpm | 1.60 | PROTECT | 26.2% | creep_score (+4.3%) |
| operator | mid | 1 | madstone | 1.10 | VALUE UNCERTAIN DUE TO DATA | n/a | creep_score (+22.1%) |
| operator | mid | 2 | runes_grabbed | 1.50 | PROTECT | 39.6% | none better |
| operator | mid | 3 | tormentor_kills | 1.60 | HIGH-PRIORITY REROLL TARGET | 2.9% | teamfight_participation (+33.1%) |
| operator | mid | 4 | deaths | 2.20 | HIGH-PRIORITY REROLL TARGET | 43.1% | creep_score (+5.5%) |
| operator | mid | 5 | first_blood | 1.30 | HIGH-PRIORITY REROLL TARGET | 6.5% | teamfight_participation (+22.5%) |
| operator | support | 1 | lotuses_grabbed | 1.50 | VALUE UNCERTAIN DUE TO DATA | n/a | camps_stacked (+24.1%) |
| operator | support | 2 | tormentor_kills | 3.00 | HIGH-PRIORITY REROLL TARGET | 18.5% | stuns (+6.6%) |
| operator | support | 3 | wards_placed | 1.20 | PROTECT | 24.2% | none better |
| operator | support | 4 | teamfight_participation | 1.30 | PROTECT | 26.2% | none better |
| operator | support | 5 | smokes_used | 1.60 | PROTECT | 28.1% | none better |
| target | core | 1 | gpm | 1.50 | PROTECT | 21.2% | none better |
| target | core | 2 | roshan_kills | 2.10 | HIGH-PRIORITY REROLL TARGET | 15.3% | teamfight_participation (+12.5%) |
| target | core | 3 | creep_score | 3.40 | PROTECT | 58.5% | none better |
| target | core | 4 | tormentor_kills | 1.00 | HIGH-PRIORITY REROLL TARGET | 1.5% | teamfight_participation (+11.5%) |
| target | core | 5 | madstone | 2.10 | VALUE UNCERTAIN DUE TO DATA | n/a | deaths (+27.2%) |
| target | mid | 1 | deaths | 1.80 | PROTECT | 38.1% | gpm (+4.0%) |
| target | mid | 2 | wards_placed | 1.50 | HIGH-PRIORITY REROLL TARGET | 4.3% | runes_grabbed (+44.2%) |
| target | mid | 3 | stuns | 1.10 | HIGH-PRIORITY REROLL TARGET | 10.5% | teamfight_participation (+19.3%) |
| target | mid | 4 | creep_score | 1.10 | PROTECT | 25.6% | none better |
| target | mid | 5 | first_blood | 1.60 | HIGH-PRIORITY REROLL TARGET | 11.7% | teamfight_participation (+32.1%) |
| target | support | 1 | runes_grabbed | 2.90 | HIGH-PRIORITY REROLL TARGET | 23.6% | camps_stacked (+26.2%) |
| target | support | 2 | first_blood | 1.50 | HIGH-PRIORITY REROLL TARGET | 5.7% | courier_kills (+8.9%) |
| target | support | 3 | watchers_taken | 1.10 | VALUE UNCERTAIN DUE TO DATA | n/a | smokes_used (+16.9%) |
| target | support | 4 | teamfight_participation | 1.80 | PROTECT | 35.8% | none better |
| target | support | 5 | wards_placed | 1.80 | PROTECT | 29.7% | none better |

