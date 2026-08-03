# Validation plan v2 - historical rolling-origin backtest (design, pre-registration)

Authorized by the client (2026-08-03) as a validation phase now that the contest inputs are known.
This SUPERSEDES the "modeling parked/final" line of docs/CHECKPOINT.md **for validation purposes
only**, under the same no-leakage discipline. It does not silently change any frozen number: B-bt
stays the production model unless this plan's outer tests earn a change under the selection rule below.

## 0. The one principle
The goal is NOT "maximize historical accuracy". It is: under strict time-forward extrapolation, find a
strategy that is **cross-event stable, well-calibrated, strong on the official scoring, and not
overfit**. Tuning a dozen past events into an answer key that fails in 2026 is the failure mode to
avoid.

## 1. Protocol - rolling-origin / prequential, nested
- **Outer loop:** each historical target event `E` (a TI or high-tier international) is a pure
  out-of-sample test. Cutoff = `E`'s prediction-lock time. Train only on matches, rosters and
  identities knowable strictly before that cutoff. Never use: any `E` result, any post-lock match,
  any post-hoc roster confirmation, or final standings.
- **Inner loop (nested tuning):** hyperparameters (time-decay half-life, event weights, roster
  penalties, model family) are chosen using ONLY events earlier than `E`, then FROZEN before
  predicting `E`. Choosing a half-life after seeing `E` turns `E` into training data.
- The 2026 strategy is selected from the outer-test results only, then the chosen model is refit on
  all pre-2026-cutoff data.
- **No random splits.** No per-map independence in inference.

## 2. Three phases (validate separately; do not force old years into 2026 Swiss)
- **Phase 1 - match win-probability model.** The most sample-rich, least format-dependent layer.
  Predict map win prob, Bo3/Bo5 series win prob, and results. Metrics (per event, then aggregated):
  **log-loss (primary)**, Brier, calibration (reliability + ECE), series accuracy, and per-bin hit
  rate. Accuracy alone is never the criterion (a 55%-hedger and a 90%-overconfident model can share
  70% accuracy with very different probability quality).
- **Phase 2 - tournament advancement / placement.** Replay each event under ITS OWN real format,
  official groups and round-1 draw; predict advancement / elimination / final placement before lock;
  compare to truth. Checks whether the map probabilities propagate sensibly through structure
  (over/underrating favourites, underrating short-format upsets). Years without a reconstructable
  format are Phase-1-only and MUST NOT be claimed as 16-slot end-to-end backtests.
- **Phase 3 - 2026 16-slot policy (model-conditional; see sec 4).** May lack enough isomorphic
  historical events, so it is a strategy simulation under the frozen model, explicitly NOT an
  empirical backtest.

## 3. Candidates and pre-registered variants (freeze the list before results)
- Model families (already implemented in ti_predict/backtest.py): `A-elo`, `B-eloTD`, `B-bt`,
  `C-glicko2`.
- Pre-registered variants, added one at a time, kept only on stable multi-event improvement:
  1. B-bt time-decay half-life in {45, 60, 90, 120, 180} days.
  2. Data window / weighting: natural-year vs trailing 6/9/12 months vs long window + exp decay.
  3. Event-quality weights: equal vs LAN-up / online-down / strong-opponent-network-up (rules fixed
     in advance; never down-weight a specific event after seeing it fail).
  4. Roster change: org-only vs decayed-on-change vs retained-player-fraction vs shrunk player prior
     vs uncertainty-widening. Rosters are the as-of-lock lineup, never post-hoc.
  5. Optional simple ensembles - only if they beat the best single model across outer tests.

## 4. Convex scoring: three policies (the immediate, data-free question)
Group scoring is `f(K)`, convex in the number correct `K` (docs/contest-official-ti15.md sec 3), so
`argmax E[K]` need not equal `argmax E[f(K)]`.
- **A - max expected correct:** the current Hungarian assignment (`ti_predict/assign.py`).
- **B - max expected official points:** estimate `E[f(K)]` from the simulator's full per-run
  outcomes and local-search (pairwise swaps) from A.
- **C - robust points:** best worst-case / penalized-mean points across C5 pairing, D4 opponent
  choice, strength perturbation and seed.
Implemented in `backtest2/compare_policies.py`. It uses NO actual results and NO crowd% - it is a
decision-theory simulation UNDER the model, and does not by itself prove the model predicts. Without
player pick-share, do NOT build a contrarian anti-crowd policy; optimize expected points and
robustness only.

## 5. Reporting and selection
- Report **per event** (log-loss, Brier, series acc, predicted points, K) AND aggregates (mean,
  median, worst event, win count, recent-events, event-blocked bootstrap CI). No pooling of maps as
  independent.
- **Selection rule (not accuracy):** pick a candidate only if it (1) is no worse than frozen B-bt on
  log-loss + calibration, (2) beats it in a majority of outer events, (3) shows stable official-points
  / advancement improvement, (4) does not regress on recent events, (5) has stable params across
  years, (6) does not depend on one event/region, (7) is reproducible, (8) improves beyond MC + event
  noise. **One-standard-error rule:** among comparable candidates, choose the simpler, fewer-param,
  more stable one. A complex model that only ties frozen B-bt loses.

