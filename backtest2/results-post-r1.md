# Post-round-1 round (2026-08-10): official draw ingest, roster audit, roster-uncertainty study

Entry state: commit `825c68c` (the compact freeze), working tree clean. Production configuration
frozen and NOT re-tuned in this round: identity side-neutral B-bt, half-life 90, no calibration,
map probability `0.5*(sigmoid(d+c)+sigmoid(d-c))` with train-only `c`, Hungarian assignment plus the
verified points refinement, official run at 120000 simulations, market diagnostic only.

## 1. Round 1 is official; the pod membership is not

Valve's league feed (league_id 19719) published the round-1 nodes. `ti_predict/league_feed.py`
parses the stored snapshot, resolves every feed team id through `canonical_identity.csv`
`source_team_ids` (never by name similarity), and writes `data/ti2026/inputs/draw.json`.

| block | match | scheduled (UTC) |
|---|---|---|
| 1.A | Team Falcons vs LGD Gaming | 2026-08-13T02:00Z |
| 2.A | Tundra Esports (1w Team / **Iron Wing**) vs Nigma Galaxy | 2026-08-13T02:00Z |
| 3.A | BetBoom Team (**BoomBoys**) vs OG | 2026-08-13T02:00Z |
| 4.A | PARIVISION (**TEAM VISION**) vs Team Resilience | 2026-08-13T02:00Z |
| 1.B | Team Spirit vs Xtreme Gaming | 2026-08-13T05:00Z |
| 2.B | Team Liquid vs Vici Gaming | 2026-08-13T05:00Z |
| 3.B | Aurora Gaming vs GamerLegion | 2026-08-13T05:00Z |
| 4.B | Team Yandex vs HULIGANI | 2026-08-13T05:00Z |

All 16 ids resolve to exactly one tracked organization; the eight matches cover each team once. The
feed also restates the format at Tier 1: `team_count=16, max_rounds=5, win_loss_limit=4, advancing=3`.

**Lock time upgraded to a second independent Tier-1 source.** Every first-block node carries
`scheduled_time = 1786586400` = 2026-08-13T02:00:00Z. That is Valve's own schedule data reproducing
the value the blog wording implied, so `GROUP_LOCK_UTC` is confirmed and the circulating 15:00 UTC
figure is definitively a timezone-conversion error. The in-client countdown remains the last check.

**The two-pod structure is confirmed; only the pod MEMBERSHIP is unpublished** (corrected within
this round -- see sec 10). The official TI15 rules page states the rule directly: round 1 splits the
16 into two initial groups and pairs within them, rounds 2 and 3 pair only inside a team's initial
group, and round 4 pairs only against the other group. The league feed exposes no pod field, which
means the MEMBERSHIP is absent there -- it is not evidence that the format is an undivided 16-team
Swiss. The ".A"/".B" suffixes are broadcast blocks separated by start time (02:00Z vs 05:00Z), as are
the stream A/B/C/D labels in the event's social posts, whose later slots are follow-up Swiss rounds
for 1-0 and 0-1 teams; reading a membership off either would be a fabrication.

The draw therefore records three separate facts -- `structure = two_pod`,
`structure_status = confirmed`, `pod_membership_status = unresolved` -- and an official run with an
unresolved membership marginalizes over the 35 memberships compatible with round 1 rather than
assuming one or refusing to run.

## 2. LGD roster event (already-established fact; verified, not re-investigated)

Recorded with full provenance in `data/ti2026/inputs/roster_events.csv`:

| field | value |
|---|---|
| organization | LGD Gaming (South American roster) |
| role | position 2 (mid) |
| outgoing | TaiLung, account_id **1026694469** |
| incoming | Topson, account_id **94054712** |
| reason | tournament-integrity ban (TI2026 + all future PGL events) |
| evidence tier | 1 (LGD official Weibo / X), corroborated by the Liquipedia participant table |

Verification performed (the point of this round was the identity plumbing, not the news):
- **Account id, cross-checked and never inferred from the nickname.** Liquipedia's player infobox
  gives `playerid=94054712`; OpenDota `/players/94054712` returns name "Topson" (steamid
  76561198054320440) and `/proPlayers` lists that account as Topson. Two other accounts use the same
  nickname (1309827242, 1430260352) and belong to other people -- exactly the collision the
  numeric-id rule exists to prevent. TaiLung's 1026694469 is already inside LGD's tracked
  `player_ids`.
