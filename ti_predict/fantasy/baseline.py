"""PHASE 3 public baseline: what the TI2026 fantasy scoring function does to real recent matches.

This is deliberately not a recommendation engine. It answers one question -- given the confirmed
scoring structure and the corroborated coefficients, how much would each team's core pair, mid and
support pair have scored over the last five top-tier events -- and it answers it at the four levels
the ruleset actually uses:

    per-map player score  ->  role score (mean over the role's players)
    role score per series ->  the top two maps of that series
    role score per period ->  the BEST series, not the sum
    exposure              ->  the number of eligible series, i.e. extreme-value draws

Unresolved rules are carried as switches rather than choices, and every one of them is measured
rather than argued about (see sensitivity.py). One of them turned out not to matter: with every
series contributing at least two maps, which is the TI best-of-three condition, summing the top two
maps and averaging them differ by exactly a factor of two, so no comparison anywhere in the decision
can see the difference.

The emblem stats are random draws in the real game, so a team cannot be scored against a known
banner. What is computed instead is the ENVELOPE: the best legal stat set for the banner's colour
layout, scored as a unit. That is an upper bound on what crafting could reach, and it is the right
quantity for comparing teams before any rolling has happened.
"""
import argparse
import csv
import itertools
import json
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


# Candidate shapes for the Teamfight Participation curve. `linear` is the working hypothesis: the
# public 2026 calculator applies the plain product, and its stored inputs were shown to be OpenDota's
# teamfight_participation field exactly. The other two are deliberate stress shapes -- one that pays
# low participation more generously, one that pays it much less -- kept so the choice of curve can be
# shown not to matter rather than assumed not to.
TFP_CURVES = {"linear": lambda p: p, "concave": lambda p: p ** 0.5, "convex": lambda p: p ** 2}


def map_score(row, stat, rules, deaths_floor, tfp_curve="linear"):
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
        return TFP_CURVES[tfp_curve](min(1.0, max(0.0, raw))) * c["maximum_points"]
    return raw * c["points_per_unit"]


def role_period_scores(rows, accounts, stat, rules, top_two, deaths_floor,
                       min_series_maps=2, tfp_curve="linear"):
    """Per-league best-series score for one role and one stat: the four levels, in order.

    `min_series_maps` exists because the training window is not the target format. Every TI2026
    Swiss and elimination series is a best-of-three, so every series there contributes at least two
    maps; a quarter of the series in the recent-form window are best-of-ones. Counting those would
    let a format that cannot occur at TI drive the estimate, and -- see the note in
    scoring_pipeline -- it is the only mechanism by which summing and averaging the top two maps can
    differ at all. The default of 2 is the TI condition, not a filter chosen for convenience.
    """
    per_series = defaultdict(lambda: defaultdict(dict))     # league -> series -> match -> [scores]
    for r in rows:
        if int(r["account_id"]) not in accounts:
            continue
        s = map_score(r, stat, rules, deaths_floor, tfp_curve)
        if s is None:
            continue
        per_series[r["_league"]][r["_series"]].setdefault(r["match_id"], []).append(s)
    out = {}
    for league, ser in per_series.items():
        best = None
        for maps in ser.values():
            if len(maps) < min_series_maps:
                continue
            # role score for a map is the mean over the role's players who played it
            per_map = sorted((sum(v) / len(v) for v in maps.values()), reverse=True)[:2]
            if not per_map:
                continue
            agg = sum(per_map) if top_two == "sum" else sum(per_map) / len(per_map)
            best = agg if best is None else max(best, agg)
        if best is not None:
            out[league] = best
    return out


