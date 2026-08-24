# TI 2026 Fantasy Settlement Addendum

**Post-seal evidence addendum, 2026-08-24.** Four first-party client captures of the settled TI2026
Fantasy panels — two accounts x two periods — became available after the archive was sealed. This
document records what they say.

Every claim below carries one of five labels, and they are not interchangeable:

| label | meaning |
|---|---|
| **FACT** | read directly off a client frame at native resolution |
| **DERIVED** | arithmetic performed here on those facts |
| **FROZEN** | the sealed pre-event estimate, read from the archive and never recomputed |
| **DIAGNOSTIC** | a post-hoc reading of the frozen estimate against the outcome |
| **UNKNOWN** | not identifiable from the evidence held |

---

## 1. Scope, and what is not being reopened

This is an evidence addendum. It archives a settlement that was not available at seal time and
compares the frozen Fantasy analysis against it. It is **not**:

- a reopening of Fantasy research, optimisation, reroll evaluation or model selection;
- a re-fit — no coefficient, value table, banner ranking or decision rule was touched;
- a correction of [`fantasy_closure.json`](../predictions/ti2026/postmortem/fantasy_closure.json),
  which remains valid as the knowledge state it recorded;
- a calibration claim. Two accounts over two periods cannot support one, and the estimator being
  compared was never a complete expected-value forecast.

**The sealed closure is preserved verbatim.** It recorded

```
realized_fantasy_outcome.status = OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED
```

and that statement was true when it was written: no capture of a settled Fantasy period existed, and
the archive refused to substitute the account sidebar total, the bracket settlement, or a
reconstruction for one. That file is unchanged and a test fails if it moves. The transition to

```
current_status = OFFICIAL_FANTASY_OUTCOME_ARCHIVED
```

is recorded **here and in the new artifacts only**. Old truth is not rewritten; new truth gets its
own namespace.

---

## 2. Evidence and privacy

Four raw PNG frames, 2048x1152, first-party in-client captures, operator-supplied, no network
retrieval:

| id | account | period | sha256 (first 16) | bytes |
|---|---|---|---|---|
| `ti2026-ev-007` | operator | group stage | `abbfd8393a87a534` | 2,277,719 |
| `ti2026-ev-008` | operator | Main Event | `a4584434c186c8f9` | 2,319,007 |
| `ti2026-ev-009` | target | group stage | `3fc0abd804beb045` | 2,330,127 |
| `ti2026-ev-010` | target | Main Event | `5cfb43273e518d6c` | 2,358,904 |

The raw frames are **not committed**. They also show a Steam persona, a friend leaderboard carrying
other people's display names, avatars, and the account-level event point total and percentile — none
of which is evidence for anything this repository claims. They live in the private archive under
`ti2026/fantasy/settlement/`, moved with filesystem move semantics only and re-hashed on both sides
of the move. The public repository publishes each frame's sha256 as a commitment plus a transcription
of the facts actually used, in
[`data/ti2026/evidence/private_evidence_index.json`](../data/ti2026/evidence/private_evidence_index.json).

Accounts are labelled **`operator`** and **`target`** and nothing else. Which real person holds which
account stays operator-held and unpublished, exactly as the sealed closure committed.

**Provenance here is single-path, and that is stated rather than dressed up.** The bracket settlement
had three independent agreeing paths — two client views plus a deterministic recomputation from the
committed slate. An official Fantasy score has no such recomputation: `madstone`, `watchers_taken`
and `lotuses_grabbed` are unobservable in public match data, so a recomputed Fantasy total would be
missing terms by construction. The only corroboration available is each frame's internal
consistency, and it is enforced in code: emblem rows sum to the role score, role scores sum to the
displayed total, both within display rounding (half a unit in the last place per term). The largest
observed discrepancy across all four frames is **0.01**.

---

## 3. Official client settlement — FACT

### Group stage

| | operator | target |
|---|---:|---:|
| **period total** | 37,217.47 | 39,692.11 |
| **percentile** | 44.28% | 53.36% |
| core | 12,793.80 | 21,393.54 |
| mid | 14,148.98 | 8,229.52 |
| support | 10,274.70 | 10,069.05 |

