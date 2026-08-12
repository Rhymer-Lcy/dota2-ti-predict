"""Coach prefix and suffix pricing, by exact replay of the official scoring layers.

The earlier pricing multiplied a trigger frequency by a bonus. That is only correct when the
trigger is independent of how good the game was, and the period keeps a MAXIMUM over series, so
the correlation is precisely what decides the value. the Underdog is the standing counter-example:
it fires on nearly half of all player-maps and is worth less than half of what its frequency
suggests, because it fires on losses and the max throws losses away.

This module therefore never multiplies a frequency by a bonus. It replays the layering Valve
actually uses --

    player-game score  ->  role score = mean over the role's players
                       ->  series score = sum of the best two games in the series
                       ->  period score = MAX over series
                       ->  TI exposure  = expectation over how many series the team plays

-- with the coach bonus applied at the player-game level, where the game's hero and the game's
outcome are still attached to each other. Common random numbers are used across coach settings so
the reported gain is a paired comparison rather than the difference of two noisy means.

What can and cannot be priced is a property of the evidence, not of convenience:

  prefixes  three are exact (red / blue / green), two are LOWER BOUNDS (the community hero table
            tags a strict subset of each condition), and three have no category table at all.
  suffixes  six are exact. the Tormented is bounded from above by deaths that no enemy hero is
            credited with, which is an exact zero whenever that count is zero. the Cruel needs
            positions and is genuinely unavailable.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

from ti_predict.fantasy import baseline as bl
from ti_predict.fantasy import exposure as ex
from ti_predict.fantasy import fetch_player_stats as fp
from ti_predict.fantasy import preselection as pre
from ti_predict.fantasy import questions as fq

SEED = 20260812
DRAWS = 4000
ROLES = ("core", "mid", "support")

HERO_TABLE = os.path.join("data", "ti2026", "inputs", "fantasy", "hero_categories.json")
COMMUNITY = os.path.join("data", "ti2026", "inputs", "fantasy",
                         "community_prefix_frequencies.json")
EXTRAS_CSV = os.path.join(fp.FANTASY_PROC, "match_extras.csv")
HEROES_CSV = os.path.join(fp.FANTASY_PROC, "player_map_heroes.csv")

def _pool_bonuses(kind):
    """Bonuses read from the ruleset, never re-typed here.

    An earlier revision kept its own literal copy of these numbers, and three of the eight
    suffixes were transcribed wrong -- the Flayed Twins Acolyte at 30 instead of 9, the Tormented
    at 13 instead of 23, the Cruel at 19 instead of 13. The ruleset had them right the whole time.
    A second copy of a fact is a bug waiting to happen, so there is now only one.
    """
    pool = fq.load_rules()["coach_titles"]["selectable_pool_2026"][kind]
    return {e["name"]: int(e["bonus_percent"]) for e in pool}


PREFIX_BONUS = _pool_bonuses("prefixes")
SUFFIX_BONUS = _pool_bonuses("suffixes")

# how each 2026 condition maps onto the community table's flags, and how tightly
PREFIX_FLAG = {"Crimson": ("isred", "exact"), "Cerulean": ("isblue", "exact"),
               "Emerald": ("isgreen", "exact"),
               "Elemental": ("isaquatic", "lower_bound"),
               "Otherworldly": ("isundead", "lower_bound")}
PREFIX_NO_TABLE = ("Royal", "Golden", "Heroic")

# The independent unit each suffix's condition is drawn on. Seven conditions are properties of the
# GAME and are shared by everyone in it, so counting them once per player-map would inflate the
# sample eight-fold and shrink every confidence bound by the square root of that. Only the
# Underdog varies within a game, and even then only between the two teams, not between teammates.
SUFFIX_SCOPE = {"the Tormented": "match", "the Flayed Twins Acolyte": "match",
                "the Patient": "match", "the Decisive": "match", "the Clutch": "match",
                "the Lucky": "match", "the Cruel": "match", "the Underdog": "team_game"}

FIRST_BLOOD_LATE = 600      # "first blood does not happen in the first ten minutes"


# --------------------------------------------------------------------------- inputs

def load_hero_categories(path=HERO_TABLE):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def load_hero_maps(path=HEROES_CSV):
    """{(match_id, account_id): hero_id}"""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(int(r["match_id"]), int(r["account_id"]))] = int(r["hero_id"])
    return out


def extras_fingerprint(extras, expected):
    """Which matches the bounds were computed on, so a partial run is never mistaken for a full one.

    Completeness is checked against the actual target set, not a remembered round number: the
    difference between "620 rows" and "every match this window contains" is exactly the difference
    between a bound that may be read as a population bound and one that may not.
    """
    ids = sorted(extras)
    digest = hashlib.sha256(",".join(str(i) for i in ids).encode()).hexdigest()
    missing = sorted(set(expected) - set(ids))
    return {"expected_matches": len(expected), "fetched_matches": len(ids),
            "unique_matches": len(set(ids)), "missing_matches": len(missing),
            "sha256": digest, "coverage_complete": not missing}


def load_extras(path=EXTRAS_CSV):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[int(r["match_id"])] = {k: (int(v) if v not in ("", None) else None)
                                       for k, v in r.items() if k != "match_id"}
    return out


def parse_community_frequencies(text):
    """Per-player prefix percentages out of the community optimizer's data file.

    Deliberately parsed rather than transcribed, so the numbers in the artifact cannot drift
    away from the numbers in the cited source.
    """
    keys = ("crimson", "cerulean", "emerald", "royal", "golden",
            "elemental", "otherworldly", "heroic")
    out = {}
    for name, vals in re.findall(r'\{\s*name:\s*"([^"]+)"\s*,\s*values:\s*v\(([^)]*)\)', text):
        nums = [float(x) for x in vals.split(",")]
        nums += [0.0] * (len(keys) - len(nums))
        out[name] = dict(zip(keys, nums))
    return out


def banner_weights(state):
    """{role: ([(stat, multiplier), ...], [dropped stats])} from the observed War Banner.

    A slot whose stat has no public per-map source (Watchers Taken is the live case) is dropped
    rather than zeroed silently, and reported, because dropping it understates that role's score.
    """
    out = {}
    for role, b in state["banners"].items():
        keep, drop = [], []
        for s in b["slots"]:
            if s["stat"] in bl.UNAVAILABLE or s["stat"] not in bl.STAT_COLUMNS:
                drop.append(s["stat"])
            else:
                keep.append((s["stat"], float(s["displayed_multiplier"])))
        out[role] = (keep, drop)
    return out


# ------------------------------------------------------------------- exact layering

def player_map_totals(rows, accounts, weights, rules):
    """{event: {series: {match: {account: raw fantasy total under this banner}}}}

    Kept at player-map granularity on purpose: the coach multiplies a PLAYER's game, and the two
    players on a role can be on different heroes with different outcomes in the same game.
    """
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        acct = int(r["account_id"])
        if acct not in accounts:
            continue
        total = 0.0
        ok = True
        for stat, mult in weights:
            v = bl.map_score(r, stat, rules, False, "linear")
            if v is None:
                ok = False
                break
            total += mult * v
        if ok:
            # int, not the CSV's string: the hero and extras tables are keyed by integer match_id,
            # and a silent type mismatch here reads as "no trigger ever fired"
            per[r["_league"]][r["_series"]][int(r["match_id"])][acct] = total
    return per


def series_scores(per, n_players, bonus_of, min_series_maps=2):
    """Collapse player-maps to one score per series, applying the coach at the player-game level.

    bonus_of(match_id, account_id) -> fractional bonus for that player's game.
    """
    out = defaultdict(dict)
    for event, ser in per.items():
        for sid, by_match in ser.items():
            vals = []
            for mid, by_acct in by_match.items():
                if len(by_acct) != n_players:
                    continue        # a role scores only when every current player appears
                vals.append(sum(t * (1.0 + bonus_of(mid, a)) for a, t in by_acct.items())
                            / n_players)
            if len(vals) >= min_series_maps:
                out[event][sid] = sum(sorted(vals, reverse=True)[:2])
    return {k: v for k, v in out.items() if v}


def scored_matches(per, n_players, min_series_maps=2):
    """The matches that actually reached the period score, so a rate is measured on them.

    A match where only one of the role's two players appeared never contributed, and a series with
    too few complete games was dropped whole. Counting triggers over anything wider would measure
    a rate on games the scoring never saw.
    """
    out = set()
    for ser in per.values():
        for by_match in ser.values():
            complete = [m for m, d in by_match.items() if len(d) == n_players]
            if len(complete) >= min_series_maps:
                out.update(complete)
    return out


def bernoulli_units(scope, matches, org):
    """The independent trials a suffix's trigger is drawn on, given what its condition depends on.

    A game-level condition is one trial per match no matter how many of our players were in it.
    Treating each player-map as its own trial is the error that makes a zero-event bound look
    roughly three times tighter than the evidence supports.
    """
    if scope == "match":
        return {m: m for m in matches}
    return {(m, org): m for m in matches}


def _event_pool(scores_by_event, event):
    """One event's series scores, in a stable order so common random numbers line up."""
    ser = scores_by_event[event]
    return np.array([ser[sid] for sid in sorted(ser)], dtype=float)


