# data/ layout

Beijing-time / TI-year namespaced so a future edition drops in cleanly as `data/ti2027/…`.

```
ti2026/
  inputs/      # TRACKED (small, hand-entered, irreplaceable)
    teams.csv          # the 16-team field + qualification + OpenDota team_id
    canonical_identity.csv  # OBSERVED identity: the five account_ids actually seen on each org's
                       # side in recent professional matches, plus every source_team_id that roster
                       # used. It is DERIVED FROM MATCH DATA, so a player who joins days before the
                       # event is absent from it by construction (LGD still shows TaiLung there).
                       # The event roster of record is roster_events.csv.
    roster_events.csv  # the lock-period roster audit: one row per organization with its status
                       # (CONFIRMED / CHANGED / CONFLICT / UNRESOLVED) and, for a change, the full
                       # provenance. This is where LGD's TaiLung -> Topson change lives, and the
                       # official run is blocked by a CONFLICT or UNRESOLVED row.
    draw.json          # the posted draw parsed from the official league feed: round-1 pairings,
                       # structure / structure_status / pod_membership_status, and their evidence.
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

Provenance (so a prediction input can be reconstructed even though raw/ is gitignored):
- The **fetch scripts** (`ti_predict/…`) and the **data-source doc** (`docs/data-sources.md`) are
  tracked — they are the recipe.
- Every pull writes a small **tracked manifest** (`inputs/fetch-manifest.jsonl`): one line per pull
  with `endpoint, params, fetched_at, data_cutoff, n_records, sha256` of the raw payload. That plus
  the script version (repo SHA) lets us re-derive or verify any past `raw/` snapshot.
- The **raw→processed transform** is a tracked script, never a hand edit, so `processed/` is fully
  reproducible from `raw/` + code.

Column conventions:
- `teams.csv`: `team,qualification,opendota_team_id,notes` — fill `opendota_team_id` from the
  OpenDota `/teams` lookup when the fetcher is written.
- odds files: one row per series, `date_bj,best_of,team_a,team_b,odds_a,odds_b[,source]` — de-vig
  with `ti_predict.devig.shin`.
