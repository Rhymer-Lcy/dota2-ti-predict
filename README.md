# dota2-ti-predict

Model-driven picks for the **Dota 2 The International 2026 in-game Predictions contest**
(a free, skill-based prediction game for cosmetic rewards — **not gambling**: no stake, no money
at risk). Goal: place in the top reward tier of the global leaderboard.

Method reuses the calibrated-probability approach from the archived soccer `odds-pipeline`
(market de-vig via Shin, cross-checked by an independent model), adapted to esports series.

## Status (2026-08-01)
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
- **Model: pending.** The team-rating + Swiss + bracket simulators are not written yet; they need a
  fresh OpenDota pull (current form) and the draw. **No team strengths are hard-coded — they must
  come from live data, never guessed.**

## Two paths (pick one when inputs arrive)
- **A — fast (today, once screenshots arrive):** de-vig the contest's shown win% / a bookmaker's
  odds with `devig.py`, expand to series scores with `series.py`, produce a chalk (favourites) base
  + a few contrarian differentiators. Mirrors the football screenshot workflow.
- **B — full model:** pull recent pro results from OpenDota → team rating (Elo/Glicko/logistic) →
  per-map `p` → series/Swiss/bracket probabilities as an independent cross-check. More work, more
  robust.

## Strategy note (read before picking an all-favourites slate)
If the top reward tier is a **hard percentile cutoff** (e.g. top 5% all get the same), pure
all-favorites picking lands near the **median**, not the top — everyone picks chalk and variance
decides the tail. Reaching the top tier needs **mostly-favorites + a few high-conviction contrarian
calls** where our probabilities beat the **crowd's** picks. Our edge is over biased human pickers,
not over the betting market. If it's a **continuous ranking**, lean more purely to per-question
EV-max. Which regime applies depends on the reward table — confirm it first.

## Layout
```
docs/            research write-ups (format & field, contest, data sources, research log)
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

## Data & hygiene
See [`docs/data-sources.md`](docs/data-sources.md). OpenDota is the free primary source; there is
**no reliable free odds API** (odds come from screenshots). Never commit tokens or paid-odds data.

## Provenance
All research claims are dated and cited in [`docs/research-log.md`](docs/research-log.md), tagged
confirmed / probable / TBD. Re-verify **TBD** items against the official client once the draw and
main-event bracket are posted.
