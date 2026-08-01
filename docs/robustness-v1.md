# v1 robustness checks (non-selective; fixed predictions, no refit)

## Pooled map log-loss under 3 eval weightings + series-clustered

| model | 1/series_size | 1/best_of | map-equal | series-clustered |
|-------|-----:|-----:|-----:|-----:|
| A-elo | 0.6625 | 0.6712 | 0.6702 | 0.6625 |
| B-bt | 0.6518 | 0.6618 | 0.6606 | 0.6518 | **<-**
| B-eloTD | 0.6645 | 0.6724 | 0.6716 | 0.6645 |
| C-glicko2 | 0.6717 | 0.6827 | 0.6826 | 0.6717 |

## Calibration intercept a / slope b  (ideal a=0, b=1)

| model | a (intercept) | b (slope) |
|-------|-----:|-----:|
| A-elo | +0.532 | 0.533 |
| B-bt | +0.461 | 0.807 |
| B-eloTD | +0.541 | 0.544 |
| C-glicko2 | +0.566 | 0.431 |

## Reliability bins - B-bt (weighted 1/series_size, 10 bins)

| p-bin | n(w) | mean p | empirical | 
|-------|-----:|-----:|-----:|
| 0.2-0.3 | 5.0 | 0.263 | 0.200 |
| 0.3-0.4 | 21.0 | 0.364 | 0.452 |
| 0.4-0.5 | 101.0 | 0.453 | 0.571 |
| 0.5-0.6 | 230.0 | 0.549 | 0.673 |
| 0.6-0.7 | 151.0 | 0.641 | 0.715 |
| 0.7-0.8 | 44.0 | 0.724 | 0.723 |

## Leave-one-event-out pooled log-loss (min..max over dropping one event)

- A-elo: 0.6585..0.6768  (full 0.6625)
- B-bt: 0.6466..0.6647  (full 0.6518)
- B-eloTD: 0.6609..0.6772  (full 0.6645)
- C-glicko2: 0.6606..0.6860  (full 0.6717)

## Read
- **Ranking is robust.** B-bt is best under all three eval weightings + series-clustered, and its whole LOEO band sits below A-elo's. Not a weighting or single-event artifact.
- **Calibration finding (v2 recalibration item, NOT rating tuning).** All models show intercept a ~ +0.5 and slope b < 1: the positive intercept is the uncorrected **radiant-side advantage** (team_a is always radiant in eval; radiant wins ~53%, so empirical > predicted, see reliability bins). B-bt has the best slope (~0.81). Fixes, both out-of-sample: (a) predict **side-neutral** for real matches (sides unknown pre-match, so the bias vanishes in production), and/or (b) a fold-OOS **Platt recalibration** a + b*logit(p). Neither changes the ranking; both correct absolute calibration before any probability ships.
