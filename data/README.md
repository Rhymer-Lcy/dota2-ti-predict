# data/ layout

Beijing-time / TI-year namespaced so a future edition drops in cleanly as `data/ti2027/…`.

```
ti2026/
  inputs/      # TRACKED (small, hand-entered, irreplaceable)
    teams.csv          # the 16-team field + qualification + (to fill) OpenDota team_id
    odds-*.csv         # transcribed bookmaker / in-client odds per series (add as screenshots arrive)
    questions-*.csv    # the contest's prediction questions + point values (from the client)
  raw/         # GITIGNORED (large, regenerable): raw OpenDota / STRATZ API pulls (json)
  processed/   # GITIGNORED: cleaned match tables, team-rating snapshots
```

Rules (mirrors the odds-pipeline lesson):
- **inputs/** is version-controlled — it is the irreplaceable hand-entered record. Keep it small
  and text (csv). No secrets.
- **raw/** and **processed/** are regenerable from the APIs → gitignored; fetch scripts recreate
  them. Do not hand-edit.
- Never put API tokens here; they live in `.env.local` at the repo root.

Column conventions:
- `teams.csv`: `team,qualification,opendota_team_id,notes` — fill `opendota_team_id` from the
  OpenDota `/teams` lookup when the fetcher is written.
- odds files: one row per series, `date_bj,best_of,team_a,team_b,odds_a,odds_b[,source]` — de-vig
  with `ti_predict.devig.shin`.
