# TI15 group-stage prediction (SUBMISSION-GRADE CANDIDATE - NOT FINAL LOCK-DAY RUN)

- mode: **candidate** | commit `14f4f79` | generated 2026-08-12T18:27:36+00:00
- strengths: B-bt @ 2026-08-13T02:00:00+00:00 (radiant c=+0.093) | cutoff: 2026-08-13T02:00:00+00:00 | sims: 280000 | seed: 20260813
- draw: data\ti2026\inputs\draw.json
- expected correct: **5.249 / 16**

> SUBMISSION-GRADE CANDIDATE - the production answer as of the snapshot above, under the full official gates. NOT the final lock-day run: the exact in-client lock time, any published pod membership, any newer match data and any late roster change must still be re-checked on the day.

## Slate (assignment maximizing expected correct)

- **4-0** x1: PARIVISION (0.22+/-0.00)
- **4-1** x2: Team Yandex (0.25+/-0.00), BetBoom Team (0.24+/-0.00)
- **decider_win** x5: Team Falcons (0.40+/-0.00), Aurora Gaming (0.40+/-0.00), Team Spirit (0.39+/-0.00), Team Liquid (0.39+/-0.00), Nigma Galaxy (0.34+/-0.00)
- **decider_loss** x5: Xtreme Gaming (0.39+/-0.00), Vici Gaming (0.39+/-0.00), Tundra Esports (0.39+/-0.00), LGD Gaming (0.38+/-0.00), Team Resilience (0.38+/-0.00)
- **1-4** x2: HULIGANI (0.25+/-0.00), GamerLegion (0.25+/-0.00)
- **0-4** x1: OG (0.19+/-0.00)

## Bucket probability matrix (rows = teams)

| team | 4-0 | 4-1 | decider_win | decider_loss | 1-4 | 0-4 |
|---|---|---|---|---|---|---|
| Team Falcons | 0.127 | 0.238 | 0.399 | 0.199 | 0.029 | 0.008 |
| Aurora Gaming | 0.098 | 0.196 | 0.395 | 0.255 | 0.045 | 0.011 |
| Xtreme Gaming | 0.008 | 0.032 | 0.212 | 0.395 | 0.228 | 0.125 |
| Vici Gaming | 0.019 | 0.064 | 0.298 | 0.395 | 0.157 | 0.068 |
| Team Spirit | 0.080 | 0.171 | 0.394 | 0.284 | 0.056 | 0.015 |
| Tundra Esports | 0.025 | 0.077 | 0.320 | 0.389 | 0.136 | 0.053 |
| Team Liquid | 0.056 | 0.138 | 0.387 | 0.319 | 0.075 | 0.024 |
| LGD Gaming | 0.018 | 0.068 | 0.310 | 0.382 | 0.153 | 0.069 |
| Team Resilience | 0.015 | 0.062 | 0.299 | 0.379 | 0.165 | 0.080 |
| Nigma Galaxy | 0.032 | 0.092 | 0.342 | 0.373 | 0.118 | 0.043 |
| HULIGANI | 0.005 | 0.025 | 0.186 | 0.374 | 0.251 | 0.158 |
| Team Yandex | 0.148 | 0.250 | 0.382 | 0.189 | 0.026 | 0.006 |
| GamerLegion | 0.006 | 0.027 | 0.193 | 0.383 | 0.246 | 0.145 |
| BetBoom Team | 0.136 | 0.236 | 0.386 | 0.205 | 0.030 | 0.007 |
| PARIVISION | 0.224 | 0.305 | 0.340 | 0.117 | 0.012 | 0.003 |
| OG | 0.004 | 0.019 | 0.158 | 0.361 | 0.273 | 0.186 |

## Notes
- first-five-tiebreakers-tie rate (falls to unmodeled avg-duration/coin-toss tail): standings 0.002, 3-2 pick order 0.001
- D4 selection-sensitive buckets: none
- model-only; NOT validated against historical market increment; structural/property tested, not a replica of unpublished pairing decisions; C5 pairing and D4 opponent-choice are modeling assumptions (see docs)
