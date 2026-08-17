# TI15 Main Event prediction (OFFICIAL)

- commit `0f6c691` | generated 2026-08-17T09:41:58+00:00 | cutoff 2026-08-16T12:00:00+00:00
- snapshot: after the final Elimination Round series (Team Yandex 2-1 LGD Gaming, 2026-08-16); before any Main Event match
- model: **B-bt / h90 / lambda=1.0 / calibration none** (frozen, radiant c=+0.0940)
- inputs: 44 TI15 series inserted (109 maps) on top of 8690 historical maps; network=False, odds=False
- optimization: exact over all 16384 coherent slates x 16384 outcomes; 1000 series-blocked bootstrap draws over 4428 blocks

## Strength evolution (frozen estimator; only the data changed)

| team | pre-TI | post-Swiss | serve | +/- (bootstrap SD) | attributable to TI15 |
|---|---:|---:|---:|---:|---:|
| PARIVISION | +1.285 | +1.367 | **+1.369** | 0.137 | +0.100 |
| Team Falcons | +1.056 | +1.033 | **+1.064** | 0.176 | +0.022 |
| Team Yandex | +1.067 | +1.018 | **+1.026** | 0.165 | -0.025 |
| BetBoom Team | +1.022 | +0.957 | **+0.997** | 0.160 | -0.011 |
| Team Spirit | +0.848 | +0.848 | **+0.856** | 0.170 | +0.022 |
| Team Liquid | +0.767 | +0.829 | **+0.830** | 0.154 | +0.076 |
| Nigma Galaxy | +0.605 | +0.766 | **+0.768** | 0.226 | +0.174 |
| Tundra Esports | +0.545 | +0.614 | **+0.649** | 0.161 | +0.116 |

## Tournament probabilities

| team | champion | 90% CI | reach GF | win UBQF | reach UBF | win UBF |
|---|---:|---:|---:|---:|---:|---:|
| PARIVISION | **0.348** | 0.201-0.498 | 0.519 | 0.634 | 0.448 | 0.286 |
| Team Falcons | **0.158** | 0.055-0.301 | 0.324 | 0.603 | 0.328 | 0.161 |
| Team Yandex | **0.138** | 0.050-0.269 | 0.295 | 0.572 | 0.299 | 0.143 |
| BetBoom Team | **0.113** | 0.036-0.225 | 0.231 | 0.366 | 0.215 | 0.110 |
| Team Spirit | **0.079** | 0.022-0.170 | 0.192 | 0.571 | 0.208 | 0.096 |
| Team Liquid | **0.067** | 0.020-0.139 | 0.174 | 0.428 | 0.194 | 0.080 |
| Nigma Galaxy | **0.062** | 0.007-0.169 | 0.159 | 0.397 | 0.179 | 0.073 |
| Tundra Esports | **0.036** | 0.008-0.084 | 0.106 | 0.429 | 0.129 | 0.051 |

## Optimization

| slate | E[official score] | E[correct] |
|---|---:|---:|
| greedy coherent favourite | 2222.2 | 5.060 |
| max E[correct] | 2288.1 | 5.119 |
| **max E[official score] (primary)** | **2288.5** | 5.109 |

## Primary 14-slot slate

