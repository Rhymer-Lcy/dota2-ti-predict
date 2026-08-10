# Adversarial validation round - results (2026-08-09)

Final adversarial round before the TI15 official prediction: the goal was to REFUTE the previous
round's conclusions, not confirm them. Fact source: git history (commits 8f6be64, dd0184b, fc24c39,
621e50b, 26a284d, d37cca4, ad166ac - contents verified against their diffs). All claim-validation
experiments ran on the frozen 2026-08-01 data snapshot; all fresh archives used seed ranges never
touched by any prior study (777xxx / 888xxx / 999xxx). Modules: backtest2/refine_audit.py,
lambda_study.py, refresh_compare.py, predraw_decompose.py.

## 1. Timing facts - upgraded to Tier-1 evidence
- The lock sentence's ORIGIN is Valve's own blog (2026-07-31, dota2.com/newsentry/678505520073540063):
  guesses must be in "before the first match starts (10am CST, Thursday 8/13)". Lock == first match
  by Valve's construction.
- Valve's TI2026 ticket post demonstrably uses CST = China Standard Time ("2pm China Standard
  Time ... From 2:30pm (CST)"), resolving the abbreviation: **2026-08-13 10:00 UTC+8 = 02:00 UTC**.
- Strafe's "3:00 PM GMT" equals 10:00 US Central Daylight - a misparse of the same Valve sentence
  (it would be 23:00 in Shanghai); Hotspawn copied Valve verbatim. Both trace to one origin; there is
  no second independent measurement.
- The official Chinese localization OMITS the deadline sentence; Valve's league feed carries no
  per-match times yet. Confidence: HIGH but not unambiguous-official; **the in-client countdown
  remains the final authority** and the official gate still requires an explicit timestamp.
- Machine-readable schedule source found: league feed id 19719
  (`.../IDOTA2League/GetLeagueData/v001/?league_id=19719`). It also TIER-1 CONFIRMS the simulator's
  core format: 16-team Swiss, max_rounds=5, win_loss_limit=4, 3 advance + 10 into a 5-match
  elimination round. Draw NOT published as of 2026-08-09 (all round-1 nodes empty); league window
  opens 2026-08-12 00:00 UTC; TI2025's round-1 pairings came ~47 h before its first match
  (announced 2025-09-02, first match 2025-09-04 10:00 CEST).
- Residual format uncertainty: NO machine-readable source mentions the "two initial pods" (that
  detail rests on the in-client rules transcription; the rulebook page is a script shell). Bounded:
  14/16 slots were invariant across pod mechanisms, the 1/2/5/5/2/1 distribution is forced
  regardless, and round 1 becomes exact once posted.

## 2. points_refinement adversarial audit - the headline correction
Process audit (code + git history): the search never touches the verification data (solver_study
split one iid archive by index; production uses disjoint RNG streams seed / seed+424243); the paired
unit (per-simulation points difference) is correct; the 2-sigma threshold predates the +18.3 result;
one seed was run and all three draws were reported (no seed/draw shopping in history). The
promotion itself was, however, motivated by the observed +18.3 - a meta-selection this round was
designed to price.

**Fresh outer validation (experiment `claim`)**: the promoted sample-1 slates were reproduced
deterministically (moves = Team Falcons / Team Yandex, exact match), then evaluated as FIXED slates
on six never-before-used 40k archives:

| fresh archive | paired gain | se |
|---|--:|--:|
| 1..6 | +0.46, +6.33, +4.76, +6.74, +4.93, +12.38 | 3.2 each |

