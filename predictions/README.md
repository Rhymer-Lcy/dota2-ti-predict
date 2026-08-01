# predictions/ layout & output format

Our locked, published picks — **tracked** (small text, the deliverable). Lock before each phase's
deadline and do not edit after; corrections go in a new dated file with a note (same discipline as
the archived soccer project). No paid-circle prose article this time — the output is a list you
read and copy into the client.

```
ti2026/
  group-stage/   # Swiss-stage predictions (lock 2026-08-13 10:00 CST)
  playoffs/      # bracket predictions (lock once the 8 main-event teams are set)
```

## Output format — JSON source of truth + rendered Markdown

Each phase produces a pair with the same basename:

- `picks_<MMDD>.json` — **machine-readable source of truth**, one record per question:
  ```json
  {
    "question_id": "swiss_4-0",
    "question": "Which teams finish the Swiss stage 4-0?",
    "pick": ["Team Falcons"],
    "our_prob": 0.19,
    "crowd_pct": 0.34,
    "points": 10,
    "ev_points": 1.9,
    "tag": "contrarian",
    "rationale": "model 19% vs crowd 34% overrates favourite; ...",
    "locked_at": "2026-08-13T09:00:00+08:00"
  }
  ```
- `picks_<MMDD>.md` — **human-readable table auto-rendered from the JSON**, for the friend to read
  and copy into the game. Columns: question · our pick · our prob · crowd % · points · EV ·
  chalk/contrarian.

Why both: JSON keeps every pick auditable and lets us rank by EV / tag contrarian differentiators
and run a post-hoc review; the Markdown is what a human actually reads. `tag` is `chalk`
(model favourite) or `contrarian` (deliberate differentiation vs the crowd) so we can review which
kind of call paid off, exactly like the football post-mortems.
