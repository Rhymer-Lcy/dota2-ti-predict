# Modeling plan — audit first, let baselines compete, complexity must earn its place

Revised 2026-08-01 after external review. **Core principle: do NOT pre-commit to "Glicko-2 + hand
weights" and start reporting champion probabilities.** Prove data coverage first, then let simple
models compete under a rolling backtest; added complexity is allowed only when it yields *stable*
gains. The earlier "decided recipe" is downgraded to a hypothesis to be tested, not a spec.

## Phase B0 — data audit (before any model)
For each of the 16 teams, from OpenDota: team_id; current 5-man roster (`roster_key`); matches in
the last ~12 months (map count **and** series count); earliest/latest match; opponent-strength
distribution; event/version distribution; roster overlap vs current; and any missing matches or
`team_id` breaks. **Explain the OpenDota Elo divergence** (Xtreme ~1211 vs Yandex/PVISION ~1500+)
via coverage / id-continuity — do **not** assume "small sample / new roster" as the cause without
checking.

> Note: OpenDota's public team `rating` is a simple K=32 Elo seeded at 1000 — it is NOT
> roster/event/patch/decay/uncertainty aware. So a counter-intuitive value is a **red flag to
> audit**, not a signal to use. (Earlier claim that the 1211/1500 gap "proved" small-sample effects
> was an over-attribution; corrected here.)

## Entity separation — three distinct keys (do not conflate)
Do **not** just swap a wrong id for one "correct" id — a club can change id again, and one id can
carry several rosters. Maintain a time-versioned identity map:

- **organization** — club / brand (e.g. Team Falcons); includes TI aliases (BoomBoys=BetBoom,
  Team Vision=PARIVISION).
- **source_team_id** — the OpenDota id(s) actually used; **one org may map to several ids over time**.
- **roster_key** — the specific five players; the *true* unit of strength.

Record per mapping row: `organization, source_team_id, roster_key, valid_from, valid_to,
player_ids, source, confidence`. Weight historical matches by roster overlap with the current five;
on roster change lower inheritance **and** raise uncertainty; distinguish a temporary stand-in from
a real transfer.

## B0 hard gates — data must clear these before any training
1. **Canonical identity map** (above) resolved for all 16 teams, with time-validity, source and
   confidence — not a one-off id replacement.
2. **As-of / no-lookahead.** Reconstruct "who is the current roster" using only information knowable
   *before* the prediction cutoff (entry lists, official announcements, starting lineups of matches
   already played, subs visible then). Never use a post-cutoff match to confirm an earlier roster —
   that leaks the future into the rolling backtest.
3. **Store map-level AND series-level.** Keep `series_id, map_id, best_of, series_result,
   map_result, stage, date, patch, roster_a, roster_b`. Without series structure the "series-weight
   cap" (a 2:1 Bo3 must not outweigh a 2:0 via three "independent" maps) cannot be applied.
4. **Audit missing data, not just low counts.** 21 maps can mean *few games played* OR *OpenDota
   missed events*. Cross-check each team against the public schedule (known events ingested? map
   counts consistent? online qualifiers present? matches split across a renamed id? duplicates?).
   Apply shrinkage only when the sample is genuinely small; if data is missing, backfill first.

## Thin-sample teams
Backbone = the current roster's **team-level** rating; add player history only as a heavily-shrunk
auxiliary prior with widened uncertainty (never "new team = average of five players' old ratings").
Player-level info enters the model only if the rolling backtest shows it adds value.

## Phase B1 — competing baselines (pick by backtest, don't pre-declare a winner)
- **A — plain Elo** (opponent strength only).
- **B — time-decayed Elo / dynamic Bradley–Terry** with roster continuity (sample weights explicit
  and interpretable).
- **C — standard / minimal Glicko-2** (rating + RD + inactivity only; no stacked hand weights).

Weights are **not** hardcoded — the earlier `1.0/0.6/0.3` (version) and `1.0/0.5/0.2` (event tier)
are removed. Instead:
- **Event context → validated features**, not a blanket multiplier. Beware **double-counting**:
  Elo already rewards beating strong teams, so multiplying by "international LAN = 1.0 / league =
  0.5" can count strength twice. Split into testable features (online/LAN, same-region/cross-region,
  open/closed qualifier, group/playoff, Bo1/3/5, field average strength, days-to-TI, current-roster,
  current-patch) and keep only those that improve the backtest.
- **TI qualifiers ≠ international LAN** — qualifiers stay regional; don't put them in the same top
  tier.
- **Version → two layers**: time-decay as the default discount, plus **major-patch breakpoints** as
  added uncertainty / structural change — not a fixed per-version haircut.

## Phase B2 — rolling time backtest (not a single held-out event)
Walk-forward: train on data strictly before event A → predict A; roll to B, C, D…; **no lookahead**
(no backfilled rosters, event tiers, or results). Report per step: accuracy, **log-loss**, **Brier**,
**calibration curve**, **increment vs market**, high-confidence reliability, and **Swiss-sim
final-standing error**. **Series correlation:** cap a series' total weight so a 2:1 Bo3 does not
outweigh a 2:0 by counting three "independent" maps.

## Market — a strong baseline, not an oracle
De-vig with Shin (`devig.py`). Record **odds source + timestamp**; keep open / pre-match / closing
snapshots. Blend in logit space:

```
logit(p_final) = α · logit(p_market) + (1 − α) · logit(p_model)
```

with **α chosen by backtest**, not hand-set. Caveats: the market carries public-team bias, star
popularity, thin liquidity and staleness; and **many contest questions have no market at all**
(Swiss exact standings, stat questions, mutually-exclusive sets, fantasy) — there the model
(+ big-event shrinkage) stands alone.

## Big-stage effect ("league monster / worlds no-show")
No per-team "chokes at TI" fudge (overfits). Handle only via (1) market pricing where it exists and
(2) a modest **big-event variance shrinkage** toward the field (better calibration, no per-team
tuning) — both validated in the backtest.

## Gate to production
**No TI2026 champion / advancement probabilities are published until** the model either (a) beats
plain Elo in the rolling backtest, or (b) reliably adds increment over the market. Until then the
only outputs are the B0 audit, the baseline comparison, and calibration results.

## What carries over unchanged (still good)
Rating → single-map `p` → `series.py` → Swiss/bracket simulation; market-anchoring architecture;
JSON-source-of-truth + Markdown output; no hard-coded team strengths (all from live data).