- **Valve has not synced the change anywhere machine-readable.** The league feed's
  `registered_players` array is empty for every team, so registration cannot be confirmed from the
  feed; the roster change rests on the club's own Tier-1 announcements.
- **No match record exists for Topson with LGD**, and none for Topson in our professional universe
  at all: 0 of his matches fall inside the 2026-02-27..2026-08-09 pro-match window.
- LGD's own most recent official maps (2026-08-03, The Games of the Future 2026) were played by the
  previous lineup, TaiLung included.

### Topson as-of profile (used ONLY to grade uncertainty, never as a strength adjustment)
- Retired from competitive Dota on 2024-09-24 (announced by Tundra Esports); left for Finnish
  military service in January 2025. Liquipedia still lists his status as Retired.
- Public match activity is close to zero: **12 matches in the last 3 months, 14 in 6 months, 33 in
  12 months**, against 298 in the preceding 12 -- and the most recent is 2026-06-11, two months
  before TI.
- No official match on the current patch, and no recorded competitive game with any of LGD's other
  four players.
- Grading: **high roster uncertainty** -- a two-year layoff, a new region, a new language group and
  four days of preparation. That is a statement about how little the data pins the new lineup, not a
  claim that the team got worse. Nothing here is converted into a strength bonus or penalty.

### Historical late core replacement: qualitative only, deliberately not quantified
Late position-1/2 replacements at LAN majors do exist (Team SMG's visa problem at TI2023 and the
Mind Control backup; roughly seven of seventeen Arlington Major 2022 teams fielding stand-ins; the
Nigma Galaxy stand-in run to third; OG winning the Stockholm Major with Ceb standing in). The record
is small, mixed, and self-selected in reporting. Our own universe starts 2026-02-27 and carries no
roster-change labels, so a genuine as-of study cannot be constructed. Verdict, per the pre-registered
rule: **`player-aware production adjustment: inadmissible before TI2026`**; the historical record is
used for qualitative risk framing only, and no case was selected to argue for or against LGD.

## 3. Full 16-team lock-period roster audit

`data/ti2026/inputs/roster_events.csv` (validated by `ti_predict/rosters.py`, enforced by tests, and
carried in every run manifest): **15 CONFIRMED, 1 CHANGED, 0 CONFLICT, 0 UNRESOLVED.**

| organization | status | note |
|---|---|---|
| LGD Gaming | **CHANGED** | position 2: TaiLung (banned) -> Topson |
| Team Liquid | CONFIRMED | source conflict **resolved** -- see below |
| Tundra Esports | CONFIRMED | competes as **Iron Wing** (1w Team); five players unchanged since the 2026-06-01 transfer |
| PARIVISION | CONFIRMED | competes as **TEAM VISION** (feed id 9572001) |
| BetBoom Team | CONFIRMED | competes as **BoomBoys** |
| HULIGANI | CONFIRMED | position 3 "Corrupted" and "Vazya" are one player, one alias |
| Team Resilience | CONFIRMED | position 1 "YSR-04E"; some press lists the same player as "Erika" |
| Team Yandex | CONFIRMED | "Malady" = Maladych |
| Aurora, Falcons, Spirit, Nigma, OG, GamerLegion, Vici, Xtreme | CONFIRMED | no change |

**Team Liquid (Nisha vs Miracle!) -- resolved, no model change.** A TI2026 team page listing
`m1CKe / Miracle! / Ace / Boxi / tOfu` is contradicted by three independent checks: the five
account_ids actually on Liquid's side of their most recent official matches (2026-08-05) are
tOfu / Ace / **Nisha** / Boxi / m1CKe; the Liquipedia participant table (current enough to carry the
2026-08-09/10 LGD notes) lists Nisha at position 2 with no stand-in note; and no organization or
tournament announcement of a Liquid change exists. Graded a page data error. It is recorded as a
resolved source conflict rather than silently dropped -- and had it stayed unresolved, the
`CONFLICT` status would have blocked the official run rather than defaulting to the roster already
in the model.

## 4. Data refresh -- and two real pipeline defects it exposed

