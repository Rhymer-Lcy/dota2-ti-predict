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
| decider winner      |     5 | a team (3-2 OR 2-3) that WINS its extra elimination-round match |
| decider loser       |     5 | a team (3-2 OR 2-3) that LOSES its extra elimination-round match|
| 1-4                 |     2 | eliminated                                                     |
| 0-4                 |     1 | sole winless; eliminated                                       |
| total               |    16 |                                                                |

"decider winner/loser" (Chinese client: taotaisai shengzhe / baizhe) are the 5 WINNERS and 5 LOSERS
of the extra elimination round played among the five 3-2 teams and five 2-3 teams. They are NOT a
single "special winner/loser", and -- critically -- they are NOT the 3-2 / 2-3 record groups: each
extra-round match is a 3-2 team vs a 2-3 team, and a 2-3 team can win while a 3-2 team can lose. So
the "decider winner" bucket may contain 0-5 of the 2-3 teams (and "decider loser" 0-5 of the 3-2
teams). Advancing 8 = one 4-0 + two 4-1 + five decider winners. The middle 10 slots (both decider
buckets) are the hardest; the extremes (4-0, 0-4, 4-1, 1-4) are where model confidence is highest.

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

## 5. Timing (re-verified 2026-08-09 with TIER-1 sources; client countdowns observed 2026-08-03)
- Group-stage predictions lock when the FIRST group-stage match begins - by Valve's own wording
  (Tier 1, Valve blog 2026-07-31, dota2.com/newsentry/678505520073540063): "before the first match
  starts (10am CST, Thursday 8/13)". Valve's TI2026 ticket post demonstrably uses CST = China
  Standard Time ("2pm China Standard Time ... From 2:30pm (CST)"), so the strongly supported reading
  is 10:00 UTC+8 = **2026-08-13T02:00:00Z**. The circulating "15:00 GMT" figure (Strafe) is that same
  Valve sentence parsed as US Central and would be 23:00 in Shanghai - graded a conversion error; it
  is also inconsistent with the in-client "9 days" countdown observed 2026-08-03 and with TI2025's
  10:00-local day-1 start. Caveats: Valve has not spelled the timezone unambiguously for this
  specific sentence; the official Chinese localization omits the deadline sentence entirely; the
  league feed carries no per-match times yet. **The in-client countdown is the final authority -
  reconfirm hour:minute before submitting.**
- Machine-readable official schedule source (the data behind the game client):
  `https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001/?league_id=19719`. As of 2026-08-09
  its Swiss round-1 nodes have no teams and no scheduled_time. The league window opens 2026-08-12
  00:00 UTC; TI2025's round-1 pairings were published about 47 hours before its first match, so
  expect the TI2026 draw around 2026-08-11.
- Main-event prediction opens ~13 days after 2026-08-03 -> approximately 2026-08-16.
- Winner rewards finalized 2026-08-28.
- Because submission is irreversible, target completion at least one hour before the lock, and
  reconfirm the exact in-client countdown (hour:minute, server timezone) on the day.
- Group draw status 2026-08-09: pods and round-1 pairings NOT published (Valve feed nodes empty;
  Liquipedia under construction; DLTV/BLAST empty).

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

## 9. Group-stage FORMAT (drives the simulator) -- verified 2026-08-03
- Modified Swiss, UP TO 5 rounds, 16 teams, every series Bo3. A team STOPS once it reaches its 4th
  series win (advances directly) or 4th series loss (eliminated); it plays no further Swiss rounds.
  So 4-0 and 0-4 teams play only 4 series; 4-1 / 3-2 / 2-3 / 1-4 teams play 5. "5-round" is the max
  number of pairing rounds, not a per-team game count.
- Same-record pairing forces a STRUCTURALLY FIXED post-Swiss record distribution:
  4-0 x1, 4-1 x2, 3-2 x5, 2-3 x5, 1-4 x2, 0-4 x1 (= 16 teams, 39 series).
