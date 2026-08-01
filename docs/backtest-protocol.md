# Backtest protocol — FROZEN 2026-08-01 (pre-registered before any results)

This is committed before fitting or reporting any model numbers. Changing it after seeing results is
a protocol violation; if a change is unavoidable it must be a new dated section, not an edit.

## 1. Splits — chronological, event-level, rolling (walk-forward)
- Order official events by start date. For each test event `E`, train **only** on maps dated
  `< E.start`; predict every map in `E`; then roll forward to the next event. **No random splits.**
- **As-of roster reconstruction:** within a fold, team identity / ids / rosters are frozen at
  `E.start` using only information available then (played-match lineups, announcements, entry lists
  before `E`). **No post-`E` match may confirm an earlier roster.**
- **No future leakage** of ratings, rosters, event tiers, patches, or results across the boundary.

## 2. Metrics & selection
- **PRIMARY: log-loss** (map-win probability; and series-win probability, reported separately).
- **Secondary:** Brier score; **calibration** (reliability curve + ECE).
- **Swiss-simulation final-standing error:** downstream **diagnostic only** — never a selection
  criterion.
- **Selection rule:** a candidate must beat **plain Elo consistently across folds** — lower log-loss
  in a clear majority of individual folds, not merely a better pooled/aggregate average. Report
  **per-fold** results, with a sign test / fold-win count, alongside the pooled number.

## 3. Baselines — first comparison kept clean
- **A — plain Elo:** opponent-only; single global K; map-win prob = logistic(rating diff). No other
  features.
- **B — time-decay / roster-aware Elo or dynamic Bradley-Terry:** recency decay + roster-continuity
  as explicit sample weights; nothing else.
- **C — standard / minimally-modified Glicko-2:** rating + RD + volatility + inactivity only; **no
  stacked hand weights.**
- **Frozen exclusion:** event-tier, cross-region, patch, and player-prior weights are **NOT** in the
  first comparison. Each is added **later, one at a time, as a separate ablation**, and kept **only**
  if rolling backtests show **stable** (multi-fold) improvement over the best clean baseline.

## 4. Map vs series evaluation
- Evaluate **both** map win probability and series win probability (map `p` -> series via
  `series.py` binomial).
- **Series contribution cap:** each series contributes at most one "unit" of weight regardless of how
  many maps it went — implemented as per-map weight `1 / maps_in_series` (so a 2:1 Bo3 does not count
  as three independent observations). Documented in the harness.
- **Bo2 draws:** a Bo2 can finish 1-1. **Frozen handling:** Bo2 maps are kept for **map-level** eval
  (two independent map results); Bo2 series are **excluded from the binary series-win** metric (a
  1-1 has no winner) and reported separately as a count. No silent dropping.
- **Missing / reconstructed series_id:** a map with no `series_id` is treated as its **own singleton
  series** for the cap (conservative — never inflates weight). If series reconstruction is used it is
  by `(event, day, opponent)` only, and the reconstructed count is reported. Report the fraction of
  maps lacking a real `series_id`.

## 5. Thin / roster-flux teams (Nigma, OG, Resilience) — ablation, not a fixed choice
Compare three treatments and pick per rolling backtest (do **not** fix one in advance):
  (i) **no player prior** (team-only rating, high initial RD);
  (ii) **heavily-shrunk player prior** (five players' history as a strongly-regularized prior);
  (iii) **uncertainty widening only** (inflate RD, no point-estimate shift).

## 6. Opponent-graph coverage — reported BEFORE fitting (gate)
Report on the roster-map set: number of teams (nodes incl. opponents), edges (distinct matchup
pairs), connected components + largest-component coverage of the 16 TI teams, cross-region links
among the 16 (by region), and each TI team's opponent breadth (distinct opponents). A disconnected
graph, or too few cross-region edges, means ratings are **not comparable** across the gap — flag it
and prefer market anchoring there rather than trusting the model.

## 7. Market comparison — strictly out of sample
- Only on folds/matches with **timestamped, sufficiently complete** odds (record source + timestamp;
  Shin de-vig). Compare **market-only**, **model-only**, **fused**.
- **Fusion coefficient alpha learned strictly out of sample** (fit on earlier folds, apply to later);
  never hand-set. Where odds are absent (Swiss exact standings, stat questions), model + shrinkage
  stands alone.

## 8. Production gate
**No TI2026 probabilities are emitted** until a candidate: (a) beats plain Elo consistently across
folds on **log-loss**, (b) has acceptable calibration, and (c) where odds exist, adds increment over
market **out of sample**. Until then the outputs are the graph coverage, the baseline comparison, and
calibration only.
