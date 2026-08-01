# predictions/ layout & output format

Our locked, published picks — **tracked** (small text, the deliverable). Lock before each phase's
deadline and do not edit after; corrections go in a new dated file with a note. No paid-circle prose
this time — the output is a list you read and copy into the client.

```
ti2026/
  group-stage/   # Swiss-stage predictions (lock 2026-08-13 10:00 CST)
  playoffs/      # bracket predictions (lock once the 8 main-event teams are set)
```

## Output format — JSON source of truth + rendered Markdown

Each phase produces a pair with the same basename: `picks_<MMDD>.json` (machine-readable source of
truth) and `picks_<MMDD>.md` (human-readable table auto-rendered from the JSON, for reading and
copying into the game).

**Store every option's full numbers, not just the pick** — so a post-mortem can tell whether a miss
came from the strength estimate, the market blend, the crowd shift, or the pick-selection layer:

```json
{
  "question_id": "champion",
  "question": "Tournament champion",
  "question_type": "single_choice",
  "as_of": "2026-08-10T12:00:00Z",
  "data_cutoff": "2026-08-09T23:59:59Z",
  "model_version": "0.1.0",
  "model_commit": "abc1234",
  "market_source": "screenshot:bookmaker-x",
  "market_timestamp": "2026-08-10T11:30:00Z",
  "uncertainty": "high",
  "options": [
    {"team": "Team Falcons", "model_prob": 0.18, "market_prob": 0.21,
     "final_prob": 0.20, "crowd_pct": 0.24, "points": 5.2, "expected_points": 1.04}
  ],
  "pick": ["Team Falcons"],
  "tag": "chalk",
  "rationale": "final 20% ≈ market; crowd 24% only mild over-pick; not a differentiator"
}
```

Field notes: `question_type` (single_choice / multi / ranking / over_under / stat); `as_of` = when
the pick was made, `data_cutoff` = last data included, `model_commit` = repo SHA (reproducibility);
`market_*` = odds provenance; `uncertainty` from the rating RD / big-event shrinkage; `tag` =
`chalk` (model favourite) or `contrarian` (deliberate differentiation vs the crowd). The Markdown
view renders: question · pick · final_prob · crowd_% · points · expected_points · tag.