def series_table(rows, accounts, rules, top_two="sum", deaths_floor=False, min_series_maps=2,
                 tfp_curve="linear"):
    """{league: {series: {stat: role score for that series}}} -- the per-series layer, kept whole.

    Kept whole because a War Banner is scored as ONE thing. Taking the best series separately for
    each emblem and adding those up is a sum of maxima, which is not reachable: the period keeps a
    single series and every emblem on the banner scores from that same series. Only after the
    banner's stats are chosen can the maximum be taken.
    """
    stats = [s for s in STAT_COLUMNS if s not in UNAVAILABLE]
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        if int(r["account_id"]) not in accounts:
            continue
        for stat in stats:
            s = map_score(r, stat, rules, deaths_floor, tfp_curve)
            if s is not None:
                per[r["_league"]][r["_series"]][stat].setdefault(r["match_id"], []).append(s)
    out = defaultdict(dict)
    for league, ser in per.items():
        for sid, by_stat in ser.items():
            maps = max((len(v) for v in by_stat.values()), default=0)
            if maps < min_series_maps:
                continue
            row = {}
            for stat, by_map in by_stat.items():
                per_map = sorted((sum(v) / len(v) for v in by_map.values()), reverse=True)[:2]
                if per_map:
                    row[stat] = sum(per_map) if top_two == "sum" else sum(per_map) / len(per_map)
            if row:
                out[league][sid] = row
    return {k: dict(v) for k, v in out.items()}


def _combinations(colours, pools):
    """Every legal stat assignment for a banner: distinct stats, honouring the colour layout."""
    wanted = {c: colours.count(c) for c in set(colours)}
    per_colour = []
    for colour, k in sorted(wanted.items()):
        pool = [s for s in pools[colour] if s in STAT_COLUMNS and s not in UNAVAILABLE]
        per_colour.append([tuple(sorted(c)) for c in itertools.combinations(pool, k)])
    return [tuple(sorted(s for grp in combo for s in grp))
            for combo in itertools.product(*per_colour)]


def banner_period_scores(table, combo):
    """Per-league period score for one banner: the best SERIES total, not the sum of best series."""
    out = {}
    for league, ser in table.items():
        best = None
        for row in ser.values():
            if not all(s in row for s in combo):
                continue
            tot = sum(row[s] for s in combo)
            best = tot if best is None else max(best, tot)
        if best is not None:
            out[league] = best
    return out


def best_banner(table, colours, pools):
    """The legal stat set with the highest mean period score, and that set's per-league scores."""
    best = None
    for combo in _combinations(colours, pools):
        by_league = banner_period_scores(table, combo)
        if not by_league:
            continue
        mean = sum(by_league.values()) / len(by_league)
        if best is None or mean > best[0]:
            best = (mean, combo, by_league)
    return best


def envelope(rows, roles, rules, top_two="sum", deaths_floor=False, min_series_maps=2,
             tfp_curve="linear"):
    """For each organisation and role, the best legal stat set for that banner.

    A banner may not carry the same stat twice, and -- more importantly -- the whole banner scores
    from ONE series, so the stat set and the winning series have to be chosen together. Every legal
    combination is enumerated and scored as a unit; the counts are small (75 for core, 120 for mid,
    30 for support once the unobtainable stats are removed).
    """
    res = []
    for org, assign in sorted(roles.items()):
        for role, accounts in assign.items():
            colours = rules["layout"][role]
            acct = set(accounts)
            table = series_table(rows, acct, rules, top_two, deaths_floor, min_series_maps,
                                 tfp_curve)
            best = best_banner(table, colours, rules["pools"])
            if not best:
                continue
            mean, combo, by_league = best
            res.append({"organization": org, "role": role, "players": sorted(acct),
                        "stats": list(combo), "colours": list(colours),
                        "slots": [{"stat": s} for s in combo],
                        "leagues": len(by_league),
                        "by_league": {k: round(v, 1) for k, v in by_league.items()},
                        "series_scores": series_totals(table, combo),
                        "envelope_total": round(mean, 1)})
    return res


def rank_probabilities(entries, seed=SEED, draws=BOOTSTRAP):
    """P(rank 1) and P(top 3) per organisation within a role, by a paired event bootstrap.

    Paired: the same resampled set of events is applied to every organisation in the draw. Resampling
    each team independently would break the comparison, because the events are a shared source of
    variation -- a patch or a field is common to everyone who played that event.
    """
    rng = random.Random(seed)
    leagues = sorted({lg for e in entries for lg in e["by_league"]})
    if len(leagues) < 2 or len(entries) < 2:
        return {e["organization"]: {"p_rank1": None, "p_top3": None} for e in entries}
    counts = {e["organization"]: [0, 0] for e in entries}
    for _ in range(draws):
        pick = [leagues[rng.randrange(len(leagues))] for _ in leagues]
        tot = []
        for e in entries:
            vals = [e["by_league"][lg] for lg in pick if lg in e["by_league"]]
            tot.append((sum(vals) / len(vals) if vals else float("-inf"), e["organization"]))
        tot.sort(key=lambda t: -t[0])
        for i, (_v, org) in enumerate(tot):
            if i == 0:
                counts[org][0] += 1
            if i < 3:
                counts[org][1] += 1
    return {org: {"p_rank1": round(c[0] / draws, 4), "p_top3": round(c[1] / draws, 4)}
            for org, c in counts.items()}


