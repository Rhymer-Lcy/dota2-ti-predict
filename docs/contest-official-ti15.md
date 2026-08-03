# TI15 official predictions activity - verified rules

Verified 2026-08-03 from the official in-client activity (transcribed by the client owner) and
cross-checked against public event coverage. This supersedes the earlier assumption that the contest
was a third-party / streamer ("Echodraft") activity. Git history and committed docs are the source
of truth; this doc records the client inputs the frozen checkpoint was waiting for.

## 1. Nature of the activity
It is the official Valve / Dota 2 client International 2026 (TI15) activity. Points, Dota Plus, chat
wheel and shield discounts settle in-client. Three sub-games:
1. Match predictions (group-stage record buckets + main-event series winners).
2. Fantasy Challenge (pick players + emblems; percentile-scored).
3. Event rewards (activity points -> ranked/percentile rewards).

## 2. Group-stage prediction - structure (16 fill-in slots)
The prediction is a FULL classification of all 16 teams into record buckets, not a pick of a few
extremes. Six categories, 16 individual slots, one team per slot:

| category            | slots | meaning                                                        |
|---------------------|------:|----------------------------------------------------------------|
| 4-0                 |     1 | sole undefeated; advances directly                             |
| 4-1                 |     2 | advance directly                                               |
| decider winner      |     5 | a 3-2 team that WINS the extra elimination-round match         |
| decider loser       |     5 | a 2-3 team that LOSES the extra elimination-round match        |
| 1-4                 |     2 | eliminated                                                     |
| 0-4                 |     1 | sole winless; eliminated                                       |
| total               |    16 |                                                                |

"decider winner/loser" (Chinese client: taotaisai shengzhe / baizhe) are the 5 winners and 5 losers
of the extra elimination round played among the five 3-2 teams and five 2-3 teams. They are NOT a
single "special winner/loser". Advancing 8 = one 4-0 + two 4-1 + five decider winners. The middle 10
slots (both decider buckets) are the hardest; the extremes (4-0, 0-4, 4-1, 1-4) are where model
confidence is highest.

## 3. Group-stage prediction - scoring
Points depend ONLY on how many slots are correct. No wrong-answer penalty, no underdog weighting, no
odds/pick-share weighting. The curve is convex (rising marginal points), except a dip at 16.

| correct | points |     | correct | points |
|--------:|-------:|-----|--------:|-------:|
|       1 |     30 |     |       9 |  3,360 |
|       2 |     60 |     |      10 |  4,320 |
|       3 |    120 |     |      11 |  5,400 |
|       4 |    360 |     |      12 |  6,600 |
|       5 |    720 |     |      13 |  7,920 |
|       6 |  1,200 |     |      14 |  9,360 |
|       7 |  1,800 |     |      15 | 10,920 |
|       8 |  2,520 |     |      16 | 12,000 |

Strategy implication: with no underdog bonus and no penalty, the per-slot expected value is set only
by hit probability, so the base-optimal group slate maximizes the EXPECTED number correct - a
capacity-constrained assignment of 16 teams to the 16 slots (objective = sum of P(team in bucket)),
fed by the Swiss simulator's bucket probabilities. Deviating toward higher-variance / contrarian
picks is justified ONLY because (a) the final reward is a percentile/rank competition and (b) the
points curve is convex, so reaching the top tail rewards variance - but only on slots where our
model materially and correctly disagrees with the likely-chalk crowd.

## 4. Crowd percentages
The client selection UI shows only team logos. No pick-share / heat / community-vote percentage is
displayed. There is no crowd% input available for this contest.

## 5. Timing (client showed relative countdowns on 2026-08-03)
- Group-stage prediction locks ~9 days out -> approximately 2026-08-13. Public coverage puts the lock
  at Thu 2026-08-13 15:00 UTC = 23:00 Beijing (group stage begins). Confirm the exact in-client
  countdown before submitting.
- Main-event prediction opens ~13 days out -> approximately 2026-08-16.
- Winner rewards finalized 2026-08-28.