- Two initial pods of 8. Rounds 1-3 pair only within a team's own pod; round 4 pairs across pods
  (this is what pairs the two unbeaten pod leaders, producing the single 4-0). Round 5 pairs the
  remaining record groups.
- Pairing principles: (a) same record first [hard]; (b) avoid rematches [soft -- "try to avoid"];
  (c) minimize rank gap [soft]. EXCEPTION: in round 5, ONLY matches whose loser is directly
  eliminated (the 1-3 matches) are paired to MAXIMIZE the rank gap; every other R5 match keeps the
  normal minimize-gap rule. Do NOT generalize gap-maximizing to the 3-1 or 2-2 R5 matches.
  R5 match types: 3-1 (winner 4-1 advances / loser 3-2 to decider); 2-2 (both to decider);
  1-3 (winner 2-3 to decider / loser 1-4 out -- this last one is the gap-maximized match).
- After Swiss: the 3 top-ranked teams (the 4-0 and the two 4-1) advance directly; the five 3-2 and
  five 2-3 teams play an extra elimination round; the 1-4 x2 and 0-4 x1 (ranks 14-16) are eliminated.
- Extra elimination round: five Bo3 matches, each a 3-2 team vs a 2-3 team. Seeding is a PICK ORDER:
  the highest-ranked 3-2 team picks any of the five 2-3 teams; the next 3-2 team picks from those
  remaining; and so on; the last 3-2 team faces the last 2-3 team. The 5 match WINNERS advance (top 8
  to main event) and fill the client's "decider winner" slots; the 5 LOSERS are eliminated and fill
  "decider loser". A 2-3 team can win and a 3-2 team can lose, so these buckets are NOT the 3-2 / 2-3
  record groups -- see section 2. The predictor must compute P(record) x opponent-selection x
  decider-win, not drop the 3-2 teams mechanically into "decider winner".
- Main-event seeding is by final Swiss rank (a 2-3 team that wins its decider still seeds by its own
  Swiss rank; the decider only decides advance vs eliminate).
- Swiss ranking tiebreakers, in order: (1) series_wins; (2) series_losses; (3) opponents_series_wins
  (strength of schedule -- NOT head-to-head); (4) game_win_percentage (per map/game, not per series);
  (5) opponents_average_game_win_percentage; (6) average_game_duration (shorter is better);
  (7) coin_toss. No head-to-head tiebreaker is used.

### Tier-1 confirmation and one residual format uncertainty (2026-08-09)
Valve's league data feed (league_id 19719) CONFIRMS the core format at Tier 1: a 16-team Swiss node
group with max_rounds=5 and win_loss_limit=4, advancing 3 to the playoff plus 10 into a 5-match
elimination round - exactly the structure implemented in the simulator. However, NO machine-readable
or database source mentions the "two initial pods"; that detail rests solely on the in-client rules
transcription (the official rulebook page is a script-rendered shell that cannot be read
programmatically). Residual risk is bounded: the pre-draw study found 14/16 slots invariant across
three different pod mechanisms, the record distribution 1/2/5/5/2/1 is forced regardless of pods,
and once the real round-1 pairings post, round 1 is exact. If the published draw shows no pod
structure, treat the pod constraint as a pairing-preference assumption and note it on the output.

### Two points the official rules do NOT resolve (modeling assumptions, not lookups)
- C5 -- pairing tie-break: when several legal pairings satisfy the principles equally, the official
  text does not state how the organizer chooses (random draw / fixed seeding / manual), nor the
  precedence when "avoid rematch" and "minimize gap" conflict. The simulator must ENUMERATE or SAMPLE
  over all rule-legal pairings rather than hard-code one, and report this as modeled uncertainty.
- D4 -- opponent choice in the extra round: the rules fix the pick ORDER but not WHICH 2-3 opponent a
  3-2 team picks (a strategic team decision). Default assumption: each 3-2 team, in pick order, takes
  the remaining 2-3 opponent that MAXIMIZES its own model win probability (rational self-interest),
  with a sensitivity check under random assignment (and optional selection noise). State the
  assumption on every output.