### Main Event

| | operator | target |
|---|---:|---:|
| **period total** | 82,839.01 | 93,454.67 |
| **percentile** | 88.50% | 96.41% |
| core | 39,415.52 | 36,051.03 |
| mid | 25,733.90 | 30,729.27 |
| support | 17,689.59 | 26,674.37 |

Percentiles are the client's Fantasy leaderboard percentile **for that period**. They are not the
account-level percentile in the sidebar, which is a different quantity and is deliberately not
transcribed. Percentiles are never summed, averaged or interpolated across periods.

Every scored emblem row — statistic, multiplier and points — is transcribed per frame in
[`data/ti2026/outcomes/fantasy_results.json`](../data/ti2026/outcomes/fantasy_results.json).

**Each frame is pinned to a frozen artifact by configuration, not by score.** The pin compares the
coach title pair, three teams, three player sets and every ordered `(statistic, multiplier)` emblem
pair:

| frame | frozen counterpart | fields compared | match |
|---|---|---:|---|
| ev-007 | `predictions/ti2026/fantasy/account_state_operator_20260812b.json` (tracked) | 16 | yes |
| ev-009 | `predictions/ti2026/fantasy/account_state_target_20260812d.json` (tracked) | 17 | yes |
| ev-008 | `ti2026-ev-004`, the private final banner state (`account_a`) | 23 | yes |
| ev-010 | `ti2026-ev-005`, the private final banner state (`account_b`) | 23 | yes |

The two group-stage pins re-run on any clone. The two Main Event pins need the private archive; their
result is recorded, and the test suite re-runs the live comparison wherever the archive is mounted
and fails on any disagreement.

---

## 4. Account x period — DERIVED

```
group stage   target - operator = 39,692.11 - 37,217.47 = +2,474.64
Main Event    target - operator = 93,454.67 - 82,839.01 = +10,615.66
```

Arithmetic sums of the two archived period totals:

```
operator   37,217.47 + 82,839.01 = 120,056.48
target     39,692.11 + 93,454.67 = 133,146.78
difference                          +13,090.30 to target
```

**These sums are not an official overall Fantasy total.** No rule text this project verified, and no
client view it holds, establishes that the two period scores add to a published total. The client's
sidebar figure is an account-level event point total — a different quantity, not transcribed. Until
an official equivalence is evidenced, this is arithmetic performed here, labelled as such in every
artifact.

---

## 5. Role-level decomposition — DERIVED, descriptive

`target - operator`, by role:

| role | group stage | Main Event |
|---|---:|---:|
| core | **+8,599.74** | −3,364.49 |
| mid | −5,919.46 | +4,995.37 |
| support | −205.65 | **+8,984.78** |
| **net** | +2,474.63 | +10,615.66 |

(The group-stage role differences sum to 2,474.63 against a displayed period difference of 2,474.64:
one unit in the last displayed place, which is what independent rounding of six figures permits.)

The structure matters more than the totals, and one feature of the deployment makes part of it
genuinely identifiable rather than merely described:

**Where both accounts fielded the same players, no part of the difference can be a player-selection
effect** — the underlying per-player statistics feeding both banners are literally the same numbers.

| period | role | same players? | same coach title? | what the difference can be |
|---|---|---|---|---|
| group stage | core | yes (Ame, Xxs) | yes | **emblem construction only** — +8,599.74 |
| group stage | support | yes (fy, xNova) | yes | **emblem construction only** — −205.65 |
| group stage | mid | no (Malr1ne vs CHIRA_JUNIOR) | yes | confounded: players and banner both differ |
| Main Event | core | yes (Satanic, No[t]iced) | no | emblem construction **and** coach title |
| Main Event | mid | yes (Malr1ne) | no | emblem construction **and** coach title |
| Main Event | support | no (Falcons vs Yandex pair) | no | confounded: players and banner both differ |

Two readings follow, and both are narrow on purpose:

- The **largest identifiable single effect in the whole Fantasy record is a group-stage core gap of
  +8,599.74 produced entirely by emblem construction**, on the same two players, under an identical
  coach title. A banner is not a small term.
