# Pre-lock research round - results (2026-08-09)

Final high-effort validation round before the TI15 official prediction. Scope per the client
directive: re-verify timing facts; pre-draw rehearsal with draw marginalization; orthogonal model
challengers under strict rolling-origin discipline; decision-layer (solver) study; market snapshot as
an anomaly check only. Data: the frozen universe through 2026-08-01 (8,544 maps); strengths B-bt
half-life 90, side-neutral radiant c = +0.094 at the 2026-08-02 research cutoff. All studies below
are research artifacts; none is an official prediction.

## 1. Timing facts (re-verified, graded)
- Group stage 2026-08-13..16, main event 08-20..23 (Oriental Sports Center, Shanghai). Sources
  consistent; HIGH confidence.
- The official two-pod split and round-1 pairings are NOT published as of 2026-08-09 (Liquipedia
  round 1 = TBD). HIGH confidence.
- Predictions lock at the FIRST group-stage match on 2026-08-13. Best-supported hour: "10am CST"
  (Hotspawn) read as China Standard Time (UTC+8) = **02:00 UTC**. The circulating "15:00 UTC /
  23:00 Beijing" figure is the same sentence parsed as US Central and conflicts with the in-client
  "9 days" countdown observed 2026-08-03. MEDIUM-HIGH confidence; NOT first-hand Valve wording.
  The in-client countdown is the final authority; the official gate still requires an explicit
  timezone-aware cutoff.

## 2. Pre-draw rehearsal (backtest2/pre_draw.py; research dry-run)
Draw-marginal bucket probabilities under three sampled-draw mechanisms (uniform legal split;
strength-banded pods; region-balanced pods - the latter two are sensitivity mechanisms, not official
rules), 12,000 sims each + 40-draw stability study.

Provisional slate (uniform-marginal, data through 2026-08-01, NOT official):

| bucket | teams |
|---|---|
| 4-0 | PARIVISION |
| 4-1 | BetBoom Team, Team Yandex |
| decider_win | Aurora Gaming, Nigma Galaxy, Team Falcons, Team Liquid, Team Spirit |
| decider_loss | GamerLegion, LGD Gaming, Team Resilience, Tundra Esports, Vici Gaming |
| 1-4 | HULIGANI, Xtreme Gaming |
| 0-4 | OG |

- **14/16 slots are identical across all three draw mechanisms.** The only draw-sensitive boundary
  is the pair (BetBoom Team, Team Falcons) trading "4-1" and "decider_win".
- Draw uncertainty is minor: marginal E[correct] 5.26-5.35 across mechanisms; per-draw E[correct]
  range 5.21-5.60; the earlier fixed synthetic draw differs from the uniform marginal on exactly the
  boundary pair.
- Interpretation: the unknown draw contributes little slate risk; the real draw mainly resolves the
  BetBoom/Falcons boundary and refines decider-bucket ordering.

## 3. Model challengers (backtest2/ensemble_study.py) - falsified
Candidate ranking (mechanism / data-support / cost) selected logit-space ensembles as the only
challengers the frozen data supports cleanly. Considered and deferred with reasons: roster-overlap
training weights (current overlap is measured against the FINAL roster - forward-looking for early
folds; needs time-versioned roster snapshots), LAN/event-tier weights (requires hand-labeling all
training leagues; post-hoc risk), patch regimes (no patch data; window underpowered), player-level
priors (a separate rating system).

Ensembles on the frozen v1 out-of-sample predictions (23 events, 1,177 maps; event-weighted
log-loss; event-blocked bootstrap):

| candidate | log-loss | dLL vs B-bt | 95% CI | fold wins | ECE |
|---|--:|--:|--:|--:|--:|
| B-bt (production) | 0.6518 | - | - | - | 0.0971 |
| E-A-elo-50 | 0.6560 | +0.0042 | (+0.0013, +0.0072) | 7/23 | 0.1048 |
| E-B-eloTD-50 | 0.6570 | +0.0052 | (+0.0025, +0.0077) | 6/23 | 0.1064 |
| E-C-glicko2-50 | 0.6592 | +0.0074 | (+0.0010, +0.0172) | 7/23 | 0.1012 |
| E-all4 | 0.6600 | +0.0082 | (+0.0043, +0.0135) | 7/23 | 0.1132 |
| E-adapt (prequential) | 0.6518 | 0.0000 | - | - | 0.0971 |

