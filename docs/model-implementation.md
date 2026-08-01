# Model implementation — v1 screening (exact formulas & constants, frozen 2026-08-01)

All four candidates train on the **rating universe** (8544 pro maps; opponents included via their
other games) and are **evaluated only on the 1177 target maps**. What is fit is a **map** win
probability `p = P(team_a beats team_b)`; series probabilities come from `series.py`.

## Shared
- Identity: the 16 TI rosters = organization (source_team_ids collapsed); every other pro team =
  `t{team_id}` (calibration only).
- Chronological processing over the **train portion** of the universe (`start_time < fold.cutoff`);
  ratings frozen at the cutoff; the whole held-out event predicted with no intra-event update.
- **No side (radiant/dire) term in v1** — all candidates ignore it equally; added later as a v2
  ablation (a global radiant prior).
- `w_series = 1 / series_size` (series-cap) is the primary EVAL weight.

## A-elo (plain Elo)
`E_a = 1 / (1 + 10^((R_b - R_a)/400))`; after each map `R_a += K (S_a - E_a)`, `S in {1,0}`.
Constants: init `R=1500`, `K=24`, scale `400`. No decay, no home term.

## B-eloTD (inactivity-regressed Elo)
As A-elo, but when a team returns after `d` idle days, regress toward the mean first:
`R <- 1500 + (R - 1500) * 0.5^(d/180)` (half-life **180 days**). Same K=24, scale 400, init 1500.

## B-bt (Bradley-Terry, weighted L2 logistic, refit each fold)
`P(a>b) = sigmoid(s_a - s_b)`. Fit strengths `s` by weighted regularized MLE on all train maps:
- weight `w_m = exp(-ln2 * (cutoff - start_m)/86400 / 90) * (1/series_size_m)` (time half-life
  **90 days** x series-cap).
- ridge `lambda * ||s||^2`, `lambda = 1.0` (≈ one pseudo-match vs the mean; keeps thin/unidentified
  teams near 0). Solve by L-BFGS to convergence; `s` mean-centered.
Predict `sigmoid(s_a - s_b)` with frozen `s`.

## C-glicko2 (standard, Glickman 2013)
Constants: init rating `1500`, RD `350`, volatility `sigma=0.06`, `tau=0.5`, scale `173.7178`.
**Rating period = 7 days**: batch each team's results in the period and apply the standard Glicko-2
update; an idle period inflates RD via `RD' = sqrt(RD^2 + sigma^2)`. Predict with the standard
`E = 1/(1+exp(-g(sqrt(RD_a^2+RD_b^2)) (mu_a - mu_b)))`, frozen at cutoff.

## Fractional series weights & draws (frozen)
- Map-level eval scores every map (incl. Bo2 maps), weighted by `w_series`.
- Series-level eval: series win prob from map `p` via `series.py`; **Bo2 draws (35 series) excluded**
  from the binary series-win metric and reported as a count. Best-of inferred from a series' map
  count (a 2-map non-draw series = a 2-0 Bo3 prefix).
- Missing `series_id` (7 maps) = singleton series (weight 1).

## Screening semantics (v1 is untuned)
A candidate **advances** only if it beats `A-elo` with a **calibrated, consistent** margin
(per-fold majority win + event-blocked CI on the log-loss difference excluding 0). A **tie or
universal failure triggers a separately preregistered nested-tuning v2** (hyperparameters tuned
strictly inside each outer training fold) — it is **not** evidence the model family failed.
