# TI 2026 Project Postmortem

**Status: closed.** Everything below is derived from tracked artifacts. Numbers come from
[`predictions/ti2026/postmortem/ti2026_postmortem.json`](../predictions/ti2026/postmortem/ti2026_postmortem.json)
and its companions; this document explains them and does not restate anything it cannot point at.

The chronology rule that governs the whole archive: **pre-event artifacts are immutable historical
evidence, post-event truth lives in its own namespace, and post-event truth is never an input to the
2026 production run.** That separation is enforced by
[`ti_predict/chronology.py`](../ti_predict/chronology.py), not just asserted here.

---

## Executive Summary

| | |
|---|---|
| Actual champion | **Team Spirit** (3-2 over TEAM VISION / PARIVISION, 2026-08-23) |
| Predicted champion | **PARIVISION**, pre-event title probability **0.348** |
| Actual champion's pre-event probability | **0.0793** (90% bootstrap CI 0.0218-0.1696), ranked 5th of 8 |
| Official in-client settlement | **8 correct / 6 incorrect of 14**, **4320 points** |
| Pre-event expectation | **5.109** expected correct, **2288.5** expected score |
| Model's own P(>= 8 correct) | **0.195** |

Eight of fourteen against an expectation of five is a good result, and it is one draw from a
distribution the model itself published in advance: it gave this outcome or better about a one-in-five
chance. That is the honest frame. It is not evidence of calibration, and it is not a reason to change
anything. **N = 1.**

The result worth keeping is different and firmer: **the objective was specified correctly.** The
production optimiser maximised expected official score under node-winner semantics, and the client's
own settlement credits exactly the nodes that functional predicts it would - in aggregate and at all
fourteen nodes individually. Sixteen thousand slates were ranked by the right thing.

---

## Frozen Pre-Event System

| | |
|---|---|
| Model | side-neutral Bradley-Terry (B-bt), half-life 90 days, ridge lambda = 1, no calibration layer |
| Map probability | `0.5 * (sigmoid(d + c) + sigmoid(d - c))`, train-only radiant `c` = 0.0940 |
| Weighting | 1/series_size, so one Bo3 contributes total weight 1.0 |
| Cutoff | 2026-08-16T12:00:00Z, after the last Elimination Round map and before the run |
| Training maps | 8,799 |
| Optimisation | all 16,384 coherent slates scored against all 16,384 outcomes - **exact**, not sampled |
| Uncertainty | 1,000 series-blocked bootstrap draws, fixed seed |
| Leakage declarations | `network_used=false`, `odds_used=false`, `future_main_event_results_used=false` |

A coherent 14-slot slate *is* one of the 2^14 bracket outcomes, so the candidate set and the outcome
space are the same object. That is why the optimisation is exact rather than a search. And because
expected score is linear in the outcome distribution, averaging the distribution over bootstrap draws
and then optimising is exact too, not an approximation of an average.

---

## Actual Main Event

Reconstructed in [`data/ti2026/outcomes/main_event_results.json`](../data/ti2026/outcomes/main_event_results.json).
Node assignment is **derived, not transcribed**: the fourteen retrieved records are treated as an
unordered bag, the archived opening seating fixes the four seeded nodes, and the verified Valve-feed
graph propagates winners and losers forward. A missing or incoherent record fails the build.

| Sel | Round | Result | Start (UTC) |
|---|---|---|---|
| 801 | UBQF | Team Spirit 2-0 Tundra Esports | 2026-08-20T02:30Z |
| 802 | UBQF | PARIVISION 2-1 BetBoom Team | 2026-08-20T05:45Z |
| 803 | UBQF | Team Yandex 2-0 Team Liquid | 2026-08-20T10:30Z |
| 804 | UBQF | **Nigma Galaxy 2-1 Team Falcons** | 2026-08-20T13:20Z |
| 809 | LBR1 | BetBoom Team 2-1 Tundra Esports | 2026-08-21T02:00Z |
| 810 | LBR1 | Team Liquid 2-1 Team Falcons | 2026-08-21T06:15Z |
| 805 | UBSF | PARIVISION 2-1 Team Spirit | 2026-08-21T10:20Z |
| 806 | UBSF | Team Yandex 2-1 Nigma Galaxy | 2026-08-21T14:10Z |
| 812 | LBR2 | Team Spirit 2-0 Team Liquid | 2026-08-22T02:00Z |
| 811 | LBR2 | BetBoom Team 2-1 Nigma Galaxy | 2026-08-22T05:00Z |
| 807 | UBF | PARIVISION 2-1 Team Yandex | 2026-08-22T08:45Z |
| 813 | LBSF | **Team Spirit 2-0 BetBoom Team** | 2026-08-22T13:10Z |
| 814 | LBF | Team Spirit 2-0 Team Yandex | 2026-08-23T02:10Z |
| 808 | GF | **Team Spirit 3-2 PARIVISION** | 2026-08-23T06:15Z |

