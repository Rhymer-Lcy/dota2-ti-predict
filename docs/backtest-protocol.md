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

---

## Addendum A — evaluation locks (frozen 2026-08-01, before any results)

1. **Event-frozen PRIMARY evaluation.** Folds = events (OpenDota `leagueid`), ordered by first map
   date (23 folds, 2026-02..08). For test event E: train only on maps dated `< E.start`, freeze all
   ratings + roster identity at E.start, and predict the **entire** held-out event **without updating
   from results inside E**. This mirrors the TI client (picks locked pre-event). A sequential
   within-event update variant MAY be reported but **must not drive selection**.

2. **Candidate set — ambiguity resolved: both run, separately named. All hyperparameters FROZEN
   (no tuning in v1 -> no tuning leakage).**
   - `A-elo` — Elo: init 1500, K=24, logistic scale 400, no side/home term.
   - `B-eloTD` — time-decay Elo: A + inactivity regression toward 1500 with 180-day half-life on idle
     days between a team's games.
   - `B-bt` — Bradley-Terry: weighted logistic MLE of team strengths on the training maps; weights =
     `exp(-ln2 * age_days / 90)` (90-day half-life) x series-cap weight; ridge = 1 pseudo-match vs the
     mean per team; refit each fold; predict `logistic(strength_a - strength_b)`.
   - `C-glicko2` — Glicko-2: init 1500 / RD 350 / vol 0.06 / tau 0.5; rating period = 7 days;
     inactivity inflates RD.
   Later tuning, if any, only **inside each outer training fold**, reported separately.

3. **Weighting sensitivity (non-selective — reported, never used to select):** primary =
   `1 / actual_series_size` (preregistered). Also report (i) `1 / best_of`, (ii) map-equal training
   with series-clustered evaluation. Selection uses the primary only.

4. **Per-fold opponent-graph diagnostics:** re-run the graph at each fold cutoff on train-only data —
   component coverage of the teams in E, cross-region edges + recency, and bridge-team dependence.
   Full-sample connectivity does not prove earlier folds were connected.

5. **Uncertainty:** report paired, **event-blocked** uncertainty (block bootstrap over events on the
   candidate-minus-`A-elo` log-loss difference) + per-fold point estimates + a fold-win sign test.
   Selection = consistent per-fold wins over `A-elo`, not a pooled average.

6. **Market comparison:** only odds **timestamped <= the event's prediction cutoff** (never later /
   closing lines); Shin de-vig; compare market-only / model-only / fused; fusion alpha fit strictly
   out-of-sample (earlier folds -> later).

7. **Attrition** published in `attrition.md` (1842 -> 1177: overlap-3 routed to player-prior +
   TI-vs-TI dedup). Training set = current-roster maps only (overlap >= 4).

Gate unchanged (above). No TI2026 probabilities until it passes.

---

## Addendum B — universe/folds/screening locks (frozen 2026-08-01)

1. **Rating universe != evaluation set.** Ratings train on the **full pro universe** (8544 maps in
   the as-of window, `universe_maps.csv`) so opponents are identified by their *other* games;
   **evaluation is restricted to the 1177 preregistered target maps** (current TI rosters). Sizes
   reported separately. Non-TI teams keep a fixed `t{id}` identity (calibration only; their roster
   churn is out of scope).