- In the Main Event, **84.6% of the account gap sits in the one role where the deployments differed**
  (support, +8,984.78), and that role is exactly the one where team choice and banner construction
  cannot be separated from a settlement view. The share is descriptive, not causal.

---

## 6. Frozen pre-event estimate vs realized — FROZEN / DIAGNOSTIC

### 6.1 The account mapping is proved, and proved without scores

The sealed comparison used labels `account_a` / `account_b`. Two independent supports fix the
correspondence, neither of which touches a realized total:

1. the privately archived final banner states each **state their own review label**, and the public
   evidence index already publishes that label per evidence id (`ti2026-ev-004` -> `account_a`,
   `ti2026-ev-005` -> `account_b`) along with the reroll-token count that distinguishes them;
2. each Main Event frame **reproduces its counterpart's full deployed configuration** — 23 fields
   each, all matching.

```
account_a = operator        account_b = target        status: ACCOUNT_MAPPING_PROVEN
```

Mapping by score similarity would have assumed the conclusion the comparison is meant to test, so it
is not used; a test scrambles the realized totals between accounts and requires the mapping not to
move. The pseudonym-to-person mapping remains unpublished — this correspondence links two label
systems the repository already publishes and attaches no identity to any number.

### 6.2 Main Event: direction

| | FROZEN | realized | verdict |
|---|---|---|---|
| account ordering | target > operator (+3,254.3) | target > operator (+10,615.66) | **correct** |
| core | operator favoured | operator (−3,364.49) | **correct** |
| mid | target favoured | target (+4,995.37) | **correct** |
| support | target favoured | target (+8,984.78) | **correct** |

**Ordering correct; 3 of 3 role directions correct.** That is the whole of what direction can say.

### 6.3 Main Event: magnitude, and why it is not "model error"

The frozen figures were an *observed-data plug-in on the deployed configuration*, **not** a complete
expected-value forecast: three official statistics were excluded from it by construction and
contributed zero **to that estimator by exclusion**, not by evidence. So the level gap between the
plug-in and the official total is not an error measurement, and it is not reported as one:

```
operator   realized 82,839.01  -  frozen 73,679.8  =  +9,159.21
target     realized 93,454.67  -  frozen 76,934.1  =  +16,520.57
```

The gap between accounts decomposes exactly:

```
realized gap  +10,615.66
  = frozen plug-in gap        +3,254.30
  + excluded-term gap         +4,688.90     (statistics the estimator never scored)
  + residual                  +2,672.46     (projection error on what it did score)
```

The residual is projection error on the terms the estimator did include, plus any difference in
which series ended up being each role's best. It is not separable further from a settlement view.

### 6.4 The sealed uncertainty equation, evaluated

The closure carried the unobservable terms symbolically rather than guessing them:

> `delta_full(B - A) = +3254.3 + U_B_madstone + U_B_watchers - U_A_madstone - U_A_lotuses`
>
> Necessary condition for A to overturn B: `U_A_madstone + U_A_lotuses > 3254.3` — necessary, **not
> sufficient**, because B's unobserved terms were unbounded too.

The settlement displays those exact four emblems. FACT:

| term | emblem | points |
|---|---|---:|
| `U_A_madstone` | operator, mid, madstone x1.8 | 1,931.90 |
| `U_A_lotuses` | operator, support, lotuses x1.0 | 1,611.28 |
| `U_B_madstone` | target, core, madstone x1.8 | 4,914.00 |
| `U_B_watchers` | target, support, watchers x1.1 | 3,318.08 |

Two things follow, and the second is the useful one.

- **The equation named exactly the right terms.** Four unobservable emblems existed across the two
  banners; the equation had four terms, one per emblem, with the correct signs. The observability
  matrix was right about what it could not see.
- **The necessary condition was actually met — and A still lost.** `1,931.90 + 1,611.28 = 3,543.18 >
  3,254.3`. Had "necessary" been quietly read as "sufficient" at seal time, the conclusion would have
  flipped to the wrong answer. B's unobserved terms came to 8,232.08, comfortably larger. The
  distinction the closure insisted on was the distinction that decided the case.

This is a **DIAGNOSTIC**. The terms were genuinely unknown when the decision was made, they remain
unobservable in public match data, and knowing them now changes no pre-event decision rule.