Team Spirit lost the upper-bracket semifinal to PARIVISION, then won three straight lower-bracket
series 2-0 without dropping a map, and took the Grand Final rematch 3-2. The model priced the four
series it won after that loss at 0.510, 0.447, 0.437 and 0.275 — a product of **0.016** for exactly
that route. A route that long is improbable for anyone, including the favourite; the model still gave
Team Spirit **0.079** across all routes.

**Sources.** Three, recorded with retrieval times and content hashes in
[`data/ti2026/outcomes/sources.json`](../data/ti2026/outcomes/sources.json): the tier-1 in-client
settlement capture (winners only), Liquipedia's match database (tier 2, participants, scores, times)
and an independent results site (tier 3). All fourteen scores agree between the two independent
result sources, and all fourteen winners agree with the client capture. One news summary reported
best-of-5 scores and was rejected; the archive asserts structurally that each winner's map count
clinches the node's declared best-of, so that source could not have entered silently.

---

## Official Prediction Result

**8 correct, 6 incorrect, 4320 points.** Recomputed node by node from the committed slate and the
committed 15-entry scoring vector - never copied from the client - then cross-checked against the
first-party settlement, which is a hard gate: a mismatch aborts.

> A note on provenance, because it matters more than the number. The capture displays the **8/14
> count** and a per-node check or cross on every node. It does **not** display a points figure for
> this track. **4320 is derived** - it is entry 8 of the committed scoring vector - and the evidence
> index records that explicitly rather than claiming it was seen. The number is right; its
> provenance is derivation, not transcription.

The client also settles the group-stage track at **6 of 16**, against a pre-event expectation of
5.249. Recorded for completeness; the same N = 1 caveat applies with even less force at one draw.

---

## Path-Aware Error Decomposition

The client credits a node when the team you selected there won that node's **realized** series. It
does not require the participants to be the ones you predicted. So two different things can go wrong
and they must not be added together.

| Classification | Count | Selections |
|---|---:|---|
| Credited, participants exactly as predicted | 5 | 801, 802, 803, 805, 809 |
| **Credited despite a diverged path** | 3 | 807, 811, 812 |
| **Wrong, participants as predicted - a root local miss** | 2 | 804, 813 |
| Wrong, pick did play, but against a substituted opponent | 1 | 808 (GF) |
| **Wrong, pick was not even one of the two teams playing** | 3 | 806, 810, 814 |

**Only two of the six misses were genuine local winner errors.** Team Falcons losing to Nigma Galaxy
at 804, and BetBoom Team losing to Team Spirit at 813. Both were nodes where the bracket delivered
exactly the matchup forecast and the model called the wrong side.

**Those two misses generated everything else.** 804 changed who dropped into the lower bracket and
who advanced, which is why the selected team was not even present at 806, 810 and 814. 813 changed
who reached the lower-bracket final, which - together with 804 - is why the Grand Final was played
against Team Spirit rather than Team Falcons. Counting all six as model errors would triple the
apparent local error rate.

Conversely, three nodes were **credited despite** a diverged path: at 807, 811 and 812 the selected
team reached the node by a route the model had not forecast and won anyway. Node-winner scoring is
substantially more forgiving than exact-path scoring, which is worth knowing *before* choosing an
objective.

**Diagnostic, not a score:** under a hypothetical stricter rule requiring both the participant pair
and the winner, the slate would score **5 of 14**. That is a measure of path error and nothing else.
It is not official accuracy and it is not evidence of a specification mismatch.

### Selection 810 - closing the tie correctly

The pre-event work spent real effort on 810. The two candidates differed by **0.39** expected points
out of ~2288, and a 40,000-draw paired bootstrap could not resolve the sign (95% interval about
[-127, +121], P(delta > 0) = 0.5111). The production rule takes the numerical argmax, so Nigma Galaxy
was submitted, and the artifact recorded that this was a **tie**, not a demonstration that Nigma was
better.

What actually happened at that node: **Team Liquid 2-1 Team Falcons.**

The series analysed was Nigma Galaxy versus Team Liquid. It was never played. Nigma Galaxy won its
upper-bracket quarterfinal, so Team Falcons dropped into that slot instead. The tie analysis was
conditional on a path that did not occur, and a conditional analysis of a matchup that never happens
cannot be scored as a forecast of the matchup that did.