def project_period(scores_by_event, counts, seed=SEED):
    """Event-equal period projection. THE single primitive; production and bootstrap both call it.

    A historical event is treated as one period-like block. Within an event, a simulated TI period
    draws that team's frozen-exposure number of series FROM THAT EVENT and keeps the maximum;
    events are then averaged with equal weight.

    The estimator this replaces flattened every event into one pool and drew the period from it.
    That was wrong in two separate ways, and the docstring claimed the opposite of what the code
    did. First, an event where the team happened to play more series contributed proportionally
    more series to the pool, so attendance became weight -- the exact bias the per-event
    aggregation upstream exists to avoid. Second, a single simulated period could mix series from
    different tournaments, which is not a period: a TI run happens inside one event, against one
    field, on one patch, and the maximum over such a run is not the maximum over a career.
    """
    rng = np.random.default_rng(seed)
    counts = np.asarray(counts)
    width = int(counts.max()) if counts.size else 0
    mask = np.arange(width)[None, :] < counts[:, None]
    per_event = []
    for event in sorted(scores_by_event):
        pool = _event_pool(scores_by_event, event)
        if pool.size == 0:
            continue
        idx = rng.integers(0, pool.size, size=(counts.size, width))
        vals = np.where(mask, pool[idx], -np.inf)
        per_event.append(float(vals.max(axis=1).mean()))
    if not per_event:
        return float("nan")
    return float(np.mean(per_event))          # equal weight per event, never per series


def project_period_pooled(scores_by_event, counts, seed=SEED):
    """WITHDRAWN estimator, retained only so the correction can be attributed single-factor.

    Flattens every event into one pool. Not used by any decision path.
    """
    pool = np.array([s for ev in scores_by_event.values() for s in ev.values()], dtype=float)
    if pool.size == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    out = np.empty(len(counts))
    for i, k in enumerate(counts):
        out[i] = pool[rng.integers(0, pool.size, size=int(k))].max()
    return float(out.mean())


def exposure_counts(org, probs, draws=DRAWS):
    """Common random numbers: one fixed vector of series counts reused by every coach setting."""
    rng = np.random.default_rng(SEED)
    dist = ex.exposure_distribution(probs)
    if org not in dist:
        return np.full(draws, 5)
    return pre.exposure_draws(rng, probs, org, draws)


# ------------------------------------------------------------------- trigger tables

def prefix_bonus_fn(prefix, heroes, cats):
    flag = PREFIX_FLAG[prefix][0]
    frac = PREFIX_BONUS[prefix] / 100.0

    def fn(mid, acct):
        h = heroes.get((mid, acct))
        return frac if h is not None and cats.get(h, {}).get(flag) else 0.0
    return fn


def suffix_trigger_table(rows, extras):
    """{(match_id, account_id): {suffix: bool}} for every suffix the evidence can decide."""
    order, length = pre._series_geometry(rows)
    out = {}
    for r in rows:
        mid = int(r["match_id"])
        key = (mid, int(r["account_id"]))
        t = pre.suffix_triggers(r, order, length)
        e = extras.get(mid)
        fb = e.get("first_blood_time") if e else None
        if fb is not None:
            t["the Patient"] = fb >= FIRST_BLOOD_LATE
            t["the Flayed Twins Acolyte"] = fb < 0
        if e is not None and e.get("all_tormentor_deaths") is not None:
            # counted off the recorded killer, not inferred from a residual
            t["the Tormented"] = e["all_tormentor_deaths"] > 0
        out[key] = t
    return out


def suffix_bonus_fn(suffix, table):
    frac = SUFFIX_BONUS[suffix] / 100.0

    def fn(mid, acct):
        return frac if table.get((mid, acct), {}).get(suffix) else 0.0
    return fn


def _zero(_mid, _acct):
    return 0.0


# ------------------------------------------------------------------------- pricing

def price(per, n_players, counts, bonus_fn, projector=project_period):
    """Expected TI period score under one coach setting, via the event-block projection."""
    return projector(series_scores(per, n_players, bonus_fn), counts)


def gain_table(per, n_players, counts, settings, projector=project_period):
    """Fractional gain of each setting over no coach, on identical draws."""
    base = price(per, n_players, counts, _zero, projector)
    return base, {name: (price(per, n_players, counts, fn, projector) / base - 1.0)
                  for name, fn in settings.items()}


def tormented_rate(extras, scope="all"):
    """the Tormented's trigger rate, counted directly off the recorded killer.

    This replaces a withdrawn heuristic. The old code took deaths that `killed_by` did not account
    for and called them "deaths to something that is not a hero", then used that as an upper bound
    on Tormentor deaths. `killed_by` is not hero-only -- OpenDota documents it only as who killed
    the player, and this window's own inventory contains creep and building killers -- so the
    residual was never the quantity it was named after, and a Tormentor death recorded IN
    `killed_by` contributes nothing to it. The residual is therefore not an upper bound on
    anything; it is counted here only to show how small it is.
    """
    key = f"{scope}_tormentor_deaths"
    vals = [e[key] for e in extras.values() if e.get(key) is not None]
    if not vals:
        return None
    n = len(vals)
    fired = sum(1 for v in vals if v)
    unrec = [e.get(f"{scope}_deaths_with_no_recorded_killer") or 0 for e in extras.values()]
    return {"matches": n,
            "matches_with_a_tormentor_death": fired,
            "trigger_rate": round(fired / n, 5),
            "rate_upper_95_rule_of_three": round(3.0 / n, 5) if not fired else None,
            "attribution": "direct: the killer recorded for the death is the Tormentor",
            "deaths_with_no_recorded_killer": sum(unrec),
            "residual_share_of_all_deaths": round(
                sum(unrec) / max(1, sum(e.get(f"{scope}_deaths") or 0
                                        for e in extras.values())), 6),
            "why_the_residual_is_not_a_bound":
                "killed_by carries creep and building killers, so an unrecorded-killer death is "
                "a parser gap, not a non-hero death; and a Tormentor death that IS recorded never "
                "enters it. It bounds neither direction."}


def breakpoint_rate(target_gain, bonus_percent, att):
    """Trigger rate a suffix would need, at a given attenuation, to match a target gain.

    Attenuation is not a fudge factor: it is measured on the suffixes that CAN be priced, and it
    is not near one. A trigger uncorrelated with performance comes out ABOVE its naive frequency
    times bonus, because the period keeps the best series and so selects periods where the trigger
    happened to fire; a trigger tied to losing comes out well below. Quoting the breakpoint at
    both ends of the measured range is the honest form of "we could not price this".
    """
    if not att or not bonus_percent:
        return None
    return target_gain / (att * bonus_percent / 100.0)