The simulator (`ti_predict/simulate.py`) must implement: the stop-at-4W/4L up-to-5-round Swiss; the
two-pod R1-3 / cross-pod R4 pairing; the narrow R5 gap-maximizing rule for elimination matches only;
the pick-order extra elimination round with the D4 opponent-choice assumption; the C5 legal-pairing
sampling; and the 7 tiebreakers -- then pass rule-level verification BEFORE any formal output. It is
currently only mechanics-validated. Runtime inputs still needed at lock time: the official two-pod
split (C1) and the round-1 pairings (C2).

## 10. Field - confirmed 16 (matches inputs/teams.csv)
Direct invites (7): Aurora Gaming, BetBoom Team (BoomBoys), Team Falcons, Team Liquid, Tundra Esports
(plays as 1w Team), Xtreme Gaming, Team Yandex.
Qualifiers (9): PARIVISION (Team Vision), Team Spirit, HULIGANI (L1ga), Nigma Galaxy [EU x4];
Vici Gaming, Team Resilience [CN x2]; OG [SEA]; LGD Gaming [SA]; GamerLegion [NA].
Qualifiers closed ~late June 2026; the field is locked. MOUZ is NOT in the TI15 field (it appeared in
the unrelated Astana "Future Games" event). No B0 reopening is required.

## 11. Corrections to earlier notes
- Prize pool is $1.6M (the earlier $1M was the Astana Future Games event).
- [2026-08-03 entry, itself revised 2026-08-09 - see the bullet below] Group-prediction lock was
  restated as ~Aug 13 15:00 UTC = 23:00 Beijing on the assumption the source's "10am CST" meant US
  Central; that assumption is now graded wrong.
- The prediction is a 16-slot full assignment, not a 6-extreme pick; "decider winner/loser" are 5+5
  teams, not one "special winner/loser".
- The Swiss is UP TO 5 rounds with stop-at-4-wins / stop-at-4-losses, NOT a fixed 5 rounds for every
  team (verified 2026-08-03; corrects the earlier "5-round" phrasing).
- "decider winner" != the 3-2 record group and "decider loser" != the 2-3 record group; the decider
  match is 3-2 vs 2-3 and either can win (corrects the earlier bucket mapping).
- The R5 "maximize rank gap" rule applies ONLY to matches whose loser is directly eliminated (the
  1-3 matches), not to all round-5 matches (corrects the earlier over-broad phrasing).
- 2026-08-09: the lock-time estimate is revised from 15:00 UTC to 02:00 UTC (10:00 UTC+8). The
  earlier note read the source's "10am CST" as US Central; the China Standard Time reading matches
  the host timezone and the in-client countdown arithmetic. Neither is first-hand Valve wording -
  the in-client countdown remains the final authority (sec 5).

## 12. Open items
Rule-level verification is DONE (2026-08-03, cross-checked vs dota2.com/esports/ti15/tirules,
Liquipedia, CyberScore, Strafe). What remains:

Runtime inputs, published with the official draw around Aug 13 (feed into the simulator, not blockers
to building it):
1. C1 -- the actual two-pod split (which 8 teams in each initial group).
2. C2 -- the actual round-1 pairings within each pod (organizer-preset; seeding algorithm unknown).
3. G1 -- the exact in-client lock timestamp (best external estimate: Aug 13 02:00 UTC = 10:00 UTC+8; see sec 5, older 23:00
   Beijing); confirm on the client.

Low priority / non-blocking:
4. G2 -- whether reward tiers stack (structure implies they do not; affects only how hard to chase a
   tier, not the slate). No official wording seen.

Modeling assumptions (decided in code, not lookups; see section 9): C5 legal-pairing sampling and D4
opponent-choice. These are stated on every output and covered by sensitivity checks.

## Sources
- In-client activity, transcribed by the client owner, 2026-08-03 (primary).
- The International 2026, team field and format: blast.tv, hotspawn.com (2026-06-28), dltv.org.
- Predictions lock time: strafe.com predictions-and-rewards writeup.