> **PICK UNCERTAINTY IS NOT PATH UNCERTAINTY.** This is the single most transferable lesson of the
> 2026 bracket work and it is a required item in the 2027 protocol.

---

## Probabilistic Performance

Every actually-played series scored against the **frozen pre-event serve state**, conditional on the
participants that actually played. No Main Event result updates the strengths. These are **point
estimates**, not the bootstrap-averaged objects the optimiser maximised, and the two are not
interchangeable.

| Metric | Frozen model | Uninformed baseline (p = 0.5) |
|---|---:|---:|
| Mean Brier | **0.2366** | 0.2500 |
| Mean log loss | **0.6679** | 0.6931 |
| Favourite accuracy | **9 / 14 (0.643)** | - |
| Mean probability on the actual winner | **0.5269** | 0.5000 |

Better than a coin flip on both proper scores, by a margin that fourteen correlated series cannot
distinguish from noise. Five realized winners were priced below 0.5; only one below 0.35 - the Grand
Final, where the model put **0.2747** on Team Spirit, the lowest probability it assigned to any
realized winner.

The eventual champion's pre-event title probability was **0.0793** (90% CI 0.0218-0.1696), fifth of
eight. The pre-event favourite, PARIVISION at **0.348**, finished runner-up. **An 8% event occurring
is not a contradiction.** Roughly one TI in twelve should be won by a team the model prices there.

**No calibration claim is made or supported.** Fourteen series, heavily overlapping teams, one
tournament.

---

## Optimiser Retrospective

**The scoring functional was specification-consistent with the client.** This is the strongest
positive result in the archive: the objective 16,384 slates were ranked by is the objective the
client actually pays, verified against first-party settlement at every node.

Only comparators the production run had already recorded are scored. No ex-post strategy search.

| Comparator | Pre-event E[score] | Realized | Points |
|---|---:|---:|---:|
| **max E[official score] (submitted)** | 2288.5 | 8 / 14 | **4320** |
| max E[correct] (also the recorded runner-up) | 2288.1 | 9 / 14 | 5400 |
| greedy coherent favourite | 2222.2 | 8 / 14 | 4320 |
| best slate with a different champion | 2132.5 | 8 / 14 | 4320 |
| point-estimate optimum | (identical slate) | 8 / 14 | 4320 |
| oracle: the realized bracket | - | 14 / 14 | 12000 |

Among all 16,384 coherent slates, the submitted slate's realized score of 4320 had **435 strictly
above it and 529 tied** - rank interval [436, 964], percentile band 94.1-97.3. Realized score is a
coarse integer scale, so a unique rank does not exist and is not invented.

**The runner-up beat the submitted slate by 1080 points, and that changes nothing.** The two slates
differ at exactly one node - selection 810 - and their expected scores differed by 0.39 out of 2288.
One realization cannot rank two strategies separated by noise. The 2027 objective is not being
changed on this.

---

## High-Leverage Misses

1. **804, Nigma Galaxy 2-1 Team Falcons** (model gave Falcons 0.609). The single most consequential
   node on the board: it directly cost one selection and indirectly cost three more through path
   propagation, and it removed the model's second-ranked team in the quarterfinals.
2. **808, the Grand Final** (model gave Team Spirit 0.2747). The largest single probabilistic miss.
3. **813, Team Spirit 2-0 BetBoom Team** (model gave BetBoom 0.553, near a coin flip). A root local
   miss that redirected the lower-bracket final and the Grand Final opponent.

---

## Fantasy Closure

**SEALED.** Reroll optimisation, banner construction, title search and model selection are not
reopened, and were not reopened to write this. Full record:
[`predictions/ti2026/postmortem/fantasy_closure.json`](../predictions/ti2026/postmortem/fantasy_closure.json).

Final review verdict: **PASS_WITH_MATERIAL_UNCERTAINTY.** On observed data the two deployed
configurations came out at account A 73,679.8 and account B 76,934.1, a difference of **+3,254.3** to
B, reconciled under one estimator as banner/emblem +2,388, coach title +590, team deployment +276.
Roles split A / B / B across core, mid and support.

The uncertainty semantics are the part that must survive verbatim:

> A statistic excluded from the observed-data estimator contributes **0 to that estimator by
> exclusion**. Its **true contribution is UNKNOWN, not zero.**
>
> `delta_full(B - A) = +3254.3 + U_B_madstone + U_B_watchers - U_A_madstone - U_A_lotuses`
>
> Necessary condition for A to overturn B: `U_A_madstone + U_A_lotuses > 3254.3`, derived from the
> official coefficient signs alone. It is necessary, not sufficient. **No finite upper bound exists
> in the verified mechanics**, so the flip is quantified and cannot be excluded.