**Refresh result: no new data exists.** `scan_promatches` re-ran to completion (91 pages, merged,
fail-closed) and produced a byte-identical scan: 9146 matches, 2026-02-27..2026-08-09, same SHA-256
as the previous pull. A second independent pass hours later still found nothing newer. No
professional match has been played since 2026-08-09T19:02Z -- the field is travelling to Shanghai.
Refit strengths are therefore **bit-identical** to the pre-refresh fit (max |delta| over the 16 teams
= 0.000e+00, `c = +0.0932`, 8690 training maps).

Final state: universe 8690 maps (2026-02-27T20:49Z .. 2026-08-09T19:02Z), 1239 target maps, 23 folds.
SHA-256 (first 16): universe `738e7626ffa43d0b`, teams `6fa7689f954f39e9`, canonical_identity
`32c6998a7342e93b`, draw `1e0074e3c0bfbafd`, roster_events `f7c16c1ca24f62b5`.

Two defects surfaced, both of which would have corrupted a lock-day run:

1. **`resolve_identity.py` was overwriting the deep pro-match scan.** It ran its own 30-page scan and
   wrote it straight over `raw/promatches_scan.json`, truncating the rating universe from 9146 maps
   (from 2026-02-27) to 3000 (from 2026-05-17). This is the same silent truncation observed on
   2026-08-09 -- whose fix went into `scan_promatches.py`, leaving the actual cause in place, so the
   runbook's own step order reintroduced it every time. Now it MERGES and refuses to write on any
   coverage regression. Verified: 3000 fetched -> 9146 kept, window unchanged.
2. **`resolve_identity.py` was overwriting the tracked canonical identity table.** An OpenDota 5xx
   burst (521/522) left 14 of 16 rosters empty, and the write still went through -- erasing every
   `source_team_ids` mapping, the column through which the rating universe resolves TI organizations
   (and the only place the Iron Wing / TEAM VISION / old-Resilience / old-Xtreme ids live). It now
   writes only `processed/identity_resolved.csv`, exits non-zero on an incomplete resolution, and
   retries transient 5xx; `build_canonical.py` is the single writer of the tracked table.

A third, smaller inconsistency was corrected: `inputs/folds.csv` and the `is_target` column of
`universe_maps.csv` had been generated against a stale `dataset_maps.csv` (11 folds instead of the 23
the validation record uses), because `universe` runs before `build_dataset` and was never re-run
after. Rebuilt to a verified fixed point. **Production strengths are provably unaffected**:
`is_target` is used only to build the fold table, and refitting from the pre-refresh universe
reproduces all 16 strengths bit-identically (checked above).

After the fixes, re-running identity resolution end to end succeeded with `conf=high` for all 16
teams and rosters matching the tracked table exactly.

## 5. LGD roster sensitivity: how far would the strength have to move?

The production model is organization-level, so a lineup change cannot be priced by editing a
strength: LGD's history was played by the previous five, Topson's history belongs to other
organizations, and transplanting either would be a fabrication. Rather than guess a Topson prior,
`backtest2/roster_sensitivity.py` inverts the question -- *how large a shift in LGD's strength does
the DECISION actually tolerate?* Nothing in production is edited.

**Baseline** (cutoff 2026-08-13T02:00:00Z, open structure, posted round 1, 40000 sims/scenario):
LGD strength **+0.5381**, rank **10/16**, assigned slot **decider_loss**; bucket distribution
4-0 0.018 / 4-1 0.067 / decider_win 0.306 / **decider_loss 0.387** / 1-4 0.153 / 0-4 0.071.
Round 1: Falcons beat LGD with map probability **0.626**, Bo3 series **0.686**.

**Scale, taken from the model's own uncertainty rather than asserted** (300 resamples each):
event-blocked bootstrap **sigma = 0.282**, series-blocked **sigma = 0.163**; the event-blocked
5-95% band is **-0.026 .. +0.955**, wide and right-skewed because LGD's record sits in few events.
For context LGD is the third most uncertain team of the sixteen (Nigma 0.385, Yandex 0.320, LGD
0.282; the best-pinned are Xtreme 0.133 and Aurora 0.154). **The estimate's own noise is already
larger than most plausible roster effects** -- which is the substantive finding.

