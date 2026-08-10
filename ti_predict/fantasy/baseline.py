"""PHASE 3 public baseline: what the TI2026 fantasy scoring function does to real recent matches.

This is deliberately not a recommendation engine. It answers one question -- given the confirmed
scoring structure and the corroborated coefficients, how much would each team's core pair, mid and
support pair have scored over the last five top-tier events -- and it answers it at the four levels
the ruleset actually uses:

    per-map player score  ->  role score (mean over the role's players)
    role score per series ->  the top two maps of that series
    role score per period ->  the BEST series, not the sum
    exposure              ->  the number of eligible series, i.e. extreme-value draws

Two rules are still unresolved and are therefore carried as hypotheses rather than choices:
the top-two maps may be summed or averaged, and Deaths may or may not floor at zero. Every output
is produced under both and the spread between them is reported. Nothing here picks one.

The emblem stats are random draws in the real game, so a team cannot be scored against a known
banner. What is computed instead is the ENVELOPE: for each colour slot on a role's banner, the
best stat available in that colour's pool. That is an upper bound on what crafting could reach, and
it is the right quantity for comparing teams before any rolling has happened.
"""
import argparse
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict

from ti_predict.fantasy import questions as fq

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
PROC = os.path.join(REPO, "data", "ti2026", "processed")
STATS_CSV = os.path.join(PROC, "fantasy", "player_map_stats.csv")
UNIVERSE = os.path.join(PROC, "universe_maps.csv")
CANONICAL = os.path.join(INPUTS, "canonical_identity.csv")
ROSTER_EVENTS = os.path.join(INPUTS, "roster_events.csv")

SEED = 20260813
BOOTSTRAP = 400
# The stat a fantasy emblem tracks, expressed over the columns this project actually fetches.
# Watchers and Lotuses are absent by construction: no public source carries them per player.
STAT_COLUMNS = {
    "kills": ("kills",), "deaths": ("deaths",), "creep_score": ("last_hits", "denies"),
    "gpm": ("gold_per_min",), "tower_kills": ("towers_killed",), "madstone": ("madstone",),
    "wards_placed": ("obs_placed",), "camps_stacked": ("camps_stacked",),
    "runes_grabbed": ("rune_pickups",), "smokes_used": ("smokes_used",),
    "roshan_kills": ("roshans_killed",), "teamfight_participation": ("teamfight_participation",),
    "stuns": ("stuns",), "first_blood": ("firstblood_claimed",), "courier_kills": ("courier_kills",),
}
UNAVAILABLE = ("watchers_taken", "lotuses_grabbed", "tormentor_kills")