Two claims were withdrawn during the review and must not return: the points-per-multiplier-unit
proxy for unobservable statistics, and the "First Blood <= 1/10 for an individual" bound.

**Realized Fantasy outcome: `OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED`.** No first-party settlement of a
Fantasy period score was captured. The post-event capture is the *Predictions* page. The account's
overall event points and percentile in that capture are **not** a Fantasy score and must never be read
as one, and no reconstruction was attempted from public statistics while three official statistics
remain unobservable.

---

## Evidence / Privacy Architecture

Raw Dota 2 client captures are load-bearing evidence and personally identifying at the same time. The
architecture separates those two facts:

- **Canonical raw storage is a private archive outside the repository**, holding the three captures
  under `ti2026/{pre_event,post_event}/` plus a private manifest.
- **The repository publishes a commitment, not the image**:
  [`data/ti2026/evidence/private_evidence_index.json`](../data/ti2026/evidence/private_evidence_index.json)
  carries each capture's sha256, dimensions, phase, source tier and a privacy-safe transcription of
  only the facts the project uses. The hash pins exactly which bytes were read, so a reviewer handed
  the private file can verify it is the one transcribed - without it ever being published.
- **`evidence_local/` is a git-ignored ingress** for new captures before they move to the private
  archive. The ignore rule is deliberately narrow (`/evidence_local/`), not a blanket image ignore,
  because the one published privacy-preserving crop under `data/ti2026/inputs/` must stay tracked: a
  frozen production gate hashes it.
- **Every rename and move was proved byte-preserving**: sha256 before, sha256 after, both recorded.

The declared trust boundary is unchanged: the hash proves an image has not changed since it was read.
It does not prove the reading was correct.

**One open privacy item.** Seven tracked pre-event Fantasy state files carry the friend account's
client display name inside a rendered `compendium_player_title` string. They were committed and
pushed long before this phase. Both remedies are out of scope here - editing them mutates frozen
pre-event evidence, and removing them means rewriting a published branch, which cannot recall
existing clones or forks. The exposure is therefore **registered** (INC-19) with an exact file list
and enforced by a test that fails if it ever spreads to a new file. **It needs an operator decision.**

---

## Engineering Incidents and Corrections

Nineteen incidents are recorded in full - symptom, root cause, whether a submitted decision depended
on it, fix, prevention and the check that should catch it next time - in
[`ti_predict/ti2026_record.py`](../ti_predict/ti2026_record.py) and the postmortem JSON. The ones
that changed how the project works:

- **INC-04, side provenance.** Synthetic result rows were oriented winner-first, so 88 of 109 had
  `team_a` winning by construction; the side estimator read that as a Radiant advantage and inflated
  `c` to 0.1056. Corrected to 0.0940. Zero change to any strength, zero change to the slate - a real
  bug whose numerical effect happened to be nil. Every row now declares its side provenance and the
  estimator fails closed on an unmarked one.
- **INC-01/02, seating provenance.** The opening pairings had no verifiable local source, because the
  saved Valve feed carries the graph but no team ids in its Playoff nodes. Closed with a hashed
  first-party capture, with seating and topology kept as two separate artifacts answering two
  separate questions.
- **INC-05/06, claims stronger than their evidence.** A diagnostic was described as a
  group-to-playoff replay it could not be, and a candidate set was called preregistered with no prior
  artifact. Both downgraded to what the evidence supports.
- **INC-11/13, Fantasy observability.** Three official statistics turned out to be unobservable, and
  the first response was to fill the gap with an aggregate ratio used as a rate. Withdrawn. The terms
  are now symbolic and unbounded. **UNKNOWN is a valid value.**
- **INC-16, a fact remembered as observed.** The archival brief stated the settlement capture shows
  "+4320". It does not; 4320 is derived. The conclusion is unchanged and the provenance is now
  recorded correctly. *Look at the artifact again before recording that you saw something in it.*
- **INC-17/18, structural checks caught two real errors during archival.** A secondary source
  reported best-of-5 scores (rejected by the clinch assertion), and the first node-assignment attempt
  failed because PARIVISION and Team Spirit played twice - the participant pair is not a unique key
  for a bracket node.

---

## What Worked