| delta | in sigma | LGD strength | LGD slot | Falcons series win | E[correct] | regret of baseline slate | other teams moved |
|---:|---:|---:|---|---:|---:|---:|---|
| -0.423 | -1.5 | +0.115 | 0-4 | 0.807 | 5.37 | 0.105 | BetBoom, GamerLegion, OG, Falcons |
| -0.282 | -1.0 | +0.256 | 1-4 | 0.771 | 5.29 | 0.023 | BetBoom, GamerLegion, Falcons |
| -0.141 | -0.5 | +0.397 | decider_loss | 0.730 | 5.27 | 0.000 | none |
| 0 | 0 | +0.538 | **decider_loss** | 0.686 | 5.26 | 0.000 | none |
| +0.141 | +0.5 | +0.679 | decider_win | 0.638 | 5.28 | 0.045 | Nigma |
| +0.282 | +1.0 | +0.820 | decider_win | 0.587 | 5.32 | 0.137 | Nigma |
| +0.423 | +1.5 | +0.962 | decider_win | 0.535 | 5.34 | 0.205 | Nigma |

Bootstrap-quantile scenarios agree: the 5th percentile of LGD's own strength distribution puts it in
0-4, the median leaves the slate untouched, the 95th moves it to decider_win.

### The answer
**LGD's pick changes at +0.070 log-strength upward (+0.25 sigma) and at -0.252 downward
(-0.89 sigma)** -- bisected to about +/-0.006 resolution, with the residual Monte-Carlo noise of a
40000-sim run on top. The asymmetry is real and comes from the capacity constraint, not from LGD:
upward, LGD only has to overtake Nigma Galaxy for the last decider_win slot (their bucket
probabilities differ by 0.075); downward, it must fall past three teams to reach the two 1-4 slots.

Two consequences worth separating:
- **In labels the pick is fragile upward.** A quarter of one standard error is enough to flip
  decider_loss -> decider_win. Anyone who believes Topson makes LGD stronger than the previous
  lineup, by even a small margin, is arguing for the other side of that boundary.
- **In value it barely matters.** The regret of submitting the baseline slate in a world where the
  perturbed strength is true is **0.002 expected correct at the upward threshold and 0.015 at the
  downward one**, rising to only 0.045 at +0.5 sigma and 0.205 at +1.5 sigma -- against a total
  expected score of about 5.26/16. The LGD slot is a coin-flip whose price is nearly zero, which is
  exactly why it does not justify overriding the frozen model by hand.

The direction of the roster effect is left unstated on purpose. The evidence supports "wider
uncertainty about LGD", not a signed adjustment: a two-year layoff argues one way, two Aegises argue
the other, and neither is measurable from data that exists today. Since the decision is nearly
value-neutral across the whole plausible range, no adjustment is warranted in either direction.

## 6. Post-round-1 provisional slate (R1 fixed, pod membership marginalized)

`backtest2/post_r1.py`, 35 admissible memberships x 3000 simulations = **105000 headline
simulations** under the official two-pod structure (MC se about 0.0015 per cell), plus a same-sized
open-16 comparator run. Frozen production configuration throughout.

**The membership question is closed by measurement.** Marginalizing over the 35 admissible
memberships gives the slate below; running the no-pod comparator instead gives the **same 16 slots**,
with a largest per-cell probability difference of **0.0056** (Nigma; every other team below 0.005).
So even the extreme case -- removing the pod constraint entirely -- does not move a single slot, and
the unpublished membership therefore cannot. The official run still refuses to *claim* a membership
nobody published: it marginalizes and says so in the manifest.

| bucket | picks (marginalized probability) |
|---|---|
| 4-0 x1 | PARIVISION (0.23) |
| 4-1 x2 | Team Yandex (0.25), BetBoom Team (0.24) |
| decider_win x5 | Aurora (0.40), Falcons (0.40), Spirit (0.40), Liquid (0.39), Nigma (0.34) |
| decider_loss x5 | Vici (0.40), Xtreme (0.39), Tundra/Iron Wing (0.39), LGD (0.38), Resilience (0.38) |
| 1-4 x2 | HULIGANI (0.25), GamerLegion (0.25) |
| 0-4 x1 | OG (0.19) |

E[correct] = **5.261 / 16**. The points refinement proposed no move, so the Hungarian slate stands.
D4 opponent-choice sensitivity: **no team changes slot** across strategic / noisy / random.

**Round 1, side-neutral map and Bo3 series win probability (first-named team):**

