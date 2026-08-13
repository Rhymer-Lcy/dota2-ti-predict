# dota2-ti-predict

Model-driven picks for the **Dota 2 The International 2026 in-game Predictions contest**
(a free, skill-based prediction game for cosmetic rewards — **not gambling**: no stake, no money
at risk). Goal: place in the top reward tier of the global leaderboard.

Method reuses the calibrated-probability approach from the archived soccer `odds-pipeline`
(market de-vig via Shin, cross-checked by an independent model), adapted to esports series.

## Status (2026-08-12) — **GROUP STAGE LOCKED**; Fantasy period 0 operationally set
- **Contest rules: verified** (official Valve in-client TI15 activity, not a third-party game). The
  group prediction is a full **16-slot classification** — 4-0 x1, 4-1 x2, decider-win x5,
  decider-loss x5, 1-4 x2, 0-4 x1 — scored by number correct (convex `f(K)`, no penalty, no underdog
  weighting, **no crowd% shown**). Group predictions lock at the **first group-stage match,
  2026-08-13 02:00 UTC = 10:00 UTC+8** — now Tier-1 confirmed by the league feed's own
  `scheduled_time` on every round-1 node, not just by the blog wording (the in-client countdown stays
  the final check). Full write-up: [`docs/contest-official-ti15.md`](docs/contest-official-ti15.md).
