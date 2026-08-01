# Attrition: 1842 roster-maps -> 1177 training maps

Not data loss — it is (a) routing predecessor-lineup maps to the player-prior track and (b)
de-duplicating maps between two TI teams (counted once per team in the roster view). Exact global
reconciliation:

```
1842  roster-map rows (roster_matches.csv, overlap >=3; 5/5=1361, 4/5=350, 3/5=131)
 -131  overlap-3 maps = a predecessor lineup (only 3 of the current 5) -> player-prior track, NOT team history
=1711  current-roster rows (overlap >=4: 5/5 direct + 4/5 stand-in)
 -533  TI-vs-TI duplicate perspectives (a map between two TI teams appears once per team; kept once)
   -1  map missing from the proMatches scan (no team ids)
=1177  unique training maps  (check: 1177 + 533 + 131 + 1 = 1842)
```

## By TI team (perspective counts, pre global-dedup; from roster_coverage.csv)
Kept = 5/5 (direct) + 4/5 (stand-in, discounted). Routed-to-prior = 3/5 (predecessor lineup).

| team | 5/5 | 4/5 | kept | 3/5 -> prior |
|------|----:|----:|----:|-----:|
| Aurora | 117 | 26 | 143 | 0 |
| BetBoom | 140 | 0 | 140 | 0 |
| Falcons | 90 | 17 | 107 | 0 |
| Liquid | 89 | 38 | 127 | 0 |
| Tundra->1w | 96 | 31 | 127 | 0 |
| Xtreme | 115 | 5 | 120 | 0 |
| Yandex | 71 | 26 | 97 | 0 |
| Resilience | 35 | 0 | 35 | 0 |
| Vici | 98 | 19 | 117 | 0 |
| LGD (SA) | 113 | 14 | 127 | 0 |
| OG | 21 | 44 | 65 | 0 |
| GamerLegion | 76 | 15 | 91 | 0 |
| Spirit | 63 | 39 | 102 | 23 |
| PARIVISION | 80 | 66 | 146 | 0 |
| HULIGANI | 129 | 10 | 139 | 6 |
| Nigma | 28 | 0 | 28 | **102** |

Notes:
- **Nigma** is the extreme case: only **28** current-roster maps; **102** maps are a predecessor
  lineup (3/5) now routed to the player-prior track, not counted as the current team's history.
- **OG** keeps 65 but 44 of them are 4/5 (stand-in) -> will be discounted, not treated as full.
- Perspective counts sum above the global 1177 because TI-vs-TI maps are counted for both teams here
  but once in the training set.
