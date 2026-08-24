# TI 2027 Reuse Protocol

An operational checklist for running this project again on a new International. It is written to be
executed in order, not read for inspiration. Every item exists because TI2026 either did it and it
worked, or did not do it and paid for that.

Evidence for every claim below: [`docs/TI2026_POSTMORTEM.md`](TI2026_POSTMORTEM.md) and
[`predictions/ti2026/postmortem/ti2026_postmortem.json`](../predictions/ti2026/postmortem/ti2026_postmortem.json).

**The three rules that govern everything else.**

1. **Verify the scoring functional against the client BEFORE optimising it.** TI2026 optimised
   expected official score under node-winner semantics and only confirmed after the tournament that
   this was what the client pays. It was. That was not guaranteed, and the whole optimisation rested
   on it.
2. **PICK UNCERTAINTY IS NOT PATH UNCERTAINTY.** In a bracket, "which team wins this series" and
   "which teams reach this node" are different unknowns. TI2026 priced selection 810 to four decimals
   as Nigma Galaxy versus Team Liquid; the series played there was Team Liquid versus Team Falcons.
3. **UNKNOWN is not zero.** A quantity excluded from an estimator contributes zero *to that
   estimator, by exclusion*. Its true value is unknown. Never substitute a proxy for a missing
   measurement.

---

## PHASE 0 - Clean year snapshot

- [ ] Create the new event namespace: `data/ti2027/`, `predictions/ti2027/`. Do not write into any
      `ti2026` path.
- [ ] Declare the event explicitly: year, TI number, league id, event name, in one config location
      rather than scattered constants (see the inventory at the end).
- [ ] Declare the knowledge cutoff explicitly, and make it a real timestamp that has been reached -
      TI2026 shipped a cutoff dated 75 minutes *after* the run that consumed it before an audit
      caught it. Assert both bounds: after the last observation, before the run start.
- [ ] Ingest TI2026 as **history** through the 2027 historical-data pipeline. Concretely: the 44
      Swiss/Elimination series and the 14 Main Event series become ordinary rated observations with
      real timestamps.
- [ ] **Do not mutate the frozen TI2026 snapshot** to do it. `data/ti2026/inputs/` and
      `predictions/ti2026/` are historical evidence. Read them; never write them.
- [ ] Confirm `ti_predict/chronology.py` still refuses `data/ti2026/outcomes/` and
      `predictions/ti2026/postmortem/` as production inputs, and extend `POST_EVENT_DIRS` with the
      2027 equivalents on day one - not after the tournament.

## PHASE 1 - First-party rule capture (do this before it is urgent)

The client is the only tier-1 source for how the contest actually scores. Capture and hash all of it
while there is no deadline pressure.

- [ ] Prediction **scoring vector** for every track, transcribed into a tracked questions file.
- [ ] **Exact scoring semantics.** Not just the points curve: *what earns a point*. TI2026's answer
      was "the team you selected at a node won that node's realized series, regardless of who the
      participants turned out to be". Re-verify; do not assume it carries.
- [ ] **Bracket topology** and the winner/loser routing, from the official feed where possible.
- [ ] **Opening seating**, from a client capture. The Valve feed carried the 2026 graph but every
      Playoff node had `team_id_1 = team_id_2 = 0`, so the feed structurally could not supply seats.
- [ ] **Fantasy stat coefficients**, transformations, caps and starting credits.
- [ ] **Title and trait mechanics**, and the banner colour layout **per period** (2026's period 1 had
      five emblem slots, not three; that was found by re-reading the client).
- [ ] **Reroll mechanics** and token costs.
- [ ] **Lock and snapshot timing**, and what each lock actually freezes.
- [ ] Hash every capture; index it publicly; keep the raw file private (PHASE 7).

**Gate:** no optimisation begins until the scoring functional is written down and verified.

## PHASE 2 - Current-event data

For **every** series as it is played, capture:

- [ ] authoritative **actual start timestamp** (not an imputed cadence),
- [ ] both teams, resolved through the canonical identity table,
- [ ] result and exact map score,
- [ ] map count and best-of,
- [ ] radiant/dire per map where available,
- [ ] roster and any stand-in,
- [ ] provenance: source, retrieval time, content hash.