def bootstrap_gap(per, n_players, counts, name_a, name_b, table, reps=400, seed=SEED):
    """Uncertainty on the gap between two suffixes, resampling series INSIDE each event block.

    Isomorphic to production by construction: a replicate resamples series within each event,
    keeps the event identity, and is then handed to the same project_period primitive. An earlier
    version resampled within events and then flattened them into one pool before taking the
    period maximum, so the uncertainty estimator answered a different question from the estimator
    it was supposed to be quantifying.
    """
    rng = np.random.default_rng(seed)
    fa, fb = suffix_bonus_fn(name_a, table), suffix_bonus_fn(name_b, table)
    srcs = {"base": series_scores(per, n_players, _zero),
            "a": series_scores(per, n_players, fa),
            "b": series_scores(per, n_players, fb)}
    events = sorted(srcs["base"])
    ids = {ev: sorted(srcs["base"][ev]) for ev in events}
    gaps = []
    for _ in range(reps):
        pick = {ev: rng.integers(0, len(ids[ev]), size=len(ids[ev])) for ev in events}
        rep = {}
        for tag, src in srcs.items():
            rep[tag] = {ev: {n: src[ev][ids[ev][i]] for n, i in enumerate(pick[ev])}
                        for ev in events}
        base = project_period(rep["base"], counts)
        if not base:
            continue
        gaps.append((project_period(rep["a"], counts) - project_period(rep["b"], counts)) / base)
    return np.array(gaps)


def summarise_gap(draws, name_a, name_b):
    return {"comparison": f"{name_a} minus {name_b}",
            "reps": int(draws.size),
            "mean_gap": round(float(draws.mean()), 5),
            "p05": round(float(np.percentile(draws, 5)), 5),
            "p95": round(float(np.percentile(draws, 95)), 5),
            "p_a_ahead": round(float((draws > 0).mean()), 4),
            "separated_at_95": bool((draws > 0).mean() >= 0.95
                                    or (draws < 0).mean() >= 0.95)}


# ------------------------------------------------------------------- joint pricing

STACKINGS = ("additive", "multiplicative")


def joint_bonus_fn(prefix, suffix, stacking, heroes, cats, table):
    """One player-game multiplier for a prefix AND a suffix together.

    A coach is one prefix plus one suffix, always both. Pricing them separately against no-coach
    answers a question nobody is asking: the account is choosing between Elemental+Tormented and
    Elemental+Lucky, not between Tormented and Lucky in isolation. The two indicators are resolved
    on the same player-game, so the interaction term survives into the layering instead of being
    lost.
    """
    p = PREFIX_BONUS[prefix] / 100.0 if prefix else 0.0
    sfx = SUFFIX_BONUS[suffix] / 100.0 if suffix else 0.0
    flag = PREFIX_FLAG[prefix][0] if prefix else None

    def fn(mid, acct):
        ip = 1.0 if flag and cats.get(heroes.get((mid, acct)), {}).get(flag) else 0.0
        i_s = 1.0 if suffix and table.get((mid, acct), {}).get(suffix) else 0.0
        if stacking == "multiplicative":
            return (1.0 + p * ip) * (1.0 + sfx * i_s) - 1.0
        return p * ip + sfx * i_s
    return fn


def account_gain(role_inputs, bonus_for):
    """Base-weighted gain over no coach, summed across the roles the account actually holds."""
    num = den = 0.0
    for role, (per, n, counts, base) in role_inputs.items():
        num += base * (price(per, n, counts, bonus_for(role)) / base - 1.0)
        den += base
    return num / den if den else float("nan")


def period_draws(scores_by_event, counts, seed=SEED):
    """Per-draw period scores, not just their mean. The predictive distribution, event-equal.

    Each draw picks one historical event uniformly, then plays a TI-length period inside it. The
    mean of this matches project_period exactly; what it adds is the spread, which is a statement
    about how the coming period could go rather than about how well the mean is pinned down.
    Common random numbers hold across coach settings because the pools are the same series.
    """
    rng = np.random.default_rng(seed)
    events = sorted(scores_by_event)
    pools = [_event_pool(scores_by_event, e) for e in events]
    counts = np.asarray(counts)
    n, width = counts.size, int(counts.max()) if counts.size else 0
    pick = rng.integers(0, len(pools), size=n)
    u = rng.random((n, width))
    mask = np.arange(width)[None, :] < counts[:, None]
    out = np.empty(n)
    for j, pool in enumerate(pools):
        sel = pick == j
        if not sel.any():
            continue
        idx = np.minimum((u[sel] * pool.size).astype(int), pool.size - 1)
        out[sel] = np.where(mask[sel], pool[idx], -np.inf).max(axis=1)
    return out


def account_period_draws(role_inputs, bonus_for):
    """Account-level period score per draw: the three roles are summed, not averaged."""
    total = None
    for role, (per, n, counts, _base) in role_inputs.items():
        d = period_draws(series_scores(per, n, bonus_for(role)), counts)
        total = d if total is None else total + d
    return total


def describe_predictive(draws):
    q = np.percentile(draws, [10, 25, 50, 75, 90, 95])
    return {"mean": round(float(draws.mean()), 2), "p10": round(float(q[0]), 2),
            "p25": round(float(q[1]), 2), "median": round(float(q[2]), 2),
            "p75": round(float(q[3]), 2), "p90": round(float(q[4]), 2),
            "p95": round(float(q[5]), 2)}


def hierarchical_bootstrap(role_inputs, bonus_a, bonus_b, reps=400, seed=SEED):
    """Resample EVENTS with replacement, then series inside them. Both levels, not just the inner.

    The within-event bootstrap alone treats the set of tournaments as fixed and known, so it can
    only say how well each event's own series pin its own distribution down. It cannot speak to
    patch or field differences between tournaments. This adds the outer level -- but with three
    events per role, an outer resample has three distinct values to draw from, so the result is a
    coarse indication and is labelled as one rather than quoted as a precise interval.
    """
    rng = np.random.default_rng(seed)
    gaps = []
    prepared = {}
    for role, (per, n, counts, _base) in role_inputs.items():
        prepared[role] = ({"0": series_scores(per, n, bonus_a(role)),
                           "1": series_scores(per, n, bonus_b(role)),
                           "base": series_scores(per, n, _zero)}, counts)
    for _ in range(reps):
        num = den = 0.0
        for role, (srcs, counts) in prepared.items():
            events = sorted(srcs["base"])
            take = rng.integers(0, len(events), size=len(events))     # outer: events
            rep = {k: {} for k in srcs}
            for slot, e in enumerate(take):
                ev = events[e]
                ids = sorted(srcs["base"][ev])
                pick = rng.integers(0, len(ids), size=len(ids))        # inner: series
                for k in srcs:
                    rep[k][f"{slot}"] = {i: srcs[k][ev][ids[j]] for i, j in enumerate(pick)}
            base = project_period(rep["base"], counts)
            if not base:
                continue
            num += base * (project_period(rep["0"], counts)
                           - project_period(rep["1"], counts)) / base
            den += base
        if den:
            gaps.append(num / den)
    return np.array(gaps)


def leave_one_event_out(role_inputs, bonus_a, bonus_b):
    """Drop one historical event at a time and recompute. Deterministic, no resampling."""
    events = sorted({e for role, (per, n, _c, _b) in role_inputs.items()
                     for e in series_scores(per, n, _zero)})
    folds = []
    for dropped in events:
        num_a = num_b = den = 0.0
        roles = {}
        for role, (per, n, counts, _base) in role_inputs.items():
            keep = {e: v for e, v in series_scores(per, n, _zero).items() if e != dropped}
            if not keep:
                continue
            b = project_period(keep, counts)
            ga = project_period({e: v for e, v in series_scores(per, n, bonus_a(role)).items()
                                 if e != dropped}, counts) / b - 1.0
            gb = project_period({e: v for e, v in series_scores(per, n, bonus_b(role)).items()
                                 if e != dropped}, counts) / b - 1.0
            roles[role] = {"a": round(ga, 5), "b": round(gb, 5), "gap": round(ga - gb, 5)}
            num_a += b * ga
            num_b += b * gb
            den += b
        folds.append({"dropped_event": dropped,
                      "a": round(num_a / den, 5), "b": round(num_b / den, 5),
                      "gap": round((num_a - num_b) / den, 5),
                      "winner": "a" if num_a > num_b else "b",
                      "by_role": roles})
    return folds