Every fixed mixture is WORSE than pure B-bt with confidence intervals excluding zero on the harmful
side, and the no-lookahead adaptive selector - free to add any partner at 25/50/75% weight - chose
pure B-bt in ALL 23 folds. Conclusion: the independent models carry no stable complementary
information beyond B-bt on this data. **Production stays frozen B-bt, half-life 90.** (The negative
result is the finding; no challenger reached the promotion gate.)

## 4. Decision layer (backtest2/solver_study.py) - one real, adopted improvement
Optimize-half / evaluate-half protocol (15,000 + 15,000 sims), three draws, paired bootstrap:

| draw | policy | moves vs Hungarian | held-out paired gain |
|---|---|---|--:|
| fixed-synthetic | swap / multi-start / 3-cycle | none | 0.0 |
| uniform-sample-1 | swap | Falcons <-> Yandex (4-1 vs decider_win) | **+18.3 +/- 5.5** |
| uniform-sample-1 | multi-start / 3-cycle | same as swap | +18.3 +/- 5.5 |
| uniform-sample-2 | swap / multi-start / 3-cycle | none | 0.0 |

- The convex points curve can prefer a different resolution of a near-tie boundary pair than
  expected-correct does, worth roughly 15-20 points when it occurs; multi-start and 3-cycle
  neighborhoods added NOTHING over simple pairwise swaps in any draw (all results are local-search
  candidates, not proven global optima).
- **Adopted into production** (ti_predict/predict_ti15.py `points_refinement`): after the Hungarian
  assignment, a swap search on the simulation archive proposes a slate; it is adopted ONLY if an
  independent verification archive (fresh seed) shows a paired gain exceeding two bootstrap standard
  errors; otherwise the Hungarian slate stands. The manifest records proposed moves, the paired gain
  and se, and whether it was adopted. The frozen model is untouched; this is a decision-layer change
  with a quantified, held-out-verified effect and a fail-safe default.

## 5. Market snapshot (anomaly check only; no fusion)
Polymarket, 2026-08-07: Team Vision (PARIVISION) 22%, Team Yandex 22%, Team Falcons 10%, 1w Team 9%,
BoomBoys 9%. Bookmaker consensus (CyberScore): PARIVISION / Yandex / BetBoom strongest.
- Top-of-field ALIGNMENT with B-bt (PARIVISION 1.32 > Yandex 1.10 > Falcons 1.09) is good.
- One material divergence: **1w Team** (market ~4th; our model bottom-half). Most plausible cause is
  the local data gap: the universe ends 2026-08-01 and 1w has been winning at 1W Essence Season 2
  (Aug 1-5), which is not yet in the data. Same applies to OG (current 0-4 pick; also playing that
  event). This is an argument for the mandatory lock-day refresh - already enforced by the official
  freshness gate - not for changing the model.
- No historical timestamped odds backtest exists, so odds remain excluded from production per the
  frozen market-gate decision.

## 6. Engineering notes
- The official/dry-run pipeline now runs three simulation passes (probability archive, verification
  archive, CRN sensitivity), roughly tripling runtime at the same --sims; the default remains
  tractable (minutes).
- New tests: pre-draw pod sampling validity, archive/P consistency, ensemble mixing endpoints, and
  the refinement adopt/reject/no-move rules (37 tests total).

## 7. Decision summary
1. Production model UNCHANGED: identity side-neutral B-bt, half-life 90, no calibration layer.
2. Ensemble challengers falsified with CIs excluding zero; adaptive selector independently chose
   pure B-bt in every fold.
3. Decision layer upgraded: verified expected-points refinement (fail-safe, evidence above).
4. Lock estimate corrected to 2026-08-13T02:00:00Z (10:00 UTC+8), pending in-client confirmation.
5. Remaining external inputs unchanged: posted draw, exact lock time, refreshed universe.