| match | map | series |
|---|---:|---:|
| Team Falcons vs LGD Gaming | 0.626 | 0.686 |
| Tundra Esports (Iron Wing) vs Nigma Galaxy | 0.485 | 0.478 |
| BetBoom Team vs OG | 0.700 | 0.784 |
| PARIVISION vs Team Resilience | 0.681 | 0.759 |
| Team Spirit vs Xtreme Gaming | 0.634 | 0.696 |
| Team Liquid vs Vici Gaming | 0.567 | 0.600 |
| Aurora Gaming vs GamerLegion | 0.658 | 0.730 |
| Team Yandex vs HULIGANI | 0.694 | 0.777 |

Only one round-1 match is near a coin flip: Iron Wing vs Nigma at 0.478.

### Stable slots, boundary slots, and where the uncertainty lives
Uncertainty ordering, unchanged from the pre-draw decomposition and now measured with round 1 fixed:
**strength estimation (bootstrap sigma 0.13-0.39 per team) >> pod membership (<= 0.0056 per cell,
0 slot changes) > D4 policy (0 slot changes) > Monte-Carlo (0.0015)**. The binding uncertainty is
still the strength estimate; for round 1 the draw is no longer uncertain at all.

- **Stable** (assigned-vs-second gap >= 0.10, structural delta <= 0.005): Xtreme decider_loss
  (+0.165), Falcons decider_win (+0.157), Aurora decider_win (+0.144), Spirit decider_win (+0.113).
- **Boundary set A -- the top three slots.** PARIVISION leads 4-0 clearly (0.225 vs 0.147), but
  Yandex 0.249 / Falcons 0.240 / BetBoom 0.238 are a genuine three-way tie for two 4-1 slots; which
  two are named is decided by the global assignment, not by any real separation. A 3000-simulation
  rehearsal reshuffled exactly this trio -- which is why the official run uses 120000.
- **Boundary set B -- the bottom three slots.** OG 0.273 / HULIGANI 0.253 / GamerLegion 0.245 for
  1-4, and OG 0.188 / HULIGANI 0.155 / GamerLegion 0.144 for 0-4, with Xtreme just behind. Same
  situation: three teams, three slots, no separation.
- **Boundary set C -- the middle.** Nigma decider_win at a NEGATIVE gap (about -0.03) is the thinnest
  assignment in the slate, and it is the same boundary LGD would cross if its strength rose by a
  quarter of a standard error (section 5).
- **Roster uncertainty** applies to LGD alone, and section 5 bounds its whole plausible range at
  about 0.2 expected correct.

## 7. Market diagnostic (not fused, not a promotion input)

Polymarket outright champion market, normalized, snapshot 2026-08-10T07:16Z
(`backtest2/market_check.py`): **Spearman rho vs B-bt = 0.865**, unchanged from the pre-draw round.
The top seven agree almost exactly (PARIVISION and Yandex first and second on both sides).

Material disagreements, flagged for human sanity-check only:
- **OG**: model rank 16 (last), market rank 11 (2.2%). We put OG in 0-4; the market does not think OG
  is the weakest team in the field. This is the largest divergence and it lands directly on boundary
  set B.
- **Nigma Galaxy**: model rank 8, market rank 14 -- the standing flag from the previous round, and
  also our thinnest assignment (boundary set C).
- Vici (model 12 / market 9) and Xtreme (13 / 10) are milder versions of the same pattern.

**Repricing check on the roster event.** LGD's normalized implied champion probability is **2.0%**,
against 2.0% in the 2026-08-09 snapshot taken before the Topson announcement propagated: the market
did not materially reprice LGD after the change. That is evidence about the market's judgement of the
change, not about LGD's strength, and it is consistent with declining to apply a signed adjustment.
No market number enters the model.

## 8. Official readiness

**The remaining blockers are operational, not structural.**

| requirement | state |
|---|---|
| Round 1 confirmed | **PASS** - official, from the league feed, all 16 ids resolved |
| Pairing structure confirmed | **PASS** - two-pod, from the official rules page |
| Pod membership | **UNRESOLVED -> marginalized** over 35 admissible memberships, recorded in the manifest; worst-case held-out regret 0.032 expected correct, inside the 0.05 limit |
| Roster audit clean | **PASS** - 15 CONFIRMED, 1 CHANGED, 0 CONFLICT/UNRESOLVED |
| Universe refreshed | **PASS** - current through 2026-08-09T19:02Z, genuinely the latest professional map |
| Freshness gate | needs `--allow-stale` at the lock cutoff (3.29 d lag); no pro match exists in between, and the override is recorded in the manifest |
| Client-confirmed cutoff | **pending** - confirm the in-client countdown on the day (expected 2026-08-13T02:00:00Z) |

