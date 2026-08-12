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

SEED = 20260812
DRAWS = 4000
ROLES = ("core", "mid", "support")

HERO_TABLE = os.path.join("data", "ti2026", "inputs", "fantasy", "hero_categories.json")
COMMUNITY = os.path.join("data", "ti2026", "inputs", "fantasy",
                         "community_prefix_frequencies.json")
EXTRAS_CSV = os.path.join(fp.FANTASY_PROC, "match_extras.csv")
HEROES_CSV = os.path.join(fp.FANTASY_PROC, "player_map_heroes.csv")

PREFIX_BONUS = {"Crimson": 6, "Cerulean": 11, "Emerald": 6, "Royal": 10,
                "Golden": 8, "Elemental": 8, "Otherworldly": 7, "Heroic": 9}
# how each 2026 condition maps onto the community table's flags, and how tightly
PREFIX_FLAG = {"Crimson": ("isred", "exact"), "Cerulean": ("isblue", "exact"),
               "Emerald": ("isgreen", "exact"),
               "Elemental": ("isaquatic", "lower_bound"),
               "Otherworldly": ("isundead", "lower_bound")}
PREFIX_NO_TABLE = ("Royal", "Golden", "Heroic")

SUFFIX_BONUS = {"the Underdog": 6, "the Decisive": 24, "the Clutch": 16, "the Lucky": 21,
                "the Patient": 23, "the Flayed Twins Acolyte": 30, "the Tormented": 13,
                "the Cruel": 19}
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


def expected_period(scores_by_event, counts):
    """E[max over the series actually played], given a drawn series count per period.

    The pool is per event and never pooled across events: pooling would reward a team simply for
    having attended more tournaments, which says nothing about how it will do at TI.
    """
    pool = np.array([s for ev in scores_by_event.values() for s in ev.values()], dtype=float)
    if pool.size == 0:
        return float("nan")
    rng = np.random.default_rng(SEED)
    out = np.empty(len(counts))
    for i, k in enumerate(counts):
        idx = rng.integers(0, pool.size, size=int(k))
        out[i] = pool[idx].max()
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

def price(per, n_players, counts, bonus_fn):
    return expected_period(series_scores(per, n_players, bonus_fn), counts)


def gain_table(per, n_players, counts, settings):
    """Fractional gain of each setting over no coach, on identical draws."""
    base = price(per, n_players, counts, _zero)
    return base, {name: (price(per, n_players, counts, fn) / base - 1.0)
                  for name, fn in settings.items()}


def tormented_bound(extras, scope="all"):
    """Upper bound on the Tormented's trigger rate.

    killed_by credits enemy heroes only. A death it does not account for is a death to something
    that is not a hero -- a creep, Roshan, a tower, or a Tormentor. That is a genuine upper bound,
    and where the count is zero it is an exact negative: nobody in that game died to a Tormentor.
    """
    key = f"{scope}_unattributed_deaths"
    vals = [e[key] for e in extras.values() if e.get(key) is not None]
    if not vals:
        return None
    n = len(vals)
    return {"matches": n,
            "matches_with_any_unattributed_death": sum(1 for v in vals if v),
            "upper_bound_trigger_rate": round(sum(1 for v in vals if v) / n, 4),
            "exact_negatives": sum(1 for v in vals if not v),
            "note": "an upper bound; every zero is an exact negative"}


def breakpoint_rate(gain_reference, bonus_percent, base, per, n_players, counts, table,
                    probe="the Lucky"):
    """Trigger rate at which a suffix would have to match the incumbent's delivered gain.

    Calibrated on a suffix we CAN price, so the conversion from rate to gain carries the same
    max-over-series attenuation instead of assuming the naive frequency times bonus.
    """
    probe_rate = sum(1 for v in table.values() if v.get(probe)) / max(1, len(table))
    probe_gain = price(per, n_players, counts, suffix_bonus_fn(probe, table)) / base - 1.0
    if probe_gain <= 0:
        return None
    # gain is very nearly linear in the rate at a fixed bonus, so scale off the calibrated probe
    per_rate_per_point = probe_gain / (probe_rate * SUFFIX_BONUS[probe])
    return gain_reference / (per_rate_per_point * bonus_percent)


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
    priced_suffixes = [s for s in SUFFIX_BONUS if any(v.get(s) for v in table.values())]
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
                "gain_ceiling": round(r * PREFIX_BONUS[p] / 100.0 * worst, 5),
                "basis": f"community rate x bonus x {worst}, the largest attenuation measured "
                         f"on any prefix this role CAN be scored on"}

        out_roles[role] = {"organization": org, "priced": True,
                           "players": len(accounts), "dropped_slots": drop,
                           "player_maps_scored": len(maps),
                           "base_expected_period_score": round(base, 3),
                           "gain": {k: round(v, 5) for k, v in sorted(
                               gains.items(), key=lambda kv: -kv[1])},
                           "prefix_attenuation": att,
                           "untabled_prefix_ceiling": ceiling}

    # totals: the account's score is the sum over roles, so a coach is ranked on the summed gain
    totals = {}
    weighted = {r: v for r, v in out_roles.items() if v.get("priced")}
    denom = sum(v["base_expected_period_score"] for v in weighted.values())
    for k in set().union(*[set(v["gain"]) for v in weighted.values()]) if weighted else ():
        totals[k] = round(sum(v["base_expected_period_score"] * v["gain"].get(k, 0.0)
                              for v in weighted.values()) / denom, 5)
    ceilings = {}
    for p in PREFIX_NO_TABLE:
        vals = [(v["base_expected_period_score"], v["untabled_prefix_ceiling"].get(p))
                for v in weighted.values()]
        if all(c for _b, c in vals):
            ceilings[p] = round(sum(b * c["gain_ceiling"] for b, c in vals) / denom, 5)

    return {"state": os.path.basename(state_path), "seed": SEED, "draws": draws,
            "exposure_source": prob_src, "roles": out_roles,
            "total_gain_over_no_coach": dict(sorted(totals.items(), key=lambda kv: -kv[1])),
            "untabled_prefix_total_ceiling": ceilings,
            "frequency_replication": replicate_frequencies(hero_rows, cats, community),
            "priced_suffixes": priced_suffixes,
            "prefix_coverage": {"exact": [p for p, (_f, k) in PREFIX_FLAG.items()
                                          if k == "exact"],
                                "lower_bound": [p for p, (_f, k) in PREFIX_FLAG.items()
                                                if k == "lower_bound"],
                                "no_category_table": list(PREFIX_NO_TABLE)},
            "tormented_bound_all_players": tormented_bound(extras, "all"),
            "tormented_bound_roster_only": tormented_bound(extras, "roster"),
            "community_frequencies_parsed": bool(titles_path)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--state", required=True)
    a.add_argument("--out")
    a.add_argument("--draws", type=int, default=DRAWS)
    a = a.parse_args(argv)
    doc = build(a.state, draws=a.draws)
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