TI2026 had real scheduled times for round 1 only; rounds 2-6 were placed on an assumed two-blocks-
per-day cadence. The effect was bounded (under 3% of the block's h90 weight, slate unchanged) and
labelled, but it was a standing dependency that never needed to exist - the post-event archive shows
per-series times are obtainable.

## PHASE 3 - Side provenance

- [ ] Every observation used for side-bias estimation declares `radiant_dire` or `none`.
- [ ] `team_a` / `team_b` carry **one** meaning per row, declared at construction, never inferred
      from the result.
- [ ] The side estimator **fails closed** on an unmarked row rather than assuming.

TI2026 expanded its result rows winner-first as a bookkeeping convenience. 88 of 109 rows then had
`team_a` winning by construction and the side coefficient absorbed it, reading 0.1056 instead of
0.0940. Bradley-Terry is orientation-symmetric so the strengths were untouched, but the bug was real
and only the marker prevents it recurring.

## PHASE 4 - Main Event seating

- [ ] Archive first-party client bracket evidence **immediately** when seeding is published.
- [ ] Keep three things and check all three: the **private raw original**, its **sha256**, and a
      **public-safe transcription**.
- [ ] Derive the seat table from that single transcription. Do not keep a second hand-entered copy -
      two editable tables of the same fact will eventually disagree.
- [ ] Keep **seating evidence and topology evidence separate**. They answer different questions and
      must not be circular: the capture says who is seated, the feed says how the graph routes.
- [ ] Cross-check the seated organisations against the survivors reconstructed from the completed
      series. Agreement between two independent facts is a real check.

## PHASE 5 - Production freeze

Before the final current-event optimisation runs, require **all** of:

- [ ] methodology frozen and the freeze *asserted* against the earlier locked run, not just claimed;
- [ ] the declared cutoff actually reached, and not later than the run's own start;
- [ ] clean tracked tree at run start, recorded in the manifest;
- [ ] deterministic seed recorded;
- [ ] no forbidden network use in production mode, recorded as an explicit false;
- [ ] immutable run manifest with input hashes;
- [ ] exact enumeration of coherent slates where the structure permits it (candidate set = outcome
      space), and an explicit statement of what is exact and what is an estimate;
- [ ] the official-score objective, not a proxy for it;
- [ ] client display names reconciled against canonical names, both recorded, so the operator types
      the right string into the client;
- [ ] independent audit before filing.

## PHASE 6 - Fantasy observability matrix

**Build this before any Fantasy optimisation.** One row per official statistic:

| official stat | coefficient | transformation | cap | source field | observability | missingness policy | validation status |
|---|---|---|---|---|---|---|---|

- [ ] Resolve or explicitly model: **madstones**, **lotuses**, **watchers**, rune interpretation,
      First Blood, and any statistic new in 2027.
- [ ] Any statistic that stays unobservable is carried **symbolically** through every conclusion, with
      the necessary condition for the conclusion to flip stated explicitly.
- [ ] **No proxies.** TI2026 briefly estimated three unobservable statistics from a banner-wide
      points-per-multiplier-unit ratio. That is an aggregate ratio, not a rate; three claims were
      withdrawn.
- [ ] **No share is a bound.** "One of ten players gets First Blood" is not an upper bound on any
      individual's rate over a period.

TI2026's Fantasy conclusion closed as `PASS_WITH_MATERIAL_UNCERTAINTY` solely because this matrix was
built after the value model instead of before it.

## PHASE 7 - Private evidence

- [ ] Canonical raw storage is the **external private archive**, `<private root>/<year>/`, with
      `pre_event/` and `post_event/` subdirectories. Keep it shallow.
- [ ] Repository-local ingress is `evidence_local/`, git-ignored. Stage there, then move.
- [ ] Keep the ignore rule **narrow** (`/evidence_local/`). A blanket `*.png` would also hide the
      published crop that a production gate hashes.
- [ ] **Hash before move, hash after move, prove they match.** Never recompress, resize or re-encode.
- [ ] Name files after **evidence content**, never after a nickname, an account id, or an upload
      UUID. Include a date only when independently supported.
- [ ] If a destination already exists: identical hash means reconcile and document the duplication;
      different hash is a **hard stop**.
- [ ] The public repository may carry: hash, anonymous evidence id, safe transcription, provenance
      classification, phase. Nothing else.
- [ ] **Prefer a clean crop to redaction** when a capture must be published. Crop only - no painted
      pixels - and record the crop geometry so it is reproducible.
- [ ] **Strip account-identifying strings at capture time.** Transcribe what a UI string *means*, not
      the string. TI2026 copied a rendered Compendium title verbatim into seven tracked files, and
      that string embeds the account's display name; it is now published and cannot be recalled
      (INC-19).

## PHASE 8 - Event lock

Archive, with timestamps and hashes, before each lock:

- [ ] the final submitted bracket, exactly as entered in the client;
- [ ] the final Fantasy selection;
- [ ] the final banners and their emblem layouts;
- [ ] coach titles;
- [ ] remaining reroll tokens;
- [ ] the lock time the client itself displayed.

## PHASE 9 - Post-event

- [ ] Use a separate namespace: `data/ti2027/outcomes/`, `predictions/ti2027/postmortem/`.
- [ ] Stamp every artifact `post_event_only`, `observed_after_prediction`, `valid_production_input:
      false`, and register the new directories in `chronology.POST_EVENT_DIRS`.
- [ ] Retrieve results from at least two independent sources; record URL, retrieval time, tier, scope
      and content hash for each. Corroborate every fact.
- [ ] **Derive** node assignment from the bracket graph rather than transcribing it, and key nodes on
      the participant pair **plus** the best-of clinch - a pair can be played twice in a
      double-elimination bracket (PARIVISION and Team Spirit met at the upper-bracket semifinal and
      again in the Grand Final).
- [ ] Compute official accuracy from the committed slate and the committed scoring vector. **Never
      hard-code the client's figure**; cross-check against it and fail hard on a mismatch.
- [ ] Report root local misses separately from propagated misses, and separately again from nodes
      credited despite a diverged path.
- [ ] Score the frozen model on the matchups that were actually played, conditional on the actual
      participants, with **no sequential updating** in the primary evaluation. Label point estimates
      as point estimates.
- [ ] Score only the comparators the production run already recorded. **No ex-post strategy search.**
- [ ] State what is N = 1 and change nothing on the strength of it.

---

## Portability / hard-code inventory

Audited across `ti_predict/`. **Nothing was generalised during the 2026 closure.** No item met the
bar of obvious cross-year meaning *and* exact preservation of TI2026 reproduction *and* low risk
*and* existing tests, so the whole list is recorded as migration work rather than half-done now.

### ALREADY_GENERIC - reuse unchanged

| Component | Note |
|---|---|
| `calibrate.bt_strengths`, `calibrate.est_c` | the estimator itself; no event knowledge |
| `series.series_win_prob` | best-of arithmetic |
| `backtest.load`, the universe schema | generic map-row loader and 1/series_size weighting |
| `assign.py` | Hungarian max-expected-correct solver |
| `swiss.py` | rules-based Swiss simulator with structural invariants |
| `bracket.py` graph reading, round labelling, enumeration, scoring | reads topology from the feed and derives labels from the graph; `2**len(order)` is not hard-coded to 14 |
| `chronology.py` | contract is generic; only the directory list is per-year |
| `devig.py`, `opponent_graph.py`, `resolve_identity.py` | generic |
| `postmortem.py` evaluation logic | reads slate, outcomes and topology from files; no results embedded |

### SHOULD_BE_CONFIG - works, but is a 2026 constant in code

| Assumption | Where | Migration note |
|---|---|---|
| league id `19719` | `ti15_results`, `league_feed`, feed filename | one event-config field |
| selection ids 801-814 -> feed node ids | `bracket.SELECTION_TO_NODE` | client-assigned per year; must come from the transcribed questions file |
| `EXPECTED_SHAPE` (8-team double elimination, 14 nodes) | `bracket.py` | keep as an *asserted* shape, but make the expected shape a parameter |
| Grand Final = Bo5, all others Bo3 | `bracket.load_topology` | derived from `node_type` today; re-verify per year |
| scoring vectors | `contest_rules.GROUP_SCORE`, `MAIN_EVENT_SCORE` | values are 2026's; the *mechanism* (cross-check against the tier-1 client transcription) is right and should stay |
| `SERVE_CUTOFF`, `SWISS_LOCK`, round day/block cadence | `ti15_results` | per-year; the cadence should disappear entirely once PHASE 2 is done |
| `SEED = 20260816`, `POOL`, `VERIFY_DRAWS` | `predict_main_event` | per-run config |
| `data/ti2026/...`, `predictions/ti2026/...` paths | many modules | derive from the event config |
| synthetic id offsets (`SERIES_ID_BASE`, `MATCH_ID_BASE`) | `ti15_results`, `postmortem` | must stay collision-free across years - allocate a per-year block |
| alias table | `ti15_results.ALIAS` | grows per year; keep the fail-closed `canon()` behaviour |
| Fantasy period constants, layouts, coefficients | `fantasy/` | re-capture per year (PHASE 1); 2026 already saw a period-1 layout change |

### SNAPSHOT_SPECIFIC - must NOT be generalised

Frozen so TI2026 stays reproducible: `ti15_results.SWISS` / `ELIMINATION` / `PUBLISHED_STANDINGS` /
`FINAL_EIGHT`, the seating evidence record and its pinned hash, the filed prediction artifact,
`predictions/ti2026/postmortem/frozen_serve_state.json`, `radiant_c = 0.0940`, and
`ti_predict/ti2026_record.py`.

---

## Standing research question (not a change)

In-event sequential assimilation improved the proper scores on TI2026 (Brier 0.2366 -> 0.2262, log
loss 0.6679 -> 0.6450) with a decay-origin control showing the gain is the new information rather
than the moving cutoff. **It is not adopted.** It was chosen after the outcome, measured on 14
non-independent series, and has no interval worth quoting.

To pursue it in 2027: pre-register the arm, the metric and the decision rule in a committed,
timestamped artifact **before** the analysis, then evaluate on completed events that were not used to
design it. If it survives that, it is a method. Until then it is a hypothesis, and the word
"preregistered" means a prior artifact exists - nothing weaker.