def series_totals(table, combo):
    """Every series' banner total, kept for the extreme-value work; the period keeps only the max."""
    out = []
    for ser in table.values():
        for row in ser.values():
            if all(s in row for s in combo):
                out.append(round(sum(row[s] for s in combo), 1))
    return sorted(out, reverse=True)


def uncertainty(entry, seed=SEED, draws=BOOTSTRAP):
    """Bootstrap the envelope total over the events, which is the unit of independent exposure."""
    rng = random.Random(seed)
    leagues = sorted(entry["by_league"])
    if len(leagues) < 2:
        return {"se": None, "p10": None, "p90": None, "events": len(leagues)}
    tot = []
    for _ in range(draws):
        pick = [leagues[rng.randrange(len(leagues))] for _ in leagues]
        vals = [entry["by_league"].get(lg, 0.0) for lg in pick]
        tot.append(sum(vals) / len(vals))
    tot.sort()
    return {"se": round(statistics.pstdev(tot), 1), "p10": round(tot[int(.10 * len(tot))], 1),
            "p90": round(tot[int(.90 * len(tot))], 1), "events": len(leagues)}


def coverage(stats_path=None):
    """How much of the target window the stat table actually holds, measured from the table itself.

    Deliberately not read from the fetcher's provenance file: that file is written when a run ends,
    so during a long or interrupted pull it describes an earlier run. Counting the match ids present
    cannot go stale.
    """
    from ti_predict.fantasy import fetch_player_stats as fp
    targets = {t[0] for t in fp.target_matches(fp.DEFAULT_LEAGUES)}
    have = fp.done_matches(stats_path)
    covered = len(targets & have)
    frac = covered / len(targets) if targets else 0.0
    return {"matches_covered": covered, "matches_targeted": len(targets),
            "coverage": round(frac, 4), "complete": frac >= fp.MIN_COVERAGE}


def build(top_two="sum", deaths_floor=False, min_series_maps=2, tfp_curve="linear"):
    rules = load_rules()
    rows, dropped, swap = load_stats()
    roles, notes = assign_roles(rows)
    env = envelope(rows, roles, rules, top_two, deaths_floor, min_series_maps, tfp_curve)
    for e in env:
        e["uncertainty"] = uncertainty(e)
    for role in ("core", "mid", "support"):
        grp = [e for e in env if e["role"] == role]
        rp = rank_probabilities(grp)
        for e in grp:
            e["rank_probability"] = rp[e["organization"]]
    env.sort(key=lambda e: -e["envelope_total"])
    return {"hypothesis": {"top_two": top_two, "deaths_floor": deaths_floor,
                           "min_series_maps": min_series_maps,
                           "tfp_curve": tfp_curve},
            "input_coverage": coverage(),
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
    a.add_argument("--tfp-curve", choices=tuple(TFP_CURVES), default="linear")
    a.add_argument("--min-series-maps", type=int, default=2,
                   help="skip series shorter than this; 2 is the TI best-of-three condition")
    a.add_argument("--out", default="")
    a.add_argument("--top", type=int, default=10)
    a = a.parse_args(argv)
    r = build(a.top_two, a.deaths_floor, a.min_series_maps, a.tfp_curve)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    print(f"PRELIMINARY envelope, top_two={a.top_two}, deaths_floor={a.deaths_floor}: "
          f"{r['rows_used']} parsed player-maps, {r['organizations']} organisations")
    for e in r["ranking"][:a.top]:
        u = e["uncertainty"]
        stats = " + ".join(e["stats"])
        print(f"  {e['envelope_total']:>9.1f}  se {str(u['se']):>7}  "
              f"{e['organization']:<18} {e['role']:<8} {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