Rehearsed end to end on the real data (140000 simulations, 4000 per membership, written outside the
repository): the gate **accepts**, and the marginalized slate is exactly the section-6 slate. The
manifest carries the three structure fields, the marginalization, the membership-agreement
measurement, the roster audit, the freshness-gate override and every input hash.

**Sizing the membership gate.** It compares 35 held-out regret estimates, so it needs enough
simulations per membership or it blocks on Monte-Carlo noise instead of a real effect. Measured
worst-case regret against the 0.05 limit: **0.206 at 500 per membership, 0.064 at 1000, 0.032 at
4000**. The runbook therefore requires at least 140000 total simulations while the membership is
unresolved. (The first implementation of this metric scored each alternative slate on the same
archive that selected it and reported 0.21 - the same in-sample winner's curse the points refinement
was corrected for; it is now measured on the independent verification archive.)

No official slate is emitted yet: the lock-day sequence still calls for one final data refresh and
the in-client cutoff confirmation before the real run.

## 9. Verdicts

| component | verdict |
|---|---|
| Model B-bt half-life 90, no calibration | **KEEP** - untouched; no challenger run this round |
| Solver Hungarian + verified points refinement | **KEEP** - the refinement proposed no move on the post-R1 archive |
| Round-1 ingest | **ADOPT** - official, machine-readable, hash-recorded |
| Lock time 2026-08-13T02:00:00Z | **CONFIRMED** at Tier 1 by a second independent Valve channel |
| Pod structure | **CONFIRMED two-pod** (official rules page); the league feed's silence concerns membership only |
| Pod membership | **MARGINALIZED** over 35 admissible partitions; measured effect <= 0.0056 per cell, zero slot changes, held-out regret 0.032 |
| LGD roster event | **RECORDED, NOT PRICED** - no strength edit; decision impact bounded at about 0.2 expected correct across the full plausible range |
| Player-aware production adjustment | **INADMISSIBLE** before TI2026 (no as-of data) |
| Market | **DIAGNOSTIC ONLY** - rho 0.865; OG and Nigma flagged for human sanity-check |
| Pipeline defects (scan truncation, identity clobber, stale folds) | **FIXED**, with tests; production strengths verified bit-identical |


## 10. Correction log (within this round)

- **Pod semantics, corrected 2026-08-10.** The first pass of this round read the league feed's
  missing pod field as evidence that TI15 runs one undivided 16-team Swiss, recorded a single
  `pods_status` flag, and offered an `open-16` structure as an official-mode fallback. That was
  wrong. The official TI15 rules page states the two-initial-groups rule directly: round 1 splits
  the field and pairs within the groups, rounds 2-3 pair inside a team's group, round 4 pairs
  across. Absence of a field in a feed is evidence about the feed. Corrected everywhere:
  - the draw now carries three separate facts -- `structure`, `structure_status`,
    `pod_membership_status` -- instead of one conflated flag;
  - `structure = two_pod`, `structure_status = confirmed`, `pod_membership_status = unresolved`;
  - an official run marginalizes over the 35 round-1-compatible memberships and records it, rather
    than refusing to run or asserting a structure;
  - `open-16` is demoted to a sensitivity comparator and is **refused** in official mode;
  - the 35-partition study from the first pass is retained unchanged -- its result (identical slate,
    <= 0.0056 per-cell difference) is exactly the evidence that membership uncertainty barely
    affects the submission, and it never depended on the structural claim that was wrong.
- **Topson recent-match check, no change to the conclusion.** Liquipedia's Topson page lists the
  2026-06-29 Finland-Switzerland and 2026-06-30 Finland-Norway matches under Recent Matches, but he
  was a listed substitute for that national roster and did not play: the actual lineup was
  mumu / topita / MTD / Nukkumatti / Wazza, neither 06-30 map shows him, and account 94054712 has no
  match record on those dates. Last confirmed competitive appearance therefore remains 2026-06-11,
  and the inactivity / high-roster-uncertainty grading in section 2 stands unchanged. A team-roster
  association on a wiki is not an appearance.