## 6. Data-scope reality (staged, honest)
- **Now, no new data:** Phase-1 rolling backtest over the existing 2026 universe (23 events) already
  exists; the variant sweep (sec 3) extends it. Phase 3 (sec 4) runs today on frozen B-bt.
- **Requires a historical-data project (scope, then approve before fetching):** multi-TI outer folds
  (2022-2025) and Phase-2 replay need OpenDota pulls back years PLUS per-event roster snapshots and
  per-year format reconstruction - a real effort, not free. Decide how far back to go given the payoff
  (a friend's cosmetic-reward game) before spending it.

## 6b. Scope decision (client, 2026-08-03) - LOCKED
Chosen: **D2 (2026 events for inner tuning) + TI2024 and TI2025 as OUTER held-out tests.**
- The 2026 events are the INNER tuning set (nested half-life / weight / roster-variant selection).
- **TI2024 and TI2025 are outer held-out: parameters are NEVER adjusted using their results.** They
  are predicted once with the config frozen from 2026-only selection.
- **Decision rule:** if the TI2024 and TI2025 outer results CONFLICT, or their sample is
  insufficient, KEEP the frozen B-bt. Do not force-tune for maximum historical score.
- Full multi-year (TI2022/2023) and Phase-2 replay remain out of scope for now.

## 6c. D3 pre-registration (LOCKED 2026-08-03, before any TI24/25 results)
D3 is an OUTER validation with a hard exit rule, not another tuning round. Two TIs are limited
evidence (directional, not a final statistical verdict). All rules below are frozen before scoring;
both events are scored simultaneously (looking at TI2024 then changing anything makes TI2024 a dev set
and only TI2025 remains a true outer test).

**Frozen scope - allowed:** fixed `hl=90` and fixed `hl=180`; one data source; one event filter; one
identity/roster rule set; one lock time per event; predict TI2024 and TI2025 exactly once each.
**Not allowed:** new half-lives (240/365...), new event weights, new roster-decay formulas,
per-event roster patches, or any look-then-modify-then-test-the-other flow.

**Production-switch rule (pre-registered):** change production from `hl=90` to `hl=180` ONLY IF ALL:
1. TI2024 AND TI2025 event-level log-loss are BOTH better than 90;
2. combined log-loss improvement is at least `dLL <= -0.002`;
3. Brier and calibration are not materially worse;
4. no concentrated breakdown on the major-roster-change / stand-in subset;
5. identity verification is clean (no old-org strength wrongly inherited by a new roster).
Otherwise KEEP `hl=90` - including: split result (one TI wins, one loses); both win but tiny;
log-loss better yet calibration clearly worse; improvement driven by a few extreme games; any
unresolved identity/roster doubt. Series accuracy is REPORTED but auxiliary; primary = event-level
log-loss, then Brier, calibration, stability/failure cases. Challenger-to-production: 180 must prove
itself; 90 does not have to re-prove itself.

**Required diagnostics (before the decision):**
- roster-stability subgroups (stable / one change / two-plus / stand-in-or-uncertain), 90 vs 180 each;
- per-team and per-match loss-contribution: the largest 90-vs-180 differences, to confirm a broad
  improvement rather than one or two upsets;
- effective sample size per team under 90 vs 180 (to tell variance-reduction from stale-roster bias).

**Identity discipline (biggest risk, per event, frozen before scoring):** org names; OpenDota team
ids; actual five-player rosters + stand-ins; renames / acquisitions / shell relationships; pre-lock
team affiliation; which history may be inherited and which may not. Prevent: post-hoc roster backfill;
merging same-name-different-org records; a new org inheriting an old org's full strength; a
transferred player's future identity leaking into the past; any TI main-event result entering
training. Deliver a HUMAN-VERIFIABLE identity/roster table per event BEFORE running any scoring.

## 7. Deliverable staging
- **D1 (done):** this plan + event-manifest schema + framework skeleton + runnable Phase-3
  `compare_policies.py`.
- **D2 (in progress, no new data):** pre-registered variant sweep on the 2026 events with nested
  tuning + the Phase-3 A/B/C report; per-event tables + event-blocked bootstrap. Produces the FROZEN
  config, selected on 2026 events only.
- **D3 (approved, new data - TI2024 + TI2025 only):** acquire those two events' pre-lock data +
  as-of-lock rosters; predict each ONCE with the D2-frozen config as an outer held-out test; Phase-2
  replay only if the format is faithfully reconstructable. No re-tuning on TI24/25 outcomes.
- Main-event (14-series) entry stays deferred until the group draw is set.

## 8. Anti-leakage checklist (every run asserts/records)
cutoff timestamp; training set ends < cutoff; rosters as-of-lock; params chosen from earlier events
only; results source; model + data commit; whether the run is a real-format backtest or a synthetic
strategy simulation.