def _f(row, key):
    v = row.get(key, "")
    if v in ("", "None", None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_rules(path=None):
    r = fq.load_rules(path)
    coef = {s["stat_id"]: s for s in r["stats"]["list"]}
    layout = r["emblems"]["slot_layout"]["period_0_color_composition"]
    pools = r["stats"]["by_color"]
    return {"coef": coef, "layout": layout, "pools": pools,
            "deaths_credit": coef["deaths"]["starting_points"]}


def roster_override(path=None):
    """outgoing account id -> incoming account id, from the tracked lock-period roster audit.

    Without this the baseline would rank a player who is not eligible to play: canonical_identity
    is derived from match data, so a replacement signed days before the event is simply absent
    from it while the departed player is still present.
    """
    from ti_predict import rosters
    audit = rosters.roster_audit(path)
    return {int(c["outgoing"]["account_id"]): (int(c["incoming"]["account_id"]),
                                               c["incoming"]["player"], c["organization"])
            for c in audit["changed"]}


def load_stats(stats_path=None, universe_path=None):
    """Parsed player-map rows joined to their series, with the roster override applied."""
    stats_path = stats_path or STATS_CSV
    universe_path = universe_path or UNIVERSE
    if not os.path.exists(stats_path):
        raise SystemExit(f"player stats not found: {stats_path}; "
                         "run python -m ti_predict.fantasy.fetch_player_stats")
    series = {}
    with open(universe_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            series[int(r["match_id"])] = (r["leagueid"], r["series_id"] or f"m{r['match_id']}")
    swap = roster_override()
    rows, dropped = [], 0
    with open(stats_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["parsed"] != "1":
                dropped += 1
                continue
            mid = int(r["match_id"])
            if mid not in series:
                dropped += 1
                continue
            acct = int(r["account_id"])
            if acct in swap:
                # The departed player's history must not be inherited by the replacement, and must
                # not be scored for the organisation either. Drop it and let the sample speak.
                dropped += 1
                continue
            r["_league"], r["_series"] = series[mid]
            rows.append(r)
    if not rows:
        raise SystemExit("no parsed player-map rows survived filtering")
    return rows, dropped, swap


def assign_roles(rows):
    """Split each organisation's players into the fantasy roles: 2 core, 1 mid, 2 support.

    Rule, in order: rank by median last hits per map; the two highest are the cores, the two lowest
    are the supports, and of the remaining pair the mid is whichever bottles more runes. Reported
    with the margin that separated the mid from the offlaner so a thin call is visible rather than
    silent.
    """
    by_org = defaultdict(lambda: defaultdict(list))
    names = {}
    for r in rows:
        by_org[r["organization"]][int(r["account_id"])].append(r)
        names[int(r["account_id"])] = r["player_name"]
    out, notes = {}, []
    for org, players in sorted(by_org.items()):
        med = {a: statistics.median([_f(x, "last_hits") or 0 for x in rs])
               for a, rs in players.items() if len(rs) >= 3}
        if len(med) < 5:
            notes.append({"organization": org, "issue": "fewer than five players with 3+ maps",
                          "players_with_sample": len(med)})
            continue
        order = sorted(med, key=lambda a: -med[a])
        cores_pool, supports = order[:3], order[3:5]
        runes = {a: statistics.median([_f(x, "rune_pickups") or 0 for x in players[a]])
                 for a in cores_pool}
        mid = max(cores_pool, key=lambda a: runes[a])
        cores = [a for a in cores_pool if a != mid]
        second = sorted((runes[a] for a in cores_pool), reverse=True)[1]
        out[org] = {"core": cores, "mid": [mid], "support": supports}
        notes.append({"organization": org, "mid": names[mid],
                      "mid_rune_margin": round(runes[mid] - second, 2),
                      "core": [names[a] for a in cores],
                      "support": [names[a] for a in supports]})
    return out, notes


def map_score(row, stat, rules, deaths_floor):
    """Points a single emblem of `stat` would earn this player on this map, before multipliers."""
    cols = STAT_COLUMNS.get(stat)
    if not cols:
        return None
    vals = [_f(row, c) for c in cols]
    if any(v is None for v in vals):
        return None
    raw = sum(vals)
    c = rules["coef"][stat]
    if stat == "deaths":
        s = rules["deaths_credit"] - raw * c["points_per_unit"]
        return max(0.0, s) if deaths_floor else s
    if stat == "teamfight_participation":
        return min(1.0, raw) * c["maximum_points"]
    return raw * c["points_per_unit"]


def role_period_scores(rows, accounts, stat, rules, top_two, deaths_floor):
    """Per-league best-series score for one role and one stat: the four levels, in order."""
    per_series = defaultdict(lambda: defaultdict(dict))     # league -> series -> match -> [scores]
    for r in rows:
        if int(r["account_id"]) not in accounts:
            continue
        s = map_score(r, stat, rules, deaths_floor)
        if s is None:
            continue
        per_series[r["_league"]][r["_series"]].setdefault(r["match_id"], []).append(s)
    out = {}
    for league, ser in per_series.items():
        best = None
        for maps in ser.values():
            # role score for a map is the mean over the role's players who played it
            per_map = sorted((sum(v) / len(v) for v in maps.values()), reverse=True)[:2]
            if not per_map:
                continue
            agg = sum(per_map) if top_two == "sum" else sum(per_map) / len(per_map)
            best = agg if best is None else max(best, agg)
        if best is not None:
            out[league] = best
    return out


def envelope(rows, roles, rules, top_two="sum", deaths_floor=False):
    """For each organisation and role, the best stat in each of that banner's colour slots."""
    res = []
    for org, assign in sorted(roles.items()):
        for role, accounts in assign.items():
            colours = rules["layout"][role]
            acct = set(accounts)
            slots, total = [], 0.0
            for colour in colours:
                pool = [s for s in rules["pools"][colour]
                        if s in STAT_COLUMNS and s not in UNAVAILABLE]
                best, best_stat, best_by_league = -math.inf, None, {}
                for stat in pool:
                    by_league = role_period_scores(rows, acct, stat, rules, top_two, deaths_floor)
                    if not by_league:
                        continue
                    m = sum(by_league.values()) / len(by_league)
                    if m > best:
                        best, best_stat, best_by_league = m, stat, by_league
                if best_stat is None:
                    continue
                slots.append({"colour": colour, "stat": best_stat, "mean_best_series": round(best, 1),
                              "leagues": len(best_by_league),
                              "by_league": {k: round(v, 1) for k, v in best_by_league.items()}})
                total += best
            if len(slots) == len(colours):
                res.append({"organization": org, "role": role, "players": sorted(acct),
                            "slots": slots, "envelope_total": round(total, 1)})
    return res


def uncertainty(entry, seed=SEED, draws=BOOTSTRAP):
    """Bootstrap the envelope total over the events, which is the unit of independent exposure."""
    rng = random.Random(seed)
    leagues = sorted({k for s in entry["slots"] for k in s["by_league"]})
    if len(leagues) < 2:
        return {"se": None, "p10": None, "p90": None, "events": len(leagues)}
    tot = []
    for _ in range(draws):
        pick = [leagues[rng.randrange(len(leagues))] for _ in leagues]
        vals = []
        for lg in pick:
            vals.append(sum(s["by_league"].get(lg, 0.0) for s in entry["slots"]))
        tot.append(sum(vals) / len(vals))
    tot.sort()
    return {"se": round(statistics.pstdev(tot), 1), "p10": round(tot[int(.10 * len(tot))], 1),
            "p90": round(tot[int(.90 * len(tot))], 1), "events": len(leagues)}


def build(top_two="sum", deaths_floor=False):
    rules = load_rules()
    rows, dropped, swap = load_stats()
    roles, notes = assign_roles(rows)
    env = envelope(rows, roles, rules, top_two, deaths_floor)
    for e in env:
        e["uncertainty"] = uncertainty(e)
    env.sort(key=lambda e: -e["envelope_total"])
    return {"hypothesis": {"top_two": top_two, "deaths_floor": deaths_floor},
            "rows_used": len(rows), "rows_dropped": dropped,
            "roster_overrides": {str(k): v[1] for k, v in swap.items()},
            "organizations": len(roles), "role_notes": notes, "ranking": env,
            "unavailable_stats": list(UNAVAILABLE),
            "status": "PRELIMINARY",
            "why_preliminary": "Four scoring semantics are unresolved, the period-1 slot count is "
                               "unknown, traits and coach titles are not modelled, and the emblem "
                               "stats are random draws rather than choices. This ranks teams by an "
                               "upper envelope over ideal rolls, which is a comparison, not a pick."}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--top-two", choices=("sum", "mean"), default="sum")
    a.add_argument("--deaths-floor", action="store_true")
    a.add_argument("--out", default="")
    a.add_argument("--top", type=int, default=10)
    a = a.parse_args(argv)
    r = build(a.top_two, a.deaths_floor)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    print(f"PRELIMINARY envelope, top_two={a.top_two}, deaths_floor={a.deaths_floor}: "
          f"{r['rows_used']} parsed player-maps, {r['organizations']} organisations")
    for e in r["ranking"][:a.top]:
        u = e["uncertainty"]
        stats = " + ".join(f"{s['colour'][0].upper()}:{s['stat']}" for s in e["slots"])
        print(f"  {e['envelope_total']:>9.1f}  se {str(u['se']):>7}  "
              f"{e['organization']:<18} {e['role']:<8} {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