- **The objective.** Validated against first-party settlement. This is the result to carry forward.
- **The freeze held.** Model, half-life, lambda and scoring form were fixed before current-event data
  arrived and never reopened; the artifact asserts pipeline identity against the earlier locked run,
  so the freeze is checked rather than promised.
- **No leakage.** No odds, market probability, crowd pick or future result entered at any point, and
  the production declarations remain true and unmodified.
- **Exact enumeration.** Candidate set = outcome space, so the optimisation is exact.
- **Series-blocked resampling.** A Bo3 could never masquerade as three independent observations.
- **Fail-closed gates.** Topology from the saved feed, seating from a hashed capture; either failing
  aborts the run.
- **Independent audit.** Six scoped audits, each finding a real defect - two of them correctness
  issues no test was catching.
- **Ties named as ties.** 810 was priced, named, and submitted by rule. It lost, and that is what a
  tie losing looks like.
- **Immutable artifacts.** The submitted slate is byte-identical to what it was before this
  postmortem, and a test asserts it.

---

## What TI2026 does NOT prove

- One tournament does not validate calibration. Fourteen correlated series cannot distinguish a
  well-calibrated model from a poorly calibrated one.
- **8 correct against ~5.1 expected does not show future outperformance.** The model's own pre-event
  distribution gave a 19.5% chance of scoring at least this well; the result sits inside the forecast.
- **4320 against ~2288 does not justify retuning.** Expected score is an average over the distribution
  this was drawn from.
- **Team Spirit winning does not justify a shorter half-life or a form coefficient.** A team priced
  fifth of eight won. That is what a 7.9% event looks like when it happens.
- **The post-hoc sequential-assimilation diagnostic does not validate sequential assimilation.**
  Chosen after the outcome, scored on 14 non-independent series, no honest interval available.
- Unknown Fantasy statistics must never be silently treated as zero, and an absence of public data is
  not an event-rate estimate.
- **One year's scoring semantics do not carry to the next.** The 2027 client must be re-verified
  before its objective is optimised, however stable the format looks.
- The optimiser comparators cannot be ranked on this realization: 1080 realized points separated two
  slates whose expected scores differed by 0.39.

### The one diagnostic that is suggestive, and stays a question

A post-hoc arm re-fit the frozen estimator - unchanged half-life, lambda and form, only the cutoff and
training set moving - as the Main Event unfolded
([`sequential_posthoc.json`](../predictions/ti2026/postmortem/sequential_posthoc.json)):

| Arm | Brier | Log loss |
|---|---:|---:|
| A frozen production | 0.2366 | 0.6679 |
| B decay-origin control (cutoff moves, no results added) | 0.2366 | 0.6677 |
| C sequentially assimilated | **0.2262** | **0.6450** |

Arm B exists so that an A-to-C difference cannot be attributed to information when it is really the
decay origin moving; it shows the decay shift does essentially nothing, so the small improvement in C
is the new results. Favourite accuracy is identical across all three arms - no call flipped side.

**This is a research question for 2027, not a change.** It was chosen after the outcome, on fourteen
non-independent series, and it cannot promote itself. The next step if pursued is to pre-register the
arm, the metric and the decision rule, then test on events that were not used to design it.

---

## TI2027 Action Items

Full operational checklist: [`docs/TI2027_REUSE_PROTOCOL.md`](TI2027_REUSE_PROTOCOL.md). The items
that exist because of something 2026 got wrong:

1. **Verify the scoring functional against the client before optimising it.** 2026 got this right and
   only learned afterwards how much rode on it.
2. **Capture and hash client rule evidence early** - scoring vector, semantics, topology, seating,
   Fantasy coefficients, lock timing - before prediction work becomes urgent.
3. **Record an observed start time for every current-event series.** 2026 imputed most of them.
4. **Require explicit side provenance on every observation** used for side-bias estimation.
5. **Build the Fantasy observability matrix before any Fantasy optimisation.** Unknown is not zero.
6. **Treat path uncertainty as distinct from pick uncertainty** in every bracket analysis.
7. **Keep post-event truth behind the chronology guard**, and ingest a finished year as history only
   through the next season's own pipeline.
8. **Strip account-identifying strings at capture time**, not at archival time (INC-19).

---

## Reproducing this

```
python -m ti_predict.postmortem                        # evaluation + machine-readable postmortem
python -m ti_predict.postmortem --refit-frozen-state   # frozen serve state (needs the local universe)
python -m ti_predict.postmortem --sequential-diagnostic # post-hoc only (needs the local universe)
python -m pytest tests/test_postmortem.py -q
```

The evaluation is deterministic and offline, and a test asserts the filed artifacts match a fresh run.
