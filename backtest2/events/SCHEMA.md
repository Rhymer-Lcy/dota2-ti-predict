# Event manifest schema (one JSON per historical target event)

One file per outer-test event. Every field must be knowable strictly BEFORE `lock_time` except the
results block, which is the answer key used only for scoring (never for training/tuning).

| field | type | meaning |
|---|---|---|
| `event` | string | unique id, e.g. `ti2024`, `pgl_wallachia_2026_s7` |
| `tier` | string | `world_championship` \| `major` \| `high_tier_intl` |
| `lock_time` | ISO-8601 UTC | prediction cutoff for this event |
| `eligible_training_end` | ISO-8601 UTC | last timestamp allowed in training (== lock_time unless a source is stricter) |
| `field` | [string] | participating teams (canonical org names) |
| `rosters` | {team: [player_id,...]} | AS-OF-LOCK lineups (snapshot; never post-hoc) |
| `format` | string | `swiss_stop4` \| `gsl` \| `round_robin` \| `double_elim` \| ... (this year's real format) |
| `format_params` | object | rounds, best-of per stage, advancement thresholds, tiebreakers |
| `groups` | {podname: [team,...]} | official group/pod split if any (empty for single-group) |
| `first_round` | [[team,team],...] | posted round-1 pairings, if the format seeds them |
| `phases_supported` | [int] | which backtest phases this event can serve: 1 (match), 2 (tournament) |
| `scoring_rule` | string | name of the points map if the event had an official prediction game |
| `actual_results_source` | string | provenance of the truth used for scoring (url / dataset id) |
| `results` | object | ANSWER KEY (scoring only): map/series outcomes, final standings, buckets |
| `data_version` | string | opendota pull id / date the training data was snapshotted |
| `notes` | string | caveats, roster-change flags, reconstruction confidence |

Rules:
- `phases_supported` gates use: a year whose format cannot be faithfully reconstructed is `[1]` only
  and must never be reported as a 16-slot / tournament backtest.
- `results` is loaded by the scorer, NEVER by any training or tuning path (enforced in code).
- `format` must be THIS event's real format; do not coerce old years into the 2026 Swiss.