## 6. Rewards
Participation rewards (claimable): Aegis chat emote, TI wallpaper, TI chat wheel (four voice lines).
Ranked winner rewards (finalized 2026-08-28), tiers: top 100, top 1,500, 95th percentile, 90th
percentile, 85th percentile - larger Dota Plus / map token / shield discount / immortal recolor at
higher tiers. Plus 300 Dota Plus shards per 1,000 activity points. "Top 5% gets everything" maps to
the 95th-percentile tier; true "gets everything" is top 100. Total ranking = group predictions +
main-event predictions + Fantasy, so group predictions alone cannot reach the top tiers. It is not
documented whether tiers stack.

## 7. Main-event prediction (opens ~2026-08-16)
Pick the winner of each of 14 series along the bracket to the champion. Scoring by number correct
(1 -> 120 ... 14 -> 12,000), same convex shape, no penalty shown. Requires the posted main-event
bracket + an official-rules-verified bracket simulator (see the simulator gate).

## 8. Fantasy Challenge (separate sub-game)
Five-slot lineup: a core duo + one mid + a support duo (from up to three teams), scored on real
player stats, with emblem/quality/trait multipliers and coach titles, then converted to points by
percentile vs all submitted lineups each period. This is a different optimization from our team
rating model and is OUT OF SCOPE unless explicitly chosen; noted here only because it contributes to
the final activity-points ranking.

## 9. Group-stage FORMAT (drives the simulator)
- Modified 5-round Swiss, 16 teams, all series Bo3.
- Two initial pods; rounds 1-3 pair only within a team's initial pod; round 4 pairs across pods;
  round 5 for advancement/elimination-deciding matches pairs to MAXIMIZE rank gap (a deliberate
  inversion of the usual "closest ranks" rule).
- Pairing principles: same record first, avoid rematches, minimize rank gap (except R5 deciders).
- After 5 rounds: top 3 advance directly; the five 3-2 and five 2-3 teams play an extra
  elimination round; ranks 14-16 are eliminated.
- Extra elimination-round seeding: the highest-ranked 3-2 team picks its 2-3 opponent, then the next
  3-2 team picks from the remaining 2-3 teams, etc. The 5 winners advance (top 8 to main event); the
  5 losers are eliminated.
- Main-event seeding is by final Swiss rank.
- Swiss ranking tiebreakers, in order: (1) series wins; (2) series losses; (3) opponents' series
  wins (strength of schedule); (4) match (map) win rate; (5) opponents' average win rate; (6) average
  game duration, shorter is better; (7) coin flip.

The simulator (`ti_predict/simulate.py`) must implement the two-pod pairing, R5 gap-maximizing
deciders, the pick-order extra elimination round, and these tiebreakers, and pass rule-level
verification BEFORE any formal output. It is currently only mechanics-validated.

## 10. Field - confirmed 16 (matches inputs/teams.csv)
Direct invites (7): Aurora Gaming, BetBoom Team (BoomBoys), Team Falcons, Team Liquid, Tundra Esports
(plays as 1w Team), Xtreme Gaming, Team Yandex.
Qualifiers (9): PARIVISION (Team Vision), Team Spirit, HULIGANI (L1ga), Nigma Galaxy [EU x4];
Vici Gaming, Team Resilience [CN x2]; OG [SEA]; LGD Gaming [SA]; GamerLegion [NA].
Qualifiers closed ~late June 2026; the field is locked. MOUZ is NOT in the TI15 field (it appeared in
the unrelated Astana "Future Games" event). No B0 reopening is required.

## 11. Corrections to earlier notes
- Prize pool is $1.6M (the earlier $1M was the Astana Future Games event).
- Group-prediction lock is ~Aug 13 15:00 UTC = 23:00 Beijing (earlier "10:00 CST" read CST as China;
  the source's CST is US Central).
- The prediction is a 16-slot full assignment, not a 6-extreme pick; "decider winner/loser" are 5+5
  teams, not one "special winner/loser".

## 12. Open items to confirm before emitting any TI15 numbers
1. Exact in-client lock timestamp (day/hour/minute).
2. Rule-level verification of the Swiss pairing / R5 deciders / extra elimination round / tiebreakers
   against the official ruleset, then implemented in the simulator (gate).
3. Whether reward tiers stack (affects only how aggressively to chase a tier, not the slate itself).

## Sources
- In-client activity, transcribed by the client owner, 2026-08-03 (primary).
- The International 2026, team field and format: blast.tv, hotspawn.com (2026-06-28), dltv.org.
- Predictions lock time: strafe.com predictions-and-rewards writeup.
