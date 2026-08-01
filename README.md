# dota2-ti-predict

Model-driven picks for the **Dota 2 The International 2026 in-game Predictions contest**
(a free, skill-based prediction game for cosmetic rewards — **not gambling**: no stake, no money
at risk). Goal: place in the top reward tier of the global leaderboard.

Method reuses the calibrated-probability approach from the archived soccer `odds-pipeline`
(market de-vig via Shin, cross-checked by an independent model), adapted to esports series.

## Status (2026-08-01) — modeling track PARKED, awaiting screenshots
- **Research: done & reconciled against the official Dota 2 blog (2026-07-31).** Event, 16-team
  field (with TI gambling-brand renames — BetBoom→BoomBoys, PARIVISION→Team Vision), format
  (**5-round Swiss Bo3: 4W direct / 4L out / 10→special-elim 5-5 → 8-team main event**), contest
  mechanics, and data sources are in [`docs/`](docs/). TI 2026 is in **Shanghai, group stage
  08-13→16, playoffs 08-20→23**; group-stage predictions **lock 2026-08-13 10:00 CST**.
- **Reusable code: ready.** Sport-agnostic de-vig ([`ti_predict/devig.py`](ti_predict/devig.py))
  and esports series math ([`ti_predict/series.py`](ti_predict/series.py), self-tested).
- **Blocked on inputs (from the friend's client / a screenshot):**
  1. exact prediction questions + per-question points;
  2. the FULL reward-tier ladder + per-question points (in-client only; the official blog confirms
     only the **top-100 = all rewards** tier, and has **no "top 5%"** — see
     [`docs/predictions-contest.md`](docs/predictions-contest.md) for the reality-check);
  3. public pick % per option, if shown (the differentiation signal);
  4. the Swiss draw/seeding once posted.
- **Model: SELECTED & FROZEN (spec, not numbers).** B0 closed (multi-id canonical + roster-centric
  coverage + opponent-graph gate). Screening backtest (event-frozen rolling, 23 folds; universe 8544
  / eval 1177) → **Bradley-Terry (B-bt)** wins **17/23 folds** (bootstrap CI excludes 0), best Brier
  + calibration. Absolute probability = **raw side-neutral B-bt** — the OOS-Platt "gain" proved to be
  a fixed-team_a-side (radiant) eval artifact and the symmetric temperature does not reproduce it, so
  **calibration is UNVALIDATED (production defaults to identity)**; a temperature candidate + cutoff +
  commit are stored in [`data/ti2026/inputs/production_platt.json`](data/ti2026/inputs/production_platt.json),
  to be validated by a side-aware eval. See `docs/backtest-results-v1.md`, `robustness-v1.md`, `calibration-v1.md`.
- **What is frozen is the pipeline SPEC, not the final TI2026 numbers** — those come from an
  as-of-cutoff refit using this frozen model + calibration. The production calibration is refit at
  the TI cutoff on pre-cutoff rolling-OOF preds only; **never** updated from crowd%, odds, or results.
- **Market gate (c): unresolved / not cleared** (no historical timestamped odds; current screenshots
  are not a substitute). Output is two-track: **Track 1** model-only (labeled "not market-validated")
  + **Track 2** expected points on the FIXED probs (no alpha, not fusion). See protocol Addendum C.
- **Simulator:** mechanics-validated (`ti_predict/simulate.py`); needs an official-rules verification
  (Swiss pairing / special elimination / seeding) before any formal tournament output.
- **No TI2026 probabilities emitted.** Blocked on: client screenshots (classify fields first) + the
  official Swiss draw.

## Two paths (pick one when inputs arrive)
- **A — fast (today, once screenshots arrive):** de-vig the contest's shown win% / a bookmaker's
  odds with `devig.py`, expand to series scores with `series.py`, produce a chalk (favourites) base
  + a few contrarian differentiators. Mirrors the football screenshot workflow.
- **B — full model (audit-gated):** B0 data audit → competing baselines → rolling backtest →
  (only if it earns it) team rating → per-map `p` → series/Swiss/bracket probabilities as an
  independent cross-check. See [`docs/modeling-plan.md`](docs/modeling-plan.md). More work, more
  robust; complexity must prove itself before it ships.

## Strategy note (read before picking an all-favourites slate)
If the top reward tier is a **hard percentile cutoff** (e.g. top 5% all get the same), pure
all-favorites picking lands near the **median**, not the top — everyone picks chalk and variance
decides the tail. Reaching the top tier needs **mostly-favorites + a few high-conviction contrarian
calls** where our probabilities beat the **crowd's** picks. Our edge is over biased human pickers,
not over the betting market. If it's a **continuous ranking**, lean more purely to per-question
EV-max. Which regime applies depends on the reward table — confirm it first.

## Layout
```
docs/            write-ups: format & field, contest, data sources, modeling-plan, research log
ti_predict/      python package: devig.py (reused), series.py (esports series math), + models TODO
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
python -m ti_predict.series        # self-test of the series math
```
De-vig is `from ti_predict.devig import shin`. OpenDota needs no key; STRATZ token (optional) goes
in `.env.local` (copy `.env.template`).

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