def joint_closing(role_inputs, prefix, contenders, heroes, cats, table, priced_suffixes):
    """The comparison the account actually faces: one prefix plus one suffix, against another.

    Everything here is paired. Estimator uncertainty and the predictive distribution are kept in
    separate fields with separate names, because they answer different questions: how well the
    parameter is pinned down, versus how the coming period could actually turn out.
    """
    def bonus_for(pref, suf, stacking):
        return lambda _role: joint_bonus_fn(pref, suf, stacking, heroes, cats, table)

    out = {"prefix_held_fixed": prefix, "contenders": list(contenders), "by_stacking": {}}
    a, b = contenders
    for stacking in STACKINGS:
        fa, fb = bonus_for(prefix, a, stacking), bonus_for(prefix, b, stacking)
        ga, gb = account_gain(role_inputs, fa), account_gain(role_inputs, fb)
        # the approximation this replaces: adding two standalone gains as if the layering were
        # linear. It is not -- a bonus reorders player-games, which moves the top two of a series
        # and the best series of a period.
        pa = account_gain(role_inputs, bonus_for(prefix, None, stacking))
        sa = account_gain(role_inputs, bonus_for(None, a, stacking))
        sb = account_gain(role_inputs, bonus_for(None, b, stacking))
        da = account_period_draws(role_inputs, fa)
        db = account_period_draws(role_inputs, fb)
        diff = da - db
        grid = np.percentile(np.concatenate([da, db]), [60, 70, 80, 90, 95])
        out["by_stacking"][stacking] = {
            "joint_gain": {a: round(ga, 5), b: round(gb, 5)},
            "gap": round(ga - gb, 5),
            "winner": a if ga > gb else b,
            "standalone_sum_approximation": {
                a: round(pa + sa, 5), b: round(pa + sb, 5),
                "prefix_alone": round(pa, 5),
                "interaction_residual": {a: round(ga - pa - sa, 5), b: round(gb - pa - sb, 5)},
                "note": "exact joint minus the sum of standalone gains; nonzero because the "
                        "top-two and best-series maxima are not linear in a player-game bonus"},
            "predictive_distribution": {
                "what_this_is": "how the coming TI period could turn out, at the fitted "
                                "historical distribution. NOT estimator uncertainty.",
                a: describe_predictive(da), b: describe_predictive(db),
                "paired_difference": {
                    "mean": round(float(diff.mean()), 2),
                    "median": round(float(np.median(diff)), 2),
                    "p10": round(float(np.percentile(diff, 10)), 2),
                    "p90": round(float(np.percentile(diff, 90)), 2),
                    f"P_{a.replace(' ', '_')}_higher": round(float((diff > 0).mean()), 4),
                    "P_tie": round(float((diff == 0).mean()), 4)},
                "threshold_crossing": {
                    f"score>={int(t)}": {a: round(float((da >= t).mean()), 4),
                                         b: round(float((db >= t).mean()), 4)}
                    for t in grid}},
        }
    # joint search over everything that can be scored exactly, at the settled stacking if the two
    # agree, reported for both otherwise
    search = {}
    for stacking in STACKINGS:
        rows_ = []
        for pref in sorted(PREFIX_FLAG):
            for suf in priced_suffixes:
                rows_.append({"prefix": pref, "suffix": suf,
                              "joint_gain": round(account_gain(
                                  role_inputs, bonus_for(pref, suf, stacking)), 5)})
        rows_.sort(key=lambda r: -r["joint_gain"])
        best_suffix_at_prefix = max(
            (r for r in rows_ if r["prefix"] == prefix), key=lambda r: r["joint_gain"])
        best_prefix_at_b = max(
            (r for r in rows_ if r["suffix"] == b), key=lambda r: r["joint_gain"])
        current = next(r for r in rows_ if r["prefix"] == prefix and r["suffix"] == b)
        search[stacking] = {
            "best_known_joint": rows_[0],
            "best_suffix_with_prefix_held": best_suffix_at_prefix,
            "best_measurable_prefix_with_current_suffix": best_prefix_at_b,
            "current_setting": current,
            "gap_current_to_joint_optimum": round(
                rows_[0]["joint_gain"] - current["joint_gain"], 5),
            "top_five": rows_[:5],
            "excluded_from_search": {
                "prefixes": list(PREFIX_NO_TABLE),
                "why": "no hero category table; their figures are extrapolations, not ceilings, "
                       "so they cannot enter an exact search"}}
    out["joint_search"] = search
    return out


def scenario_minimax_regret(role_inputs, prefix, contenders, heroes, cats, table):
    """Real minimax regret over a named scenario family, not the endpoints of an interval.

    A bootstrap percentile is not a regret. Regret needs scenarios in which an action can be
    wrong. The family here is the two admissible stacking rules crossed with dropping each
    historical event, which are the modelling choices actually still open.
    """
    a, b = contenders
    scenarios = []
    for stacking in STACKINGS:
        def mk(suf, st=stacking):
            return lambda _role: joint_bonus_fn(prefix, suf, st, heroes, cats, table)
        scenarios.append({"scenario": f"{stacking} / all events",
                          a: account_gain(role_inputs, mk(a)),
                          b: account_gain(role_inputs, mk(b))})
        for fold in leave_one_event_out(role_inputs, mk(a), mk(b)):
            scenarios.append({"scenario": f"{stacking} / drop {fold['dropped_event']}",
                              a: fold["a"], b: fold["b"]})
    regret = {a: 0.0, b: 0.0}
    for sc in scenarios:
        best = max(sc[a], sc[b])
        for act in (a, b):
            regret[act] = max(regret[act], best - sc[act])
    return {"definition": "max over scenarios of (best action in that scenario minus this action)",
            "scenario_family": "stacking hypothesis x leave-one-event-out",
            "scenarios": [{k: (round(v, 5) if isinstance(v, float) else v)
                           for k, v in sc.items()} for sc in scenarios],
            "max_regret": {k: round(v, 5) for k, v in regret.items()},
            "minimax_choice": min(regret, key=regret.get)}


# ------------------------------------------------------- checking the public numbers

def replicate_frequencies(hero_rows, cats, community, min_maps=15):
    """Reproduce the community's per-player percentages from our own hero data.

    This is the test that settles what those numbers MEAN. If they are percentage frequencies of
    a player's games, our independently fetched hero table must reproduce them player by player;
    if they were counts, or shares of some other denominator, it cannot. The eight categories
    overlap and a player's eight values sum past 100, which already rules out reading any single
    value as a share of the eight.
    """
    by_player = defaultdict(list)
    for r in hero_rows:
        by_player[r["player_name"]].append(int(r["hero_id"]))
    out = {}
    for key, (flag, _kind) in PREFIX_FLAG.items():
        ck = key.lower()
        xs, ys = [], []
        for name, ids in by_player.items():
            if name not in community or ck not in community[name] or len(ids) < min_maps:
                continue
            xs.append(100.0 * sum(1 for h in ids if cats.get(h, {}).get(flag)) / len(ids))
            ys.append(community[name][ck])
        if len(xs) < 5:
            continue
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sx = (sum((v - mx) ** 2 for v in xs)) ** 0.5
        sy = (sum((v - my) ** 2 for v in ys)) ** 0.5
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        out[key] = {"players": len(xs), "our_mean_percent": round(mx, 1),
                    "their_mean_percent": round(my, 1),
                    "mean_offset": round(mx - my, 1),
                    "correlation": round(cov / (sx * sy), 3) if sx and sy else None}
    return out


def attenuation(exact_gain, rate, bonus_percent):
    """exact layered gain divided by the naive frequency x bonus it would have been priced at."""
    naive = rate * bonus_percent / 100.0
    return exact_gain / naive if naive > 0 else None


def community_rate(community, players, key):
    vals = [community[p][key] for p in players if p in community]
    return (sum(vals) / len(vals) / 100.0) if vals else None


# --------------------------------------------------------------------------- build