| sel | round | matchup | pick | P(win \| matchup) | P(pick wins node) | cost to change | fragile |
|---:|---|---|---|---:|---:|---:|---|
| 801 | UBQF | Tundra Esports vs Team Spirit | **Team Spirit** | 0.577 | 0.571 | 127.2 | - |
| 802 | UBQF | PARIVISION vs BetBoom Team | **PARIVISION** | 0.636 | 0.634 | 477.8 | - |
| 803 | UBQF | Team Liquid vs Team Yandex | **Team Yandex** | 0.573 | 0.572 | 92.5 | - |
| 804 | UBQF | Nigma Galaxy vs Team Falcons | **Team Falcons** | 0.609 | 0.603 | 152.2 | - |
| 805 | UBSF | Team Spirit vs PARIVISION | **PARIVISION** | 0.684 | 0.448 | 277.4 | - |
| 806 | UBSF | Team Yandex vs Team Falcons | **Team Falcons** | 0.514 | 0.328 | 19.3 | YES |
| 807 | UBF | PARIVISION vs Team Falcons | **PARIVISION** | 0.612 | 0.286 | 75.0 | - |
| 808 | GF | PARIVISION vs Team Falcons | **PARIVISION** | 0.640 | 0.348 | 156.0 | - |
| 809 | LBR1 | Tundra Esports vs BetBoom Team | **BetBoom Team** | 0.628 | 0.379 | 221.2 | - |
| 810 | LBR1 | Team Liquid vs Nigma Galaxy | **Nigma Galaxy** | 0.477 | 0.267 | 0.4 | YES |
| 811 | LBR2 | Team Yandex vs BetBoom Team | **BetBoom Team** | 0.489 | 0.198 | 66.2 | YES |
| 812 | LBR2 | Team Spirit vs Nigma Galaxy | **Team Spirit** | 0.533 | 0.173 | 34.7 | YES |
| 813 | LBSF | BetBoom Team vs Team Spirit | **BetBoom Team** | 0.553 | 0.138 | 20.2 | YES |
| 814 | LBF | Team Falcons vs BetBoom Team | **Team Falcons** | 0.525 | 0.163 | 19.3 | YES |

## Runner-up and fragility

- second-best coherent slate: E[score] 2288.1 (regret 0.39), differs at 810 (Nigma Galaxy -> Team Liquid)
- paired resolution of that difference (40000 draws): plug-in +5.21, bootstrap mean +0.36 (MC SE 0.31), median +1.72, 95% CI [-127.2, +120.5], P(delta>0)=0.5111 -> **TIE**: the paired 95% interval spans zero and the mean difference is under 6 points, 5% of one correct node. The sign is NOT resolved: this says the two slates are evidentially indistinguishable, not that their true difference is zero. The fixed-seed 1000-draw production approximation has a unique NUMERICAL argmax, and the production decision procedure takes it, so the client pick stays the primary. That is emphatically NOT a claim that the underlying uncertainty-integrated objective has a unique argmax, nor that Nigma Galaxy is truly the better pick: the 40,000-draw paired comparison does not resolve the sign. The pick is determinism, not evidence.
- best slate with a different champion (Team Falcons): E[score] 2132.5 (regret 155.99)

## Client actions

- slot 801 - Upper Bracket Round 1 Match 1: **Team Spirit**
- slot 802 - Upper Bracket Round 1 Match 2: **TEAM VISION**  _(model: PARIVISION)_
- slot 803 - Upper Bracket Round 1 Match 3: **Team Yandex**
- slot 804 - Upper Bracket Round 1 Match 4: **Team Falcons**
- slot 805 - Upper Bracket Round 2 Match 1: **TEAM VISION**  _(model: PARIVISION)_
- slot 806 - Upper Bracket Round 2 Match 2: **Team Falcons**
- slot 807 - Upper Bracket Final: **TEAM VISION**  _(model: PARIVISION)_
- slot 808 - Grand Final: **TEAM VISION**  _(model: PARIVISION)_
- slot 809 - Lower Bracket Round 1 Match 1: **BoomBoys**  _(model: BetBoom Team)_
- slot 810 - Lower Bracket Round 1 Match 2: **Nigma Galaxy**
- slot 811 - Lower Bracket Round 2 Match 1: **BoomBoys**  _(model: BetBoom Team)_
- slot 812 - Lower Bracket Round 2 Match 2: **Team Spirit**
- slot 813 - Lower Bracket Round 3: **BoomBoys**  _(model: BetBoom Team)_
- slot 814 - Lower Bracket Final: **Team Falcons**

Names above are the client display names transcribed from the archived bracket/schedule evidence; the model's canonical organizations are shown in parentheses where they differ.

## Caveats

- model-only; no market, crowd or manual input of any kind
- the h90 decay origin and the 44 inserted series are the only things that changed relative to the locked group-stage run; the estimator is byte-identical
- rounds 2-5 and the Elimination Round have no locally recorded timestamp; the cadence assumption is bounded by the collapse arm in gates.timestamp_sensitivity
- maps within a series are modelled as exchangeable draws, so a 2-0 and a 2-1 differ only in the third map's outcome, never in order or momentum
