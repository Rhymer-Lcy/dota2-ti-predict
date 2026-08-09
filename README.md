# dota2-ti-predict

Model-driven picks for the **Dota 2 The International 2026 in-game Predictions contest**
(a free, skill-based prediction game for cosmetic rewards — **not gambling**: no stake, no money
at risk). Goal: place in the top reward tier of the global leaderboard.

Method reuses the calibrated-probability approach from the archived soccer `odds-pipeline`
(market de-vig via Shin, cross-checked by an independent model), adapted to esports series.

## Status (2026-08-09) — pipeline built, validated, gated; awaiting the group draw
- **Contest rules: verified** (official Valve in-client TI15 activity, not a third-party game). The
  group prediction is a full **16-slot classification** — 4-0 x1, 4-1 x2, decider-win x5,
  decider-loss x5, 1-4 x2, 0-4 x1 — scored by number correct (convex `f(K)`, no penalty, no underdog
  weighting, **no crowd% shown**). Group predictions lock at the **first group-stage match,
  ~2026-08-13 10:00 UTC+8 = 02:00 UTC** (best-supported estimate; the in-client countdown is the
  final authority). Full write-up: [`docs/contest-official-ti15.md`](docs/contest-official-ti15.md).
- **Field: confirmed 16** in [`data/ti2026/inputs/teams.csv`](data/ti2026/inputs/teams.csv), matching
  the official field (BetBoom/BoomBoys, PARIVISION/Team Vision, Tundra roster → 1w Team, etc.).
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
  `--official` refuses unless the posted draw (validated two-pod partition **and** round-1 pairings),
  a frozen `--cutoff`, and B-bt strengths are all present. Emits JSON (fact source) + Markdown + a
  full run manifest.
- **No TI2026 probabilities emitted yet.** The official slate is produced at the cutoff from the
  posted draw — follow [`docs/lockday-runbook.md`](docs/lockday-runbook.md).

## Strategy note
Scoring is by **number correct** with a **convex** points curve, **no underdog weighting, no penalty,
and no crowd pick-share** shown in the client. The base slate **maximizes expected correct**
([`ti_predict/assign.py`](ti_predict/assign.py)); because the points curve is convex, the pipeline
then applies a **verified expected-points refinement** — a swap search may adjust a near-tie boundary
pair, adopted only when an independent verification archive confirms the paired gain beyond noise
(evidence: [`backtest2/results-prelock-research.md`](backtest2/results-prelock-research.md)). A
challenger round (ensembles with Elo / EloTD / Glicko-2) was **falsified out-of-sample**, so the
frozen B-bt stands on evidence. There is **no anti-crowd / contrarian layer** because the client
exposes no pick-share to differentiate against. The higher reward tiers (top-100 / top-1500 /
percentile) also depend on the separate main-event and Fantasy sub-games, which are out of scope for
now.

## Layout
```
docs/            write-ups: official contest rules, validation plan, lock-day runbook, research log
ti_predict/      package: swiss.py (group-stage sim), assign.py (16-slot solver),
                 predict_ti15.py (gated entry), series.py / devig.py (reused), backtest/calibrate
backtest2/       historical rolling-origin validation framework (plan, manifests, Phase-3 compare)
data/            gitignored except inputs/ — see data/README.md
  ti2026/
    inputs/      hand-entered, small, TRACKED: teams.csv (+ odds/questions screenshots→csv)
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