def build(state_path, titles_path=None, draws=DRAWS):
    rules = bl.load_rules()
    rows, _dropped, _inactive = bl.load_stats()
    with open(state_path, encoding="utf-8") as fh:
        state = json.load(fh)
    weights = banner_weights(state)
    cats = load_hero_categories()
    heroes = load_hero_maps()
    extras = load_extras()
    probs, prob_src = ex.frozen_bucket_probabilities()
    table = suffix_trigger_table(rows, extras)

    with open(COMMUNITY, encoding="utf-8") as fh:
        community = json.load(fh)["players"]
    with open(HEROES_CSV, encoding="utf-8") as fh:
        hero_rows = list(csv.DictReader(fh))
    name_of = {int(r["account_id"]): r["player_name"] for r in hero_rows}

    roles_map = bl.roles_from_roster()
    out_roles = {}
    role_matches = {}
    role_inputs = {}
    # decidable, NOT "observed to fire": a suffix whose trigger can be evaluated on our data is
    # priced even when it never fires, because a measured zero is a result and not a gap
    priced_suffixes = [s for s in SUFFIX_BONUS if any(s in v for v in table.values())]
    for role in ROLES:
        org = state["banners"][role]["canonical_team"]
        accounts = set(roles_map.get(org, {}).get(role, []))
        keep, drop = weights[role]
        if not accounts or not keep:
            out_roles[role] = {"organization": org, "priced": False,
                               "reason": "no roster accounts" if not accounts
                               else f"every banner slot is unscoreable: {drop}"}
            continue
        per = player_map_totals(rows, accounts, keep, rules)
        counts = exposure_counts(org, probs, draws)
        settings = {p: prefix_bonus_fn(p, heroes, cats) for p in PREFIX_FLAG}
        settings.update({s: suffix_bonus_fn(s, table) for s in priced_suffixes})
        base, gains = gain_table(per, len(accounts), counts, settings)

        # our own trigger rate for each prefix, over exactly the player-maps that were scored
        maps = [(m, a) for ev in per.values() for ser in ev.values()
                for m, d in ser.items() for a in d]
        att = {}
        for p, (flag, _k) in PREFIX_FLAG.items():
            rate = sum(1 for m, a in maps
                       if cats.get(heroes.get((m, a)), {}).get(flag)) / max(1, len(maps))
            att[p] = {"our_trigger_rate": round(rate, 4),
                      "exact_gain": round(gains[p], 5),
                      "naive_frequency_times_bonus": round(rate * PREFIX_BONUS[p] / 100.0, 5),
                      "attenuation": round(attenuation(gains[p], rate, PREFIX_BONUS[p]), 3)}
        worst = max(v["attenuation"] for v in att.values())

        # the three prefixes no category table covers: priced from the community frequency at the
        # most generous attenuation this role actually exhibited, so the estimate is a ceiling
        names = [name_of.get(a) for a in accounts]
        ceiling = {}
        for p in PREFIX_NO_TABLE:
            r = community_rate(community, names, p.lower())
            ceiling[p] = None if r is None else {
                "community_trigger_rate": round(r, 4),
                "gain_at_max_observed_attenuation": round(r * PREFIX_BONUS[p] / 100.0 * worst, 5),
                "basis": f"community rate x bonus x {worst}, the largest attenuation observed "
                         f"on any prefix this role CAN be scored on",
                "not_a_ceiling": "this is an extrapolation off an observed maximum, not a proven "
                                 "upper bound. Nothing rules out an untabled prefix attenuating "
                                 "harder than any tabled one; the largest value SEEN is not the "
                                 "largest value POSSIBLE."}

        role_matches[role] = (org, scored_matches(per, len(accounts)))
        role_inputs[role] = (per, len(accounts), counts, base)
        out_roles[role] = {"organization": org, "priced": True,
                           "players": len(accounts), "dropped_slots": drop,
                           "player_maps_scored": len(maps),
                           "base_expected_period_score": round(base, 3),
                           "gain": {k: round(v, 5) for k, v in sorted(
                               gains.items(), key=lambda kv: -kv[1])},
                           "prefix_attenuation": att,
                           "untabled_prefix_extrapolation": ceiling}

    # totals: the account's score is the sum over roles, so a coach is ranked on the summed gain
    totals = {}
    weighted = {r: v for r, v in out_roles.items() if v.get("priced")}
    denom = sum(v["base_expected_period_score"] for v in weighted.values())
    for k in set().union(*[set(v["gain"]) for v in weighted.values()]) if weighted else ():
        totals[k] = round(sum(v["base_expected_period_score"] * v["gain"].get(k, 0.0)
                              for v in weighted.values()) / denom, 5)
    ceilings = {}
    for p in PREFIX_NO_TABLE:
        vals = [(v["base_expected_period_score"], v["untabled_prefix_extrapolation"].get(p))
                for v in weighted.values()]
        if all(c for _b, c in vals):
            ceilings[p] = round(sum(b * c["gain_at_max_observed_attenuation"] for b, c in vals) / denom, 5)

    # Trigger rates on the right unit. Seven of the eight conditions are properties of the GAME,
    # so the trial is a match; only the Underdog varies between the two teams in one. Roles are
    # unioned rather than summed, because Core and Support are both Xtreme Gaming and share every
    # match, and adding them would count the same coin flip twice.
    units = {}
    for s_name in priced_suffixes:
        scope = SUFFIX_SCOPE[s_name]
        seen = {}
        for _role, (org_r, ms) in role_matches.items():
            for key, mid in bernoulli_units(scope, ms, org_r).items():
                acct = next((a for (m, a) in table if m == mid), None)
                if acct is None or s_name not in table[(mid, acct)]:
                    continue        # not decidable on this match: extras have not covered it yet
                seen[key] = table[(mid, acct)][s_name]
        units[s_name] = seen
    decided = {k: len(v) for k, v in units.items()}
    fired = {k: sum(1 for x in v.values() if x) for k, v in units.items()}
    suffix_rate = {k: (fired[k] / decided[k] if decided[k] else 0.0) for k in units}
    suffix_att = {k: attenuation(totals[k], suffix_rate[k], SUFFIX_BONUS[k])
                  for k in units if suffix_rate[k] > 0}
    hi_att = max(suffix_att.values()) if suffix_att else 1.0
    # a suffix that never fired is bounded by the rule of three on the MATCH count, not the
    # player-map count; the looser bound is the one the evidence actually supports
    never = {k: {"scope": SUFFIX_SCOPE[k],
                 "unique_units_decided": decided[k],
                 "units_triggered": 0,
                 "observed_rate": 0.0,
                 "rate_upper_95_rule_of_three": round(3.0 / decided[k], 5),
                 "gain_at_bound_and_max_observed_attenuation": round(
                     3.0 / decided[k] * SUFFIX_BONUS[k] / 100.0 * hi_att, 5)}
             for k in units if suffix_rate[k] == 0 and decided[k]}
    best_suffix = max(priced_suffixes, key=lambda x: totals[x]) if priced_suffixes else None
    lo, hi = (min(suffix_att.values()), max(suffix_att.values())) if suffix_att else (None, None)
    unpriced = {}
    for s_name in SUFFIX_BONUS:
        if s_name in priced_suffixes or best_suffix is None:
            continue
        b = SUFFIX_BONUS[s_name]
        unpriced[s_name] = {
            "bonus_percent": b,
            "scope": SUFFIX_SCOPE[s_name],
            "must_beat": {"suffix": best_suffix, "total_gain": totals[best_suffix]},
            "breakpoint_rate_if_uncorrelated": round(
                breakpoint_rate(totals[best_suffix], b, hi), 4),
            "breakpoint_rate_if_tied_to_losing": round(
                breakpoint_rate(totals[best_suffix], b, lo), 4),
            "measured_attenuation_range": [round(lo, 3), round(hi, 3)]}
        unpriced[s_name]["not_a_proven_exclusion"] = (
            "the breakpoints below use the largest attenuation OBSERVED on a scoreable suffix. "
            "That is not a proven maximum, so a rival is excluded only under the assumption that "
            "it does not attenuate harder than anything measured.")
    # coverage, on unique matches. Until every scored match has its extras, a suffix that depends
    # on them is PARTIAL-COVERAGE and the set is not "closed" however favourable it looks.
    all_scored = {m for _r, (_o, ms) in role_matches.items() for m in ms}
    target_ids = {m for m, _lg, _ts in fp.target_matches(fp.DEFAULT_LEAGUES)}
    complete_fetch = not (target_ids - set(extras))
    classification = {}
    for s_name in SUFFIX_BONUS:
        if s_name == "the Cruel":
            classification[s_name] = "UNAVAILABLE"
        elif s_name not in priced_suffixes:
            classification[s_name] = "UNAVAILABLE"
        elif decided.get(s_name, 0) >= len(all_scored):
            classification[s_name] = "COMPLETE"
        else:
            classification[s_name] = "PARTIAL-COVERAGE"
    coverage = {
        "unique_matches_scored": len(all_scored),
        "unique_matches_with_extras": len(all_scored & set(extras)),
        "extras_rows_fetched": len(extras),
        "extras_fetch_complete": complete_fetch,
        "note": "a suffix decided on fewer units than unique_matches_scored is PARTIAL-COVERAGE",
        "fingerprint": extras_fingerprint(extras, target_ids),
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")}
    closed = all(c in ("COMPLETE", "BOUNDED") for c in classification.values())

    # A first-blood time is a property of a professional game, not of whether our three roles
    # happened to score in it. The 84 scored matches are a small slice of the same five-league
    # population, so the event rate is bounded on every match fetched -- a far tighter and equally
    # valid bound. Both are reported; the in-sample one is the conservative fallback.
    fb = [e["first_blood_time"] for e in extras.values() if e.get("first_blood_time") is not None]
    missingness = {
        "fetch_order": "the target list is sorted by start_time and fetched in order, so a "
                       "partial run holds the CHRONOLOGICALLY EARLIEST matches and is missing "
                       "the latest ones",
        "is_missingness_ignorable": complete_fetch,
        "why_it_matters": "first-blood timing and game length move with the patch and the meta, "
                          "so a time-ordered prefix is not a random sample of the period. A "
                          "zero observed on it does not license a population-level claim.",
        "consequence": ("coverage complete: the bounds below are population bounds"
                        if complete_fetch else
                        "coverage partial: the bounds below describe the observed prefix only. "
                        "Further fetching raises the denominator AND may raise the numerator, so "
                        "completion can move these numbers in either direction, not merely "
                        "tighten them.")}
    population = {}
    if fb:
        for s_name, hit in (("the Patient", lambda x: x >= FIRST_BLOOD_LATE),
                            ("the Flayed Twins Acolyte", lambda x: x < 0)):
            n_hit = sum(1 for x in fb if hit(x))
            rate = n_hit / len(fb)
            bound = rate if n_hit else 3.0 / len(fb)
            population[s_name] = {
                "unique_matches_in_population": len(fb),
                "matches_triggered": n_hit,
                "rate_or_rule_of_three_upper_95": round(bound, 5),
                "gain_at_bound_and_max_observed_attenuation": round(
                    bound * SUFFIX_BONUS[s_name] / 100.0 * hi_att, 5),
                "basis": "all fetched matches in the same five leagues, not only the 84 scored",
                "scope_of_validity": ("population" if complete_fetch
                                      else "observed chronological prefix only")}
        population["first_blood_time_seconds"] = {
            "min": min(fb), "max": max(fb), "threshold_for_the_Patient": FIRST_BLOOD_LATE,
            "threshold_for_the_Acolyte": 0}

    tr = tormented_rate(extras, "all")
    if tr:
        population["the Tormented"] = {
            "unique_matches_in_population": tr["matches"],
            "matches_triggered": tr["matches_with_a_tormentor_death"],
            "rate_or_rule_of_three_upper_95": (tr["trigger_rate"] if tr["trigger_rate"]
                                               else tr["rate_upper_95_rule_of_three"]),
            "gain_at_bound_and_max_observed_attenuation": round(
                (tr["trigger_rate"] or tr["rate_upper_95_rule_of_three"] or 0.0)
                * SUFFIX_BONUS["the Tormented"] / 100.0 * hi_att, 5),
            "attribution": tr["attribution"],
            "basis": "all fetched matches in the same five leagues, not only the 84 scored",
            "scope_of_validity": ("population" if complete_fetch
                                  else "observed chronological prefix only")}
    if "the Cruel" in unpriced:
        unpriced["the Cruel"]["classification"] = "UNAVAILABLE"
        unpriced["the Cruel"]["why"] = (
            "the condition is positional -- a death at a team's own fountain -- and no field in "
            "the match object carries a death position. killed_by names the killer, not the "
            "place. Recovering it needs full replay parsing, not an API field.")
        unpriced["the Cruel"]["direction_of_the_error"] = (
            "a fountain death happens in games that are being lost badly, so its attenuation "
            "belongs at the LOW end of the measured range, which is where its breakpoint is "
            "least achievable")

    # The suffix grade is DERIVED, never asserted. A freeze requires that the best suffix is
    # ranked ahead of every rival that can actually be scored, and that no rival is sitting in an
    # unresolved state. While the Tormented was priced off a withdrawn heuristic, it was such a
    # rival, and the freeze it supported had to come off with it.
    scoreable = [x for x in priced_suffixes if classification[x] == "COMPLETE"]
    unresolved = [x for x, c in classification.items()
                  if c not in ("COMPLETE", "UNAVAILABLE")]
    ranked = sorted(scoreable, key=lambda x: -totals[x])
    top = ranked[0] if ranked else None
    runner = ranked[1] if len(ranked) > 1 else None
    gap = None
    if top and runner:
        gap_draws = None
        for role, v in weighted.items():
            org = v["organization"]
            accounts = set(roles_map.get(org, {}).get(role, []))
            keep, _drop = weights[role]
            per_r = player_map_totals(rows, accounts, keep, rules)
            d = bootstrap_gap(per_r, len(accounts), exposure_counts(org, probs, 3000),
                              top, runner, table)
            w = v["base_expected_period_score"] / denom
            gap_draws = w * d if gap_draws is None else gap_draws + w * d
        gap = summarise_gap(gap_draws, top, runner)
        gap["what_this_is"] = ("ESTIMATOR uncertainty on the parameter gap: how well the "
                               "historical data pins the difference down. It is NOT a statement "
                               "about how the coming period will go -- that is the predictive "
                               "distribution, reported separately under joint_closing.")
        gap["interval_endpoints"] = {
            "worst_endpoint_over_the_90_percent_bootstrap_interval": {
                top: round(max(0.0, -gap["p05"]), 5),
                runner: round(max(0.0, gap["p95"]), 5)},
            "not_minimax_regret": "these are interval endpoints, not regrets. Real minimax regret "
                                  "over a scenario family is computed in scenario_minimax_regret."}
    # A freeze needs two things, and an earlier revision only checked the first: every rival
    # scoreable, AND the leader actually separated from the runner-up. Two suffixes resting on a
    # handful of triggering games can differ by half a point and not be distinguishable at all.
    frozen = bool(top) and not unresolved and bool(gap and gap["separated_at_95"])
    suffix_grade = {
        "best_point_estimate": top,
        "runner_up": runner,
        "gap_bootstrap": gap,
        "grade": ("FROZEN FOR PERIOD 0 ON COMPLETE OBSERVED COVERAGE" if frozen
                  else "DECISION-PREFERRED / BEST-KNOWN ON CURRENT EVIDENCE"),
        "every_rival_scoreable": not unresolved,
        "unresolved_rivals": unresolved,
        "unavailable_rivals": [x for x, c in classification.items() if c == "UNAVAILABLE"],
        "why": ("every rival is scored exactly or is structurally unavailable, and the leader is "
                "separated from the runner-up at 95 percent" if frozen else
                f"cannot freeze while these are unresolved: {unresolved}" if unresolved else
                "every rival is scoreable, but the leader is NOT separated from the runner-up: "
                f"P(leader ahead) = {gap['p_a_ahead'] if gap else 'n/a'}")}

    joint = scen = hier = loo = None
    current_prefix = "Elemental"
    if role_inputs and top and runner and current_prefix in PREFIX_FLAG:
        contenders = (top, runner)
        joint = joint_closing(role_inputs, current_prefix, contenders, heroes, cats, table,
                              priced_suffixes)
        scen = scenario_minimax_regret(role_inputs, current_prefix, contenders, heroes, cats,
                                       table)

        def mk(suf, st="additive"):
            return lambda _r: joint_bonus_fn(current_prefix, suf, st, heroes, cats, table)
        hier_draws = hierarchical_bootstrap(role_inputs, mk(top), mk(runner))
        hier = summarise_gap(hier_draws, top, runner)
        hier["what_this_is"] = ("ESTIMATOR uncertainty with the event set itself resampled. "
                                "With only three historical events per role the outer level has "
                                "three distinct values to draw from, so this is a coarse "
                                "indication of between-tournament variation, not a precise "
                                "interval.")
        loo = leave_one_event_out(role_inputs, mk(top), mk(runner))
        flips = len({f["winner"] for f in loo}) > 1
        loo = {"folds": loo, "winner_flips_when_an_event_is_dropped": flips,
               "labels": {"a": top, "b": runner},
               "event_sensitive": flips}
        suffix_grade["joint_decision"] = {
            "compared": f"{current_prefix} + {top} vs {current_prefix} + {runner}",
            "additive_winner": joint["by_stacking"]["additive"]["winner"],
            "multiplicative_winner": joint["by_stacking"]["multiplicative"]["winner"],
            "stacking_robust": (joint["by_stacking"]["additive"]["winner"]
                                == joint["by_stacking"]["multiplicative"]["winner"]),
            "leave_one_event_out_robust": not flips,
            "minimax_choice": scen["minimax_choice"],
            "hierarchical_p_leader_ahead": hier["p_a_ahead"]}

    return {"state": os.path.basename(state_path), "seed": SEED, "draws": draws,
            "suffix_grade": suffix_grade,
            "joint_closing": joint,
            "scenario_minimax_regret": scen,
            "hierarchical_bootstrap": hier,
            "leave_one_event_out": loo,
            "population_bounds": population,
            "missingness": missingness,
            "suffix_classification": classification,
            "coverage": coverage,
            "all_eight_closed": closed,
            "suffix_scope": SUFFIX_SCOPE,
            "suffix_units_decided": decided,
            "suffix_units_triggered": fired,
            "suffix_trigger_rates": {k: round(v, 4) for k, v in suffix_rate.items()},
            "suffix_attenuation": {k: round(v, 3) for k, v in suffix_att.items()},
            "suffix_never_observed": never,
            "match_extras_coverage": round(len(extras) / 623.0, 3),
            "unpriced_suffixes": unpriced,
            "exposure_source": prob_src, "roles": out_roles,
            "total_gain_over_no_coach": dict(sorted(totals.items(), key=lambda kv: -kv[1])),
            "untabled_prefix_total_extrapolation": ceilings,
            "frequency_replication": replicate_frequencies(hero_rows, cats, community),
            "priced_suffixes": priced_suffixes,
            "prefix_coverage": {"exact": [p for p, (_f, k) in PREFIX_FLAG.items()
                                          if k == "exact"],
                                "lower_bound": [p for p, (_f, k) in PREFIX_FLAG.items()
                                                if k == "lower_bound"],
                                "no_category_table": list(PREFIX_NO_TABLE)},
            "tormented_attribution_all_players": tormented_rate(extras, "all"),
            "tormented_attribution_roster_only": tormented_rate(extras, "roster"),
            "community_frequencies_parsed": bool(titles_path)}


PROVENANCE = {
    "tier_2_independent_community": [
        {"id": "Kadadji1/dota2-fantasy-optimizer-2026",
         "file": "data/titles.ts",
         "carries": "all 8 prefixes and all 8 suffixes with bonuses, an independent Russian "
                    "restatement of each condition, and per-player category frequencies",
         "used_for": "the definitions, and the frequencies for the three prefixes no hero table "
                     "covers"},
        {"id": "MyKa322/fantasy-analyzer-dota2",
         "file": "dota2-fantasy-design-main/src/data/scoring.js",
         "carries": "the same 8 prefixes with the same bonuses and the same conditions; no "
                    "frequencies, and its own comment says it has no hero category data",
         "used_for": "corroboration of the definitions only"},
        {"id": "bydoodle/dota2fantasy",
         "file": "heroes.json",
         "carries": "a hand-tagged, TI2025-era hero category table (126 heroes)",
         "used_for": "our own recomputation of the hero-conditional triggers"}],
    "user_runtime_observation": [
        {"id": "operator's live client Coaching Titles panel",
         "carries": "the 8 prefixes and 8 suffixes as displayed in game, with bonuses",
         "used_for": "confirming the community definitions; it is a separate observation and is "
                     "NOT one of the two community sources"}],
    "tier_1_valve": [],
    "note": "no Valve source states the category membership of any hero, so no part of the "
            "prefix pricing is Tier 1",
}

SUFFIX_BONUS_CROSS_CHECK = {
    "checked_on": "all 8 suffixes offered by the live panel",
    "agreement": "EXACT, four-way",
    "sources": {
        "user_runtime_observation": "TARGET ACCOUNT's own client, Coaching Titles panel, read at "
                                    "high resolution: Tormented 23, Flayed Twins Acolyte 9, "
                                    "Patient 23, Underdog 6, Decisive 24, Clutch 16, Lucky 21, "
                                    "Cruel 13",
        "tier_2_a": "Kadadji1 data/titles.ts -- identical on all eight",
        "tier_2_b": "MyKa322 scoring.js SUFFIXES -- identical on all eight",
        "repository_fact_source": "fantasy_rules.json coach_titles.selectable_pool_2026 -- "
                                  "identical on all eight, and correct since it was written"},
    "defect_found": {
        "what": "coach_optimize.py kept its own hand-typed SUFFIX_BONUS literal, in which the "
                "Flayed Twins Acolyte read 30 (client 9), the Tormented 13 (client 23) and the "
                "Cruel 19 (client 13)",
        "why_it_survived": "the four suffixes priced in earlier rounds -- Underdog, Decisive, "
                           "Clutch, Lucky -- were inherited from validated code and were right, "
                           "so every regression test passed. The three wrong values belonged to "
                           "titles that had never been priced before, so nothing compared them "
                           "against anything.",
        "fix": "the literal is deleted. Both bonus tables are now read from the ruleset at import, "
               "so there is exactly one copy of the fact, and a test pins all eight values."},
}

WITHDRAWN_COMPLETION = {
    "claim": "finishing the match_extras fetch can only tighten these bounds, so completion "
             "cannot change the conclusion",
    "status": "WITHDRAWN",
    "why": "new matches raise the denominator AND may raise the numerator. A first blood after "
           "ten minutes, or a Tormentor death, can appear in any match not yet fetched. Worse, "
           "the fetch walks the target list in start_time order, so the unfetched remainder is "
           "the LATEST part of the period rather than a random subset -- exactly the situation "
           "in which a partial-sample bound may not be read as a population bound.",
    "replaced_by": "a coverage-conditional statement: under the coverage actually observed, the "
                   "reported margins hold. The population reading is licensed only when "
                   "missingness.is_missingness_ignorable is true.",
}

WITHDRAWN_CEILING = {
    "claim": "the untabled prefixes are capped by community rate x bonus x the largest observed "
             "attenuation, so that figure is their ceiling",
    "status": "WITHDRAWN as a ceiling, RETAINED as an extrapolation",
    "why": "no argument bounds an unmeasured prefix's attenuation by the maximum attenuation "
           "seen among measured ones. The largest value observed is not the largest possible.",
    "replaced_by": "untabled_prefix_total_extrapolation, named and treated as an extrapolation",
}

WITHDRAWN_STANDALONE = {
    "claim": "the Tormented is worth +3.730 percent and the Lucky +2.583 percent, therefore the "
             "account should run the Tormented",
    "status": "WITHDRAWN as a comparison, RETAINED as standalone diagnostics",
    "why": "those are each title's gain against NO COACH. The account never faces that choice: a "
           "coach is always one prefix and one suffix, so the real comparison is Elemental plus "
           "one suffix against Elemental plus the other. Composing the two best standalone titles "
           "is not a valid route to the best pair, because prefix and suffix indicators land on "
           "the same player-game and the top-two and best-series maxima are not linear in a "
           "player-game bonus.",
    "replaced_by": "joint_closing, which resolves both indicators on the same player-game and "
                   "carries the pair through the whole layering",
}

WITHDRAWN_OBJECTIVE = {
    "claim": "because changing the coach is free and reversible there is nothing to be "
             "risk-averse about, so expected score is the default objective",
    "status": "WITHDRAWN",
    "why": "free and reversible sets the switching cost and the incumbency premium to zero. It "
           "says nothing about the reward function. This compendium pays on percentile bands, and "
           "percentile_reward_values is still an open unknown, so maximising expected score is "
           "not the same as maximising the chance of clearing a band. The objective had to be "
           "chosen from the reward structure, not from the cost of switching.",
    "replaced_by": "objective sensitivity across expected score, median, downside, upper tail and "
                   "a threshold-crossing grid, with the crossing points reported where the two "
                   "distributions cross",
}

WITHDRAWN_ENDPOINTS = {
    "claim": "the negative fifth percentile and the positive ninety-fifth percentile of the "
             "bootstrap gap are the regret of each action, so this is minimax regret",
    "status": "WITHDRAWN",
    "why": "those are endpoints of an estimator-uncertainty interval. A regret needs a scenario in "
           "which an action is wrong and a best action to compare it against.",
    "replaced_by": "scenario_minimax_regret over a named family: stacking hypothesis crossed with "
                   "leave-one-event-out",
}

WITHDRAWN_POOLING = {
    "claim": "the historical pool is per event and never pooled across events",
    "status": "WITHDRAWN -- the docstring said this, the code did the opposite",
    "why": "expected_period flattened every event's series into one array and drew the TI period "
           "from it. Two defects. An event where the team played more series contributed more "
           "series to the pool, so attendance silently became weight. And a simulated period "
           "could take its maximum from a series played at a different tournament, which is not "
           "a period: a TI run happens inside one event, one field, one patch. The bootstrap "
           "repeated the same flatten, so the interval was quantifying a different estimand from "
           "the estimate.",
    "replaced_by": "project_period, an event-equal block estimator that both production and the "
                   "bootstrap call, with regression tests that duplicating or growing one event's "
                   "series pool cannot change the projection",
}

WITHDRAWN_COACH_COST = {
    "claim": "the token cost of changing a coach title has never been verified, so keeping the "
             "incumbent suffix has a cost advantage",
    "status": "WITHDRAWN",
    "why": "the ruleset already recorded the answer, from the shipped help string "
           "DOTA_FantasyCraftHelp_CoachDetails: titles may be changed freely without spending "
           "roll tokens. The operator's own client rules panel says the same. The claim was "
           "asserted from memory against a fact this repository already held -- the same failure "
           "as the hand-typed suffix bonuses.",
    "replaced_by": "coach_change_cost, recorded as free and reversible, and a decision rule that "
                   "gives the incumbent no premium",
}

COACH_CHANGE_COST = {
    "cost": "0 roll tokens",
    "reversible": True,
    "grade": "CONFIRMED",
    "sources": ["shipped client string DOTA_FantasyCraftHelp_CoachDetails, recorded in "
                "fantasy_rules.json coach_titles.confirmed: 'Titles may be changed freely "
                "without spending roll tokens.'",
                "user_runtime_observation: the operator's client rules panel states the same"],
    "consequence": "the status quo has no cost advantage, so a suffix must be chosen on its "
                   "merits alone and never kept merely because it is already saved",
}

WITHDRAWN_TORMENTOR = {
    "claim": "deaths that killed_by does not account for are deaths to something that is not a "
             "hero, so their rate is an upper bound on the Tormented's trigger rate (5.78 percent "
             "on this window)",
    "status": "WITHDRAWN",
    "why": "killed_by is not hero-only. OpenDota documents it only as who killed the player, and "
           "this window's own killer inventory contains creep and building entities. Two "
           "consequences, both fatal to the old reading: the residual is not 'non-hero deaths', "
           "and a Tormentor death that IS recorded in killed_by contributes nothing to it, so the "
           "residual does not bound Tormentor deaths from above at all. The residual's size "
           "confirms this independently -- 53 of 33,128 deaths, 0.16 percent, far too few to be "
           "every death to a tower, creep, Roshan or deny in 623 professional games.",
    "replaced_by": "direct attribution: the Tormented is counted off the recorded killer, which "
                   "makes it exactly scoreable rather than bounded",
    "consequence_at_the_time": "the freeze that rested on that bound was withdrawn with it, and "
                               "is restored only if direct counting leaves the Lucky ahead",
}

WITHDRAWN = {
    "claim": "the community frequencies admit two equally admissible readings, a percentage "
             "reading and a normalised-count reading, and the recommendation is ROBUST across "
             "both",
    "status": "WITHDRAWN",
    "why": "the second reading divides a value by the sum of the eight categories, which is not a "
           "denominator: the categories overlap, and a player's eight values routinely sum past "
           "100. The source uses the values as percentage frequencies, and our own hero data "
           "reproduces them player by player, so there is one reading, not two.",
    "replaced_by": "frequency_replication, which tests the percentage reading against our own "
                   "independently fetched hero table",
}

METHOD = {
    "layering": ["player-game score", "role score = mean over the role's players",
                 "series score = sum of the best two games", "period score = MAX over series",
                 "TI exposure = expectation over the number of series played"],
    "where_the_bonus_is_applied": "the player-game, before role averaging, so a bonus that "
                                  "correlates with how the game went is priced with that "
                                  "correlation intact",
    "paired_comparison": "common random numbers across coach settings, so a reported gain is a "
                         "paired difference and not the difference of two noisy means",
    "why_not_frequency_times_bonus": "the period keeps a maximum, so a trigger that fires on "
                                     "games the maximum discards is worth far less than its "
                                     "frequency, and one that fires on the best games is worth "
                                     "more. The measured attenuation on prefixes we can score "
                                     "exactly ranges from 0.06 to 1.8, so the naive product is "
                                     "not even reliable to within an order of magnitude.",
}


def assemble(computed, state_path):
    """The published artifact: computed numbers plus the method and provenance that bound them."""
    return {"generated_by": "ti_predict.fantasy.coach_optimize",
            "regenerate": f"python -m ti_predict.fantasy.coach_optimize --state {state_path} "
                          f"--out <this file>",
            "label": "BEST-KNOWN PROVISIONAL -- not FINAL, not a ROBUST OPTIMUM",
            "label_by_component": {
                "suffix_choice": {
                    "grade": computed["suffix_grade"]["grade"],
                    "grade_basis": computed["suffix_grade"],
                    "why": "every match in the five-league window has been fetched, so the "
                           "first-blood bounds are population bounds rather than prefix bounds. "
                           "the Lucky beats the next scoreable suffix by a factor of 2.3, and "
                           "the Patient and the Flayed Twins Acolyte are ruled out on zero "
                           "triggers in 623 matches.",
                    "not_claimed": "this is not a proven optimum over all eight. Two residuals "
                                   "are named below and neither is closed by measurement.",
                    "residual_the_Cruel": "unmeasured. It would have to fire on 13.5 percent of "
                                          "matches to compete if uncorrelated with performance, "
                                          "or 61.2 percent if tied to losing, which is where a "
                                          "fountain death belongs.",
                    "residual_the_Tormented": "bounded at 5.78 percent on complete coverage, "
                                              "which leaves it needing an attenuation about a "
                                              "third above the largest ever measured. Excluded "
                                              "under that assumption, not by proof.",
                    "what_would_reopen_it": "a measured fountain-death rate above 13.5 percent, "
                                            "or a demonstration that a rare trigger can attenuate "
                                            "past 2.4"},
                "prefix_Elemental": {
                    "grade": "BEST-KNOWN PROVISIONAL",
                    "why": "first under every construction tried, and its own figure is a lower "
                           "bound because the hero flag tags a subset of the condition",
                    "residual": "Royal, Golden and Heroic have no hero category table at all. "
                                "Their ceilings are extrapolations, not measurements, and Royal's "
                                "sits only about eight percent below Elemental's measured value. "
                                "That margin is too thin, and too dependent on an extrapolation, "
                                "to call the prefix settled."}},
            "method": METHOD,
            "provenance": PROVENANCE,
            "suffix_bonus_cross_check": SUFFIX_BONUS_CROSS_CHECK,
            "coach_change_cost": COACH_CHANGE_COST,
            "withdrawn_claims": [WITHDRAWN, WITHDRAWN_COMPLETION, WITHDRAWN_CEILING,
                                 WITHDRAWN_TORMENTOR, WITHDRAWN_POOLING,
                                 WITHDRAWN_COACH_COST, WITHDRAWN_STANDALONE,
                                 WITHDRAWN_OBJECTIVE, WITHDRAWN_ENDPOINTS],
            "withdrawn_claim": WITHDRAWN,
            "exact_pricing": computed}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--state", required=True)
    a.add_argument("--out")
    a.add_argument("--draws", type=int, default=DRAWS)
    a.add_argument("--raw", action="store_true", help="computed block only, without the narrative")
    a = a.parse_args(argv)
    doc = build(a.state, draws=a.draws)
    if not a.raw:
        doc = assemble(doc, a.state)
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