- **Field: confirmed 16** in [`data/ti2026/inputs/teams.csv`](data/ti2026/inputs/teams.csv), matching
  the official field (BetBoom/BoomBoys, PARIVISION/TEAM VISION, Tundra roster/**IRON WING** — note `teams.csv` still carries the stale `ti_alias` `1w Team`; the field is display-only and never enters strength estimation).
- **Locked slate:** `predictions/ti2026/group-stage/ti15_group_prediction.json` (mode `official`, clean tree, 280000 sims over 35 pod memberships, E[correct] 5.249). The lock-day audit found **no material input change**: all four input fingerprints identical to the 2026-08-10 candidate and every bucket unchanged. Full state: [`docs/CHECKPOINT.md`](docs/CHECKPOINT.md).
- **Fantasy period 0:** operationally set on both accounts, latest observed states `predictions/ti2026/fantasy/account_state_operator_20260812b.json` (Xtreme / Team Falcons / Xtreme, 10 tokens) and `..._target_20260812d.json` (Xtreme / Team Yandex / Xtreme, 6 tokens); Coach Elemental + the Tormented on both. `coach_pricing_20260812.json` was computed on the friend's previous banner and must be re-run against state 7 before reuse.
- **Model: FROZEN.** Production = identity **side-neutral B-bt**, half-life **90**, map prob
  `0.5*(sigmoid(d+c)+sigmoid(d-c))` with train-only radiant `c`; **no Platt/temperature layer**.
  Selected via event-frozen rolling backtest (B-bt beats plain Elo **17/23** folds). The D2 nested
  half-life sweep found **no significant** out-of-sample gain over 90, so hl stays 90; the
  TI2024/TI2025 outer validation (D3) is archived on cost grounds. See
  [`docs/validation-plan-v2.md`](docs/validation-plan-v2.md).
- **Group-stage simulator + solver: built and tested.**
  [`ti_predict/swiss.py`](ti_predict/swiss.py) (rules-based Swiss + decider round; the structural
  invariant 1/2/5/5/2/1 is asserted on every run) and [`ti_predict/assign.py`](ti_predict/assign.py)
  (Hungarian max-expected-correct). The C5 pairing, D4 opponent-choice and avg-duration tiebreak
  assumptions are documented and sensitivity-checked — **not** claimed as an exact replica of the
  organizer's unpublished pairing decisions.
- **End-to-end entry: [`ti_predict/predict_ti15.py`](ti_predict/predict_ti15.py), hard-gated.**
  `--dry-run` rehearses on synthetic/historical inputs (writes `.dryrun/`, labeled NOT OFFICIAL);
  `--official` refuses unless the posted round-1 pairings, a **confirmed** pairing structure, a
  frozen `--cutoff`, B-bt strengths and a clean roster audit are all present. Emits JSON (fact
  source) + Markdown + a full run manifest.
- **Round 1 is posted** (Valve league feed, ingested by
  [`ti_predict/league_feed.py`](ti_predict/league_feed.py) into `data/ti2026/inputs/draw.json`). The
  **two-pod structure is an official rule**; what is unpublished is the pod **membership**, so an
  official run marginalizes over all 35 memberships compatible with round 1 and records that in the
  manifest. Measured effect of that uncertainty:
  [`backtest2/post_r1.py`](backtest2/post_r1.py) finds the same 16 slots across every membership,
  with at most 0.0056 per-cell probability difference against the no-pod comparator.
- **One lock-period roster change:** LGD position 2 (TaiLung banned -> Topson), recorded with full
  provenance in `data/ti2026/inputs/roster_events.csv`; the other 15 lineups are confirmed unchanged.
- **No OFFICIAL TI2026 slate emitted yet.** It is produced at the cutoff — follow
  [`docs/lockday-runbook.md`](docs/lockday-runbook.md).
- **Independent Fantasy / Compendium track: PHASE 1 BLOCKED.** The shipped client exhaustively
  enumerates 30 Predictions slots and two Fantasy periods, but Fantasy runtime coefficients,
  configurable emblem counts, dropdown restrictions and countdowns still require live-client
  captures. No Fantasy candidate is emitted while that gate is open. See
  [`docs/fantasy-runbook.md`](docs/fantasy-runbook.md).

## Strategy note
Scoring is by **number correct** with a **convex** points curve, **no underdog weighting, no penalty,
and no crowd pick-share** shown in the client. The base slate **maximizes expected correct**
([`ti_predict/assign.py`](ti_predict/assign.py)); because the points curve is convex, the pipeline
then applies a **verified expected-points refinement** — a swap search may adjust a near-tie boundary
pair, adopted only when an independent verification archive confirms the paired gain beyond noise
(evidence: [`backtest2/results-prelock-research.md`](backtest2/results-prelock-research.md)). A
challenger round (ensembles with Elo / EloTD / Glicko-2) was **falsified out-of-sample**, so the
frozen B-bt stands on evidence. There is **no anti-crowd / contrarian layer** because the client
exposes no pick-share to differentiate against. The separate main-event and Fantasy sub-games now
live behind their own independent readiness gate; they do not re-open or re-tune this frozen
group-stage model.

## Layout
```
docs/            write-ups: official contest rules, validation plan, lock-day runbook, research log
ti_predict/      package: swiss.py (group-stage sim), assign.py (16-slot solver),
                 predict_ti15.py (gated entry), fantasy/questions.py (inventory readiness gate),
                 series.py / devig.py (reused), backtest/calibrate
backtest2/       historical rolling-origin validation framework (plan, manifests, Phase-3 compare)
data/            gitignored except inputs/ — see data/README.md
  ti2026/
    inputs/      hand-entered, small, TRACKED: teams.csv, prediction_questions.json,
                 fantasy/fantasy_rules.json (+ odds/questions screenshots→csv)
    raw/         OpenDota pulls etc. (gitignored, regenerable)
    processed/   cleaned tables / rating snapshots (gitignored)
predictions/     our published picks, TRACKED — see predictions/README.md
  ti2026/
    group-stage/ Swiss predictions
    playoffs/    bracket predictions
```

## Run
```
pip install -r requirements.txt
python -m ti_predict.swiss                 # simulator self-test (structural invariants)
python -m ti_predict.assign                # solver self-test (synthetic)
python -m ti_predict.predict_ti15 --dry-run   # end-to-end rehearsal (writes .dryrun/, NOT OFFICIAL)
```
The official slate is produced only at the cutoff via `predict_ti15 --official` — see
[`docs/lockday-runbook.md`](docs/lockday-runbook.md). OpenDota needs no key; STRATZ token (optional)
goes in `.env.local` (copy `.env.template`).

Commit messages follow Conventional Commits with a **subject <=72 chars, pure ASCII**, enforced by
a hook (no manual checking). Install it once per clone:

```
cp scripts/git-hooks/commit-msg .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
```

## Data & hygiene
See [`docs/data-sources.md`](docs/data-sources.md). OpenDota is the free primary source; there is
**no reliable free odds API** (odds come from screenshots). Never commit tokens or paid-odds data.

## Provenance
All research claims are dated and cited in [`docs/research-log.md`](docs/research-log.md), tagged
confirmed / probable / TBD. Re-verify **TBD** items against the official client once the draw and
main-event bracket are posted.
