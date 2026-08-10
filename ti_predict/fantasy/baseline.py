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

from ti_predict.fantasy import build_roster_positions as brp
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
# A role needs qualifying series from at least this many distinct events before it is
# ranked. One event is a single field on a single patch, which is not a sample.
MIN_EVENTS = 2
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


def excluded_accounts(path=None):
    """Account ids that may never enter a fantasy roster, from the tracked position table.

    A player replaced before the event is marked inactive there. His history must not be scored for
    the organisation and must not be inherited by his replacement: the replacement is a different
    player, and pretending otherwise would put a number on someone who has not played.
    """
    return brp.inactive_accounts(path)


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
    inactive = excluded_accounts()
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
            if int(r["account_id"]) in inactive:
                dropped += 1
                continue
            r["_league"], r["_series"] = series[mid]
            rows.append(r)
    if not rows:
        raise SystemExit("no parsed player-map rows survived filtering")
    return rows, dropped, inactive


def roles_from_roster(path=None):
    """The authoritative role mapping: Core = positions 1 and 3, Mid = 2, Support = 4 and 5.

    Read from the tracked position table, which is built from the roster of record. Positions are a
    fact about the roster; they are never recovered from statistics here.
    """
    return brp.load_positions(path)


def assign_roles_from_statistics(rows):
    """EXPLORATORY ONLY -- guesses roles from play patterns. NOT an input to any ranking.

    Kept for one purpose: checking that the authoritative table's roles are consistent with how the
    players actually play, so a transcription error in the position table would show up rather than
    propagate. If this disagrees with the roster of record, the roster of record wins and the
    disagreement is a signal to re-check the table, never a reason to override it.

    Rule, in order: rank by median last hits per map; the two highest are the cores, the two lowest
    are the supports, and of the remaining pair the mid is whichever bottles more runes.
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
    """{league: {series: {stat: role score}}} plus a sample accounting -- the per-series layer.

    Two rules are enforced here and both change the numbers materially.

    Kept whole: a War Banner is scored as ONE thing. Taking the best series separately for each
    emblem and adding those up is a sum of maxima, which is not reachable, because the period keeps
    a single series and every emblem scores from that same series.

    Complete pair only: a Core or Support role scores the MEAN OF ITS TWO PLAYERS. A map on which
    only one of the current pair appears is not an observation of that pair -- averaging over
    whoever happened to be there silently substitutes a one-player score for a two-player one, which
    inflates nothing and deflates nothing predictably, it just measures a different quantity. Such
    maps are excluded and counted, not quietly averaged. Using history where the two never played
    together requires a synthetic-pair model, which is a separate estimator and is labelled as one.
    """
    stats = [s for s in STAT_COLUMNS if s not in UNAVAILABLE]
    need = len(accounts)
    # league -> series -> match -> account -> {stat: score}
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        acct = int(r["account_id"])
        if acct not in accounts:
            continue
        scored = {}
        for stat in stats:
            s = map_score(r, stat, rules, deaths_floor, tfp_curve)
            if s is not None:
                scored[stat] = s
        if scored:
            per[r["_league"]][r["_series"]][r["match_id"]][acct] = scored
    acct_sample = {"maps_seen": 0, "maps_complete_pair": 0, "maps_incomplete_pair": 0,
                   "series_seen": 0, "series_eligible": 0, "events_eligible": 0}
    out = defaultdict(dict)
    for league, ser in per.items():
        league_used = False
        for sid, by_match in ser.items():
            acct_sample["series_seen"] += 1
            complete = []
            for by_acct in by_match.values():
                acct_sample["maps_seen"] += 1
                if len(by_acct) == need:
                    acct_sample["maps_complete_pair"] += 1
                    complete.append(by_acct)
                else:
                    acct_sample["maps_incomplete_pair"] += 1
            if len(complete) < min_series_maps:
                continue
            row = {}
            for stat in stats:
                per_map = [sum(a[stat] for a in by_acct.values()) / need
                           for by_acct in complete if all(stat in a for a in by_acct.values())]
                if not per_map:
                    continue
                top = sorted(per_map, reverse=True)[:2]
                row[stat] = sum(top) if top_two == "sum" else sum(top) / len(top)
            if row:
                out[league][sid] = row
                acct_sample["series_eligible"] += 1
                league_used = True
        if league_used:
            acct_sample["events_eligible"] += 1
    return {k: dict(v) for k, v in out.items()}, acct_sample


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
    names = brp.player_names()
    res, excluded = [], []
    for org, assign in sorted(roles.items()):
        for role, accounts in sorted(assign.items()):
            colours = rules["layout"][role]
            acct = set(accounts)
            table, sample = series_table(rows, acct, rules, top_two, deaths_floor,
                                         min_series_maps, tfp_curve)
            entry = {"organization": org, "role": role, "players": sorted(acct),
                     "player_names": [names.get(a, str(a)) for a in sorted(acct)],
                     "sample": sample}
            best = best_banner(table, colours, rules["pools"])
            if not best:
                reason = ("the current pair never played a qualifying series together"
                          if sample["maps_complete_pair"] == 0 else
                          f"only {sample['series_eligible']} qualifying series")
                excluded.append({**entry, "exclusion_reason": reason})
                continue
            if sample["events_eligible"] < MIN_EVENTS:
                excluded.append({**entry, "exclusion_reason":
                                 f"{sample['events_eligible']} eligible event(s), "
                                 f"threshold is {MIN_EVENTS}"})
                continue
            mean, combo, by_league = best
            res.append({**entry, "stats": list(combo), "colours": list(colours),
                        "slots": [{"stat": s} for s in combo],
                        "leagues": len(by_league),
                        "by_league": {k: round(v, 1) for k, v in by_league.items()},
                        "series_scores": series_totals(table, combo),
                        "envelope_total": round(mean, 1)})
    return res, excluded


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


def coverage(stats_path=None, ledger=None):
    """How much of the target window the stat table actually holds, measured from the table itself.

    Deliberately not read from the fetcher's provenance file: that file is written when a run ends,
    so during a long or interrupted pull it describes an earlier run. Counting the match ids present
    cannot go stale.
    """
    from ti_predict.fantasy import fetch_player_stats as fp
    targets = {t[0] for t in fp.target_matches(fp.DEFAULT_LEAGUES)}
    have = fp.done_matches(stats_path, ledger)
    covered = len(targets & have)
    frac = covered / len(targets) if targets else 0.0
    return {"matches_covered": covered, "matches_targeted": len(targets),
            "coverage": round(frac, 4), "complete": frac >= fp.MIN_COVERAGE}


def build(top_two="sum", deaths_floor=False, min_series_maps=2, tfp_curve="linear"):
    rules = load_rules()
    rows, dropped, excluded_accounts = load_stats()
    roles = roles_from_roster()
    env, excluded = envelope(rows, roles, rules, top_two, deaths_floor, min_series_maps, tfp_curve)
    for e in env:
        e["uncertainty"] = uncertainty(e)
    for role in ("core", "mid", "support"):
        grp = [e for e in env if e["role"] == role]
        rp = rank_probabilities(grp)
        for e in grp:
            e["rank_probability"] = rp[e["organization"]]
    env.sort(key=lambda e: -e["envelope_total"])
    return {"hypothesis": {"top_two": top_two, "deaths_floor": deaths_floor,
                           "min_series_maps": min_series_maps, "tfp_curve": tfp_curve,
                           "role_source": "roster of record (positions 1-5)",
                           "pair_rule": "complete current pair only",
                           "min_events": MIN_EVENTS},
            "input_coverage": coverage(),
            "sample_coverage": roster_sample_coverage(rows, roles, env, excluded),
            "rows_used": len(rows), "rows_dropped": dropped,
            "inactive_accounts_excluded": sorted(excluded_accounts),
            "organizations": len(roles), "ranking": env, "excluded": excluded,
            "stat_availability": stat_availability(),
            "status": "PRELIMINARY",
            "why_preliminary": "The period-1 slot count is unknown, traits and coach titles are not "
                               "modelled, and the emblem stats are random draws rather than "
                               "choices. This ranks teams by an upper envelope over ideal rolls, "
                               "which is a comparison, not a pick."}


MIN_PLAYER_MAPS = 3


def roster_sample_coverage(rows=None, roles=None, env=None, excluded=None):
    """Five different questions that were previously answered with one number.

    "80 players, coverage 74" conflated: who is on the roster, who has any history at all, whose
    history is usable, whose sample is big enough, and which ROLE PAIRS have a joint sample. They
    are different quantities and they have different consequences -- a replacement signed last week
    is identity-covered and history-empty, which is not the same failure as a player whose matches
    exist but are unparsed.
    """
    if rows is None:
        rows, _dropped, _inactive = load_stats()
    roles = roles or roles_from_roster()
    active = {a for org in roles.values() for accts in org.values() for a in accts}
    inactive = brp.inactive_accounts()
    seen = defaultdict(int)
    for r in rows:
        seen[int(r["account_id"])] += 1
    threshold_ok = {a for a in active if seen[a] >= MIN_PLAYER_MAPS}
    if env is None or excluded is None:
        env, excluded = envelope(rows, roles, load_rules())
    pairs_total = sum(len(v) for v in roles.values())
    return {
        "roster_identity_coverage": {
            "active_slots": len(active), "expected": 80,
            "complete": len(active) == 80,
            "inactive_recorded": sorted(inactive),
            "meaning": "every position 1-5 on all sixteen teams resolves to a unique account id"},
        "players_with_any_historical_match": {
            "n": sum(1 for a in active if seen[a] > 0), "of": len(active),
            "without": sorted(a for a in active if seen[a] == 0),
            "meaning": "appears at least once in the five-event window, on the current roster"},
        "players_with_usable_parsed_map": {
            "n": sum(1 for a in active if seen[a] > 0), "of": len(active),
            "meaning": "every match in this window is parsed, so this equals the previous count; "
                       "they are kept apart because that is a property of the window, not a rule"},
        "players_passing_sample_threshold": {
            "n": len(threshold_ok), "of": len(active), "threshold_maps": MIN_PLAYER_MAPS,
            "below": sorted(a for a in active if 0 < seen[a] < MIN_PLAYER_MAPS),
            "meaning": "has at least the minimum number of parsed maps of his own"},
        "role_pairs_with_complete_sample": {
            "n": len(env), "of": pairs_total,
            "excluded": [{"organization": e["organization"], "role": e["role"],
                          "players": e["player_names"], "reason": e["exclusion_reason"],
                          "maps_complete_pair": e["sample"]["maps_complete_pair"],
                          "series_eligible": e["sample"]["series_eligible"],
                          "events_eligible": e["sample"]["events_eligible"]}
                         for e in excluded],
            "meaning": "the role's CURRENT players actually played qualifying series together; a "
                       "single-player observation is not an observation of a pair"},
    }


def stat_availability():
    """The four counts that 'stat coverage' has to be split into, so none of them can be misread."""
    defined = {s["stat_id"] for s in fq.load_rules()["stats"]["list"]}
    usable = set(STAT_COLUMNS) - set(UNAVAILABLE)
    return {"scoring_stats_defined_by_the_rules": len(defined),
            "fetched_columns_complete_for_supported_stats": True,
            "directly_usable_public_player_level": len(usable),
            "unavailable_or_unsupported": len(defined - usable),
            "unavailable_list": sorted(defined - usable),
            "note": "Column completeness on the stats this pipeline supports is not the same thing "
                    "as stat coverage. Three of the eighteen scoring stats have no usable public "
                    "player-level source at all, so they can never appear on a modelled banner and "
                    "the envelope is computed over the remaining fifteen."}


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
    cov = r["input_coverage"]
    print(f"PRELIMINARY envelope ({r['hypothesis']['role_source']}, "
          f"{r['hypothesis']['pair_rule']}): {r['rows_used']} parsed player-maps, "
          f"{len(r['ranking'])} ranked, {len(r['excluded'])} excluded, "
          f"match coverage {cov['coverage']:.1%}")
    for e in r["ranking"][:a.top]:
        u = e["uncertainty"]
        stats = " + ".join(e["stats"])
        print(f"  {e['envelope_total']:>9.1f}  se {str(u['se']):>7}  "
              f"{e['organization']:<18} {e['role']:<8} {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