- Combined with an independent 200k ground-truth archive (+7.29 +/- 1.44): **true effect about
  +6.5 +/- 1.0 points** - positive on every fresh archive, but roughly ONE THIRD of the reported
  +18.3 (a winner's-curse-typical high draw, ~2.2 sigma above the true value).
- Direction robust to D4 opponent-choice (noisy +10.4, random +8.5) and radiant-c (0.05: +10.0,
  0.15: +10.4). Mechanism confirmed: trades ~0.006 expected-correct for tail mass (dP(K>=10) ~ +0.003).
- Under strength perturbations (sigma=0.1 on log-strengths) the per-realization gain flips sign in
  3/8 cases (range -21 to +68, mean +20): the correct boundary-pair orientation is conditional on
  the estimated strengths. Since the rule re-runs at the cutoff on refreshed strengths, this is
  model risk, not a rule defect - but it caps how much any boundary swap should be trusted.

**Operating characteristics (experiment `null`, 30 end-to-end replications of the full deployed
pipeline, each scored on a 200k ground truth)**:

| draw | proposals | adoptions | adopted with truth <= 0 |
|---|--:|--:|--:|
| fixed-synthetic | 1/10 | 1/10 | 0 |
| uniform-sample-2 | 2/10 | 1/10 | 0 |
| uniform-sample-1 | 10/10 | 8/10 | 0 |

- **Zero harmful adoptions in 30 runs**; every adopted slate had positive ground-truth gain
  (+2.8 to +8.7). On draws without a strong boundary pair the rule proposes rarely and the gate
  filters further. Note the "null" draws are not exact nulls - small real convexity effects exist
  and the rule correctly found one (+8.7 truth on fixed-synthetic).
- Empirical power on the boundary draw: 8/10 at 40k sims. Winner's curse INSIDE the gate: adopted
  verify-gains averaged ~10.1 vs ground truth ~5.9 (factor ~1.7) - the manifest's recorded gain is
  an optimistic estimate of a genuinely positive effect (documented in the docstring).
- Power analysis: for a true +6.5 effect, the 2-sigma gate has ~51% analytic power at 40k
  (observed 80% because the search may pick the stronger of several boundary moves), ~94% at 120k.
  **Lock-day recommendation: --sims 120000** (runbook updated).

**VERDICT: KEEP in production.** The rule survived independent refutation testing: positive on all
fresh archives, zero observed false adoptions, fail-safe default. The evidence record is CORRECTED
from "+18.3 +/- 5.5" to "about +6.5 +/- 1.0" (docstring and docs updated; the original solver_study
numbers remain in its frozen report as the historical record).

## 3. Solver adequacy (experiment `search`)
On 40k search archives scored against 200k ground truths, simulated annealing (2-swap + 3-cycle,
5 restarts), multi-start-50 and exhaustive 3-cycle all converged to EXACTLY the pairwise-swap
solution on both draws tested (gain vs Hungarian: 0 and +7.3). An exact MILP formulation exists in
principle (17-level indicator variables per simulation) but is impractical at production simulation
counts and unnecessary given zero observed gap beyond the pairwise neighborhood. All results remain
"best found under the specified search procedure" - no global-optimality claim.

## 4. Ensemble negative result - audit passed, conclusion stands
Mechanical verification: 1177 keys x exactly 4 models, identical y per key, weights joinable
1177/1177, correct logit mixing (1e-12), clipping only at 1e-6 extremes (observed p range
0.073..0.844), one shared fold loop and cutoff for all models, event-blocked bootstrap confirmed,
adaptive tie-break favors pure B-bt only on measure-zero exact ties, first 4 folds forced to
baseline (disclosed). No defect found; the negative conclusion stands unchanged.

## 5. New challenger (pre-declared): B-bt ridge shrinkage - FAILS the gate
Admissibility audit first: time-versioned rosters (not admissible - only final-roster overlap
exists; forward-looking), LAN/online labels (subjective post-hoc), patch regimes (no patch field;
direction contradicted by the D2 longer-memory gradient), player priors (separate system). The one
admissible orthogonal candidate: the BT ridge lam (uncertainty shrinkage), grid {0.5, 1, 2, 4},
nested prequential on the frozen snapshot folds:

| lam | 0.5 | 1.0 (frozen) | 2.0 | 4.0 | nested |
|---|--:|--:|--:|--:|--:|
| pooled log-loss | 0.6435 | 0.6518 | 0.6629 | 0.6730 | 0.6465 |

Nested-vs-frozen: -0.0053 pooled but **11/23 fold wins and event-blocked 95% CI (-0.0174, +0.0040)
spanning zero**; lam=0.5 is the grid boundary. Fails the promotion gate on event-consistency and CI
(the same failure pattern as half-life 180: pooled-better, event-inconsistent, boundary-attracted,
in the direction of LESS shrinkage - exactly the overconfidence risk for a fresh TI). **Keep lam=1.**

## 6. Data refresh (through 2026-08-09) - two real pipeline defects found and fixed
The refresh rehearsal (the lock-day procedure, executed early) caught:
1. **Windows console crash**: resolve_identity died on a player name containing a non-codepage
   character (U+2660), killing the chain mid-run. Fixed (stdout reconfigured with errors="replace").
2. **Silent universe truncation**: scan_promatches broke on a transient empty API page after 30
   pages, silently shrinking the universe to 2026-05-17+ (2796 of 8544+ maps) - undetectable by the
   freshness gate (the NEWEST data was fine). Fixed: empty-page retries, incremental merge with the
   existing scan (coverage can never shrink), and a fail-closed exit if the target start date is not
   reached.
After fixes: universe 8690 maps (2026-02-27..2026-08-09), dataset 1239 target maps through 08-05.
**Roster check: all 16 roster_keys unchanged** (the only identity diff is map counts/windows and
LGD's primary source id rotating within its known id set).

Strength shifts (2026-08-02 snapshot -> 2026-08-10 cutoff): OG +0.152, GamerLegion -0.117,
Team Liquid +0.090, BetBoom -0.059, Vici -0.057; ranks: Falcons back above BetBoom (3rd/4th swap),
Tundra/1w 11th -> 9th. Provisional uniform-marginal slate changes on 5 of 16 slots: Falcons <->
BetBoom (the known boundary pair), OG 0-4 -> 1-4, GamerLegion decider_loss -> 0-4, Xtreme 1-4 ->
decider_loss.

## 7. Market diagnostic (three sources, no fusion)
Polymarket (2026-08-09T17:28Z, normalized): Yandex/Vision 21.0% each, Falcons 8.9%, Spirit 7.9%,
BetBoom 7.0%, Liquid 7.0%, 1w 6.1%, Aurora 5.6%, Vici 5.1%, Xtreme 4.0%, LGD 2.0%, Resilience 1.9%,
Nigma 1.3%, OG 0.6%, GamerLegion 0.4%, HULIGANI 0.2%. Cyberscore bookmaker aggregate and esportbet
(stale 07-31) broadly agree on the top cluster. No BO3 match odds exist anywhere yet.
- Spearman rank correlation vs B-bt (8/1 snapshot): **0.865**. Largest divergences: Nigma (model 8,
  market 13), Tundra/1w (model 11, market 7), Xtreme (model 14, market 10).
- After the refresh the divergences SHRINK in the market's direction (1w 11->9, Xtreme 14->13, OG
  and GamerLegion converge to market order) - the disagreement was substantially data-recency, as
  hypothesized. Remaining items flagged for human sanity-check at lock (not model changes): Nigma
  ranked notably higher by the model than the market; Spirit slightly lower.
- No historical timestamped odds backtest exists, so odds stay diagnostic-only per the frozen gate.

## 8. Pre-draw high-precision decomposition (refreshed data, cutoff 2026-08-10T00:00:00Z)
40k-sim uniform marginal (MC se ~0.002 per cell), 60 draws x 1000 sims, 20 event-block bootstrap
strength refits, D4 strategic-vs-random marginals (backtest2/predraw_decompose.py). E[correct] 5.22.

Uncertainty ordering, uniformly across teams: **strength estimation (sd 0.02-0.10) >> draw
(sd 0.013-0.023) >> D4 policy (<0.008) >> MC (0.002)**. The binding uncertainty for every boundary
slot is the strength estimate itself - consistent with the perturbation findings in section 2 - not
the unknown draw. Consequences:
- Draw-independent slots (assigned-vs-second gap >= 0.10, gap >> draw_sd): PARIVISION 4-0 area,
  Spirit / Aurora / BetBoom decider_win, Vici / Xtreme decider_loss.
- Boundary pairs that must wait for the lock-day refit: TOP - Falcons / BetBoom vs Yandex (4-1 vs
  decider_win; flipped once already with the refresh); BOTTOM - **OG vs GamerLegion (0-4 vs 1-4)**,
  now the least stable pair (OG's post-08-01 surge, GamerLegion's slide; assigned slots swapped
  between two independent runs). Nigma decider_win vs decider_loss is the thinnest middle boundary
  (gap -0.03).
- The capacity-forced nature of extreme buckets is visible: several teams occupy extreme slots whose
  own bucket probability is below their decider-bucket probability (negative gaps in the report);
  this is optimal under the constraint, not an error.

## 9. Verdicts (production specification after this round)
| component | verdict |
|---|---|
| Model B-bt half-life 90 | **KEEP** (ensemble falsified on CI; lam challenger failed gate) |
| Calibration none (identity side-neutral, train-only c) | **KEEP** |
| Solver baseline Hungarian | **KEEP** (no gap found beyond pairwise swaps) |
| points_refinement | **KEEP IN PRODUCTION**, evidence corrected to +6.5 +/- 1.0; recorded gain documented as adoption-conditioned (about 1.7x optimistic); official run at 120k sims |
| Pre-draw studies | research only, never auto-promote to official |
| Market | diagnostic only |
| Cutoff | 2026-08-13T02:00:00Z; Tier-1 wording + Tier-1 timezone convention; in-client countdown final |

Residual assumptions unchanged (C5 pairing sampling, D4 strategic primary, duration tiebreaker in
the coin-toss tail, two-pod detail from the in-client transcription only).