2. **Explicit frozen fold table** (`inputs/folds.csv`, 23 folds) — one per event (leagueid) with
   `league_name, start, end, cutoff, n_target, n_train_universe`. **Training eligibility is by time,
   not league membership:** a map trains iff `start_time < fold.cutoff`. This prevents leakage from
   temporally overlapping events (a concurrent league's later maps are excluded by the time cutoff).
   Exact formulas/constants for the four candidates: `model-implementation.md`.

3. **Screening semantics.** v1 is untuned and is a *screening* comparison. A clear, calibrated winner
   over `A-elo` advances; a **tie or universal failure triggers a separately preregistered
   nested-tuning v2** (tuning strictly inside each outer training fold) rather than a conclusion that
   the model families failed.

4. **Robustness reporting.** Report per-fold sizes and **leave-one-event-out (LOEO)** sensitivity of
   the aggregate, so neither many tiny folds nor one large event (e.g. DreamLeague S29 = 169, EWC =
   142) silently determines the outcome. Uncertainty via event-blocked bootstrap (Addendum A.5).

Gate unchanged. No TI2026 probabilities until it passes.

---

## Addendum C — market-gate feasibility & two-track output (frozen 2026-08-01)

- **B-bt promoted to the primary model candidate** (v1 gates (a) log-loss + (b) calibration passed:
  17/23 folds, bootstrap CI excludes 0, best Brier + ECE). See `backtest-results-v1.md`.

- **Current client screenshots do NOT clear the historical market-OOS gate (c).** The screenshot
  "crowd percentage" is the share of *contest participants* who picked an option (an input to
  expected-points), **not** a bookmaker's implied probability; and a single current snapshot cannot
  fit a fusion coefficient alpha **out of sample**. Strictly clearing (c) still requires multiple
  historical folds with **timestamped odds visible at each fold's cutoff**.

- **Feasibility:** historical timestamped esports odds are not obtainable here (no free source; paid
  feeds prohibit betting-use). Per the protocol-revision provision, output is therefore split into
  two tracks. This does **not** retroactively claim (c) passed — gate (c) is **unresolved / not
  cleared** (not merely "open") and is flagged on every output.
  - **Track 1 — model-only probability:** B-bt probabilities (map -> series -> Swiss/bracket) MAY be
    emitted (it cleared gates (a)+(b)), but **every such output is labeled "model-only; NOT validated
    against historical market increment."**
  - **Track 2 — contest decision:** once the client's questions, point values and crowd percentages
    are provided, compute **expected points on the FIXED B-bt probabilities**. This is **not** market
    fusion; **no alpha is fit**; crowd% is used only for EV / differentiation, never as a probability.

- On receiving screenshots, first classify their content — crowd pick %, official prediction
  probabilities, or true odds — before deciding use.

- **Track-2 calibration: production = IDENTITY side-neutral B-bt (CONCLUSIVELY frozen).**
  Two scores, reported separately: **0.6444** side-aware diagnostic (actual side known) vs **0.6518**
  production-aligned side-neutral (side unknown -- what ships). The clean **symmetric-OOF temperature
  test** (`calibration-sideaware.md`; each OOF obs + its (B,A,1-y,1-p) mirror at half weight;
  zero-intercept temperature fit strictly on prior folds; removes team-a base-rate confounding,
  preserves P(A>B)+P(B>A)=1) shows temperature **fails** (LL 0.6518 -> 0.6573, ECE 0.038 -> 0.049) ->
  **no calibration layer**. The symmetrized side-neutral B-bt is already well-calibrated (ECE 0.038).
  Measured c=+0.088 rules out radiant-side **advantage** as the main cause of the fixed-side +0.4
  intercept, but **not** team-a ordering / evaluation base-rate effects (unresolved; symmetrization
  confirms they were the confound). **B-bt still beats A-elo 17/23 folds.** Temperature form:
  `q = sigmoid(b*logit(p))`, `b<1` softens, `b>1` sharpens. AT THE TI CUTOFF: **refit B-bt** on all
  eligible pre-cutoff data and emit side-neutral probs -- **no production Platt to refit**; the
  temperature candidate stays DISABLED unless the preregistered symmetric-OOF test passes. Never
  update from crowd%/odds/results. Frozen = the pipeline spec, not the numbers.
  **Scope:** identity is the best *validated* choice **among the frozen candidates**, not universally
  or theoretically optimal; ECE (under the specified symmetric binning) is an **auxiliary** metric,
  with **log-loss and Brier primary**.

- **Simulator gate:** `simulate.py` is mechanics-validated only (monotonicity + normalization on
  synthetic strengths). Before ANY formal tournament output (even model-only Track 1) it must pass a
  **rule-level verification** against the official TI2026 Swiss pairing, special-elimination, and
  8-team seeding rules once posted.