### 6.5 Group stage: nothing to compare against

**No frozen two-account group-stage forecast exists.** The sealed plug-in comparison is the Main
Event one; the preselection, coach-pricing and team-change artifacts record selections and
single-account experiments, not a projected two-account total. The group-stage settlement is
therefore archived as fact and **not scored against a forecast**. Building a group-stage projection
now would be a post-hoc fit to a known answer.

---

## 7. What was correct, and what is not established

**Correct.**

- Account ordering in the Main Event, and all three role directions.
- The structure of the uncertainty: the right four terms, the right signs, and a necessary condition
  correctly refused promotion to a sufficient one.
- Every archived frame reconciles internally to within one unit in the last displayed place.

**Not established.**

- That the value model is calibrated. The level comparison is not an error measurement; three
  statistics were excluded from the estimator by construction.
- That the decision rule was right. Two accounts, one event, one realization.
- That the magnitude was well estimated. The realized gap was 3.3x the projected gap, and 44% of the
  realized gap came from terms the estimator never scored.
- Anything at all from the group stage, which had no frozen forecast.

**A displayed multiplier is still not value.** Two of the operator's fifteen Main Event emblem slots
scored exactly **0.00** — mid `roshan_kills` at 160% and support `first_blood` at 300%, the latter the
highest multiplier on that banner. None of the target's fifteen slots scored zero. This corroborates
a finding the closure already recorded rather than adding a new one, and N = 1 event: it is not a
tuning signal.

---

## 8. Unknowns

| question | status |
|---|---|
| per-player raw statistics behind any emblem row | **UNKNOWN** — the frames show scored points, not counts |
| which series set each role-period score | **UNKNOWN** — role-period is the best series, and the frames do not say which |
| opportunity from number of games played | **UNKNOWN** where teams differed; not separable from banner construction in support |
| group-stage forecast accuracy | **NOT APPLICABLE** — no frozen forecast |
| Fantasy leaderboard population | **UNCHANGED** — the closure's refusal to model it stands; the client's own percentile is archived as a displayed fact, not an estimate |
| whether the two period totals form an official overall total | **UNKNOWN** — no verified rule text or client view establishes it |

---

## 9. TI 2027 implication

One item, and it is operational rather than parametric:

> **Capture the settlement view for every Fantasy period and every compared account, immediately
> after each period settles.**

The settlement view is the only artifact that exposes the scored contribution of statistics that are
unobservable from public match data, and it exposes points per emblem — a free, exact check on the
value model. TI2026 obtained it only after the closure was sealed, which is why the closure had to
carry four terms symbolically to the end. This is a capture-discipline item added to
[`docs/TI2027_REUSE_PROTOCOL.md`](TI2027_REUSE_PROTOCOL.md) PHASE 9. **No parameter changes.**

---

## 10. Reproducibility

```
python -m ti_predict.fantasy_settlement          # rebuild both artifacts (deterministic, no network)
python -m pytest tests/test_fantasy_settlement.py
```

| artifact | what it holds |
|---|---|
| [`data/ti2026/outcomes/fantasy_results.json`](../data/ti2026/outcomes/fantasy_results.json) | the four frames' first-party facts, per-emblem, plus each frame's internal reconciliation and configuration pin |
| [`predictions/ti2026/postmortem/fantasy_settlement_addendum.json`](../predictions/ti2026/postmortem/fantasy_settlement_addendum.json) | the retrospective: mapping proof, frozen-vs-realized, attribution, unknowns |
| [`data/ti2026/evidence/private_evidence_index.json`](../data/ti2026/evidence/private_evidence_index.json) | `ti2026-ev-007` … `ti2026-ev-010`: hashes, transcriptions, scope limits |
| [`ti_predict/fantasy_settlement.py`](../ti_predict/fantasy_settlement.py) | the transcription, the arithmetic and the gates |

Both artifacts are stamped `post_event_only` / `observed_after_prediction` /
`valid_production_input: false`, live in the namespaces
[`ti_predict/chronology.py`](../ti_predict/chronology.py) already fails closed on, and cannot reach a
TI2026 fit by path, by document marker or by row marker.
