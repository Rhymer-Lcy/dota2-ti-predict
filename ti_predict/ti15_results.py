"""Completed TI15 results (39 Swiss + 5 Elimination Round series) as frozen observations.

This module is DATA plus reconciliation. It holds the series results exactly as reported, resolves
the client-facing TI names to the tracked canonical organizations, reconstructs the Swiss standings
from the series alone and asserts them against the published table, and expands each series into
map-level rows in the rating-universe schema so the frozen B-bt estimator can consume them with no
change to the estimator itself.

Three conventions are inherited from the frozen pipeline and must not drift:
  - observations are MAPS, not series (universe.py / backtest.py `load`);
  - every map of a series carries `w = 1/series_size`, so one Bo3 contributes total weight 1.0
    whether it ended 2-0 or 2-1. A series is therefore counted exactly once, never twice;
  - `start_time` drives the h90 decay, so every row needs a timestamp.

Timestamp provenance is deliberately split, because only part of it is Tier 1:
  - Round 1 uses the scheduled_time published in Valve's own league feed (league_id 19719), already
    downloaded to data/ti2026/raw/. Its eight pairings reconcile exactly with the round-1 results
    below, so the times belong to these series.
  - Rounds 2-5 and the Elimination Round have no local timestamp. They are placed on a two-rounds-
    per-day cadence across the event window. This is an ASSUMPTION, labelled as one. Its effect is
    bounded directly in the pipeline: collapsing every TI15 map onto a single instant moves the
    h90 weight of the block by under 3% and is reported as a sensitivity arm, not waved away.

No network access. Run `python -m ti_predict.ti15_results` for the reconciliation report.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED_JSON = os.path.join(REPO, "data", "ti2026", "raw", "league_19719_feed.json")

# TI client-facing name -> tracked canonical organization (teams.csv 'team'). Every TI15 identity
# resolves through this table; nothing is matched by name similarity.
ALIAS = {
    "TEAM VISION": "PARIVISION", "Team Vision": "PARIVISION", "PARIVISION": "PARIVISION",
    "BoomBoys": "BetBoom Team", "BetBoom Team": "BetBoom Team",
    "Iron Wing": "Tundra Esports", "1w Team": "Tundra Esports", "1WIN Team": "Tundra Esports",
    "Tundra Esports": "Tundra Esports",
    "Team Liquid": "Team Liquid", "Nigma Galaxy": "Nigma Galaxy", "Team Spirit": "Team Spirit",
    "Team Falcons": "Team Falcons", "Team Yandex": "Team Yandex", "Aurora Gaming": "Aurora Gaming",
    "LGD Gaming": "LGD Gaming", "Vici Gaming": "Vici Gaming", "Team Resilience": "Team Resilience",
    "GamerLegion": "GamerLegion", "Xtreme Gaming": "Xtreme Gaming", "OG": "OG",
    "HULIGANI": "HULIGANI",
}

# (round, winner, loser, winner_maps, loser_maps) -- client-facing names, exactly as reported.
SWISS = [
    (1, "Team Falcons", "LGD Gaming", 2, 1),
    (1, "Iron Wing", "Nigma Galaxy", 2, 0),
    (1, "BoomBoys", "OG", 2, 0),
    (1, "TEAM VISION", "Team Resilience", 2, 1),
    (1, "Team Spirit", "Xtreme Gaming", 2, 0),
    (1, "Team Liquid", "Vici Gaming", 2, 0),
    (1, "Aurora Gaming", "GamerLegion", 2, 0),
    (1, "Team Yandex", "HULIGANI", 2, 0),
    (2, "TEAM VISION", "Team Falcons", 2, 1),
    (2, "BoomBoys", "Iron Wing", 2, 1),
    (2, "LGD Gaming", "Team Resilience", 2, 1),
    (2, "Nigma Galaxy", "OG", 2, 0),
    (2, "Team Spirit", "Aurora Gaming", 2, 0),
    (2, "Team Liquid", "Team Yandex", 2, 1),
    (2, "GamerLegion", "Xtreme Gaming", 2, 0),
    (2, "Vici Gaming", "HULIGANI", 2, 1),
    (3, "TEAM VISION", "BoomBoys", 2, 0),
    (3, "Team Spirit", "Team Liquid", 2, 1),
    (3, "Iron Wing", "Team Falcons", 2, 1),
    (3, "Nigma Galaxy", "LGD Gaming", 2, 0),
    (3, "Vici Gaming", "GamerLegion", 2, 1),
    (3, "Aurora Gaming", "Team Yandex", 2, 1),
    (3, "Team Resilience", "OG", 2, 0),
    (3, "Xtreme Gaming", "HULIGANI", 2, 0),
    (4, "TEAM VISION", "Team Spirit", 2, 0),
    (4, "Team Liquid", "Iron Wing", 2, 1),
    (4, "Aurora Gaming", "BoomBoys", 2, 0),
    (4, "Nigma Galaxy", "Vici Gaming", 2, 0),
    (4, "LGD Gaming", "Xtreme Gaming", 2, 1),
    (4, "Team Falcons", "GamerLegion", 2, 1),
    (4, "Team Yandex", "Team Resilience", 2, 1),
    (4, "OG", "HULIGANI", 2, 1),
    (5, "Team Liquid", "Aurora Gaming", 2, 1),
    (5, "Nigma Galaxy", "Team Spirit", 2, 0),
    (5, "Team Falcons", "BoomBoys", 2, 1),
    (5, "LGD Gaming", "Vici Gaming", 2, 0),
    (5, "Iron Wing", "Team Yandex", 2, 1),
    (5, "Team Resilience", "Xtreme Gaming", 2, 0),
    (5, "GamerLegion", "OG", 2, 0),
]

ELIMINATION = [
    (6, "Team Falcons", "Vici Gaming", 2, 0),
    (6, "BoomBoys", "Aurora Gaming", 2, 0),
    (6, "Team Spirit", "Team Resilience", 2, 1),
    (6, "Iron Wing", "GamerLegion", 2, 0),
    (6, "Team Yandex", "LGD Gaming", 2, 1),
]

# Published final Swiss standings: rank -> (team, series_w, series_l, map_w, map_l). The
# reconstruction below must reproduce every series and map cell exactly.
PUBLISHED_STANDINGS = [
    (1, "TEAM VISION", 4, 0, 8, 2), (2, "Team Liquid", 4, 1, 9, 5),
    (3, "Nigma Galaxy", 4, 1, 8, 2), (4, "Team Spirit", 3, 2, 6, 5),
    (5, "Iron Wing", 3, 2, 8, 6), (6, "Team Falcons", 3, 2, 8, 7),
    (7, "Aurora Gaming", 3, 2, 7, 5), (8, "LGD Gaming", 3, 2, 7, 6),
    (9, "BoomBoys", 2, 3, 5, 7), (10, "Vici Gaming", 2, 3, 4, 8),
    (11, "Team Yandex", 2, 3, 7, 7), (12, "Team Resilience", 2, 3, 7, 6),
    (13, "GamerLegion", 2, 3, 6, 6), (14, "Xtreme Gaming", 1, 4, 3, 8),
    (15, "OG", 1, 4, 2, 9), (16, "HULIGANI", 0, 4, 2, 8),
]

# The eight Main Event teams, in the order the fixed opening bracket seats them.
FINAL_EIGHT = ["Iron Wing", "Team Spirit", "TEAM VISION", "BoomBoys",
               "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"]

# Fixed opening bracket (do not reseed): league-feed node id -> (client name, client name).
UBQF = {14: ("Iron Wing", "Team Spirit"), 15: ("TEAM VISION", "BoomBoys"),
        16: ("Team Liquid", "Team Yandex"), 17: ("Nigma Galaxy", "Team Falcons")}

# Round -> UTC day. Round 1 is overridden per series by the league feed's own scheduled_time; the
# rest is the labelled cadence assumption described in the module docstring.
ROUND_DAY = {1: "2026-08-13", 2: "2026-08-14", 3: "2026-08-14",
             4: "2026-08-15", 5: "2026-08-15", 6: "2026-08-16"}
ROUND_BLOCK_HOURS = (2, 8)      # two broadcast blocks per day, four series each
# Knowledge cutoff for the serve state. This is NOT a label: it is the reference point of the h90
# decay AND the upper bound of the training filter (start_time < cutoff), so it has to be a time we
# had actually reached. It sits strictly after the final Elimination Round map (2026-08-16T08:00Z,
# the Team Yandex 2-1 LGD series) and strictly before the production run, so nothing in the fit is
# dated in the future. An earlier value of 18:00Z was wrong on the second count -- it post-dated the
# run that consumed it by about 75 minutes. Both bounds are now asserted rather than trusted:
# verify_standings checks the lower one, and the production run refuses to start if any state cutoff
# is later than its own start time. A fixed constant is used rather than "now" so the artifact stays
# byte-reproducible.
SERVE_CUTOFF = "2026-08-16T12:00:00Z"
SWISS_LOCK = "2026-08-13T02:00:00Z"       # pre-TI production cutoff (first Swiss map)

# Synthetic series ids for the 44 TI15 series. Offset far above every id in the scanned universe so
# a collision cannot silently merge a TI15 series into a historical one; asserted in build_rows.
SERIES_ID_BASE = 900_000_000
MATCH_ID_BASE = 9_900_000_000
TI15_LEAGUE_ID = "19719"


def canon(name):
    """Client-facing TI name -> tracked canonical organization. Raises on an unknown identity."""
    if name not in ALIAS:
        raise KeyError(f"unknown TI15 identity {name!r}; add it to ti15_results.ALIAS "
                       "(never resolve a team by name similarity)")
    return ALIAS[name]


def _ts(day, hour):
    return int(datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00").timestamp())


def feed_round1_times(path=None):
    """Round-1 scheduled_time per pairing from the saved official league feed.

    Returns {frozenset({orgA, orgB}): unix_ts}. The feed is the machine-readable source behind the
    game client and is already on disk; nothing is fetched. Team ids resolve through
    canonical_identity.csv, never by name.
    """
    path = path or FEED_JSON
    if not os.path.exists(path):
        return {}
    from ti_predict.league_feed import id_to_org
    with open(path, encoding="utf-8") as fh:
        feed = json.load(fh)
    id2org = id_to_org()

    def walk(gs):
        for g in gs or []:
            yield g
            yield from walk(g.get("node_groups"))
    out = {}
    for g in walk(feed.get("node_groups")):
        if g.get("name") != "Swiss":
            continue
        for n in g.get("nodes") or []:
            a, b, t = n.get("team_id_1"), n.get("team_id_2"), n.get("scheduled_time")
            if a and b and t:
                out[frozenset((id2org[a], id2org[b]))] = int(t)
    return out


def standings(series=None):
    """Reconstruct {team: dict} from the series results alone (no standings table consulted)."""
    series = SWISS if series is None else series
    rec = defaultdict(lambda: {"sw": 0, "sl": 0, "mw": 0, "ml": 0})
    for _, w, l, wm, lm in series:
        rec[w]["sw"] += 1; rec[w]["mw"] += wm; rec[w]["ml"] += lm
        rec[l]["sl"] += 1; rec[l]["mw"] += lm; rec[l]["ml"] += wm
    return dict(rec)


def verify_standings():
    """Assert the reconstruction equals the published table cell by cell. Returns the check report."""
    got = standings()
    problems = []
    if len(SWISS) != 39:
        problems.append(f"expected 39 Swiss series, found {len(SWISS)}")
    if len(ELIMINATION) != 5:
        problems.append(f"expected 5 Elimination series, found {len(ELIMINATION)}")
    for rank, team, sw, sl, mw, ml in PUBLISHED_STANDINGS:
        g = got.get(team)
        if g is None:
            problems.append(f"rank {rank} {team}: absent from the reconstructed series")
            continue
        if (g["sw"], g["sl"], g["mw"], g["ml"]) != (sw, sl, mw, ml):
            problems.append(f"rank {rank} {team}: reconstructed {g['sw']}-{g['sl']} "
                            f"{g['mw']}-{g['ml']}, published {sw}-{sl} {mw}-{ml}")
    extra = set(got) - {t for _, t, *_ in PUBLISHED_STANDINGS}
    if extra:
        problems.append("teams in the series but not the standings table: " + ", ".join(sorted(extra)))
    # every Swiss series is a Bo3 that ended 2-0 or 2-1, and the 5 stop-at-4 structure holds
    for r, w, l, wm, lm in SWISS + ELIMINATION:
        if wm != 2 or lm not in (0, 1):
            problems.append(f"round {r} {w} vs {l}: {wm}-{lm} is not a Bo3 result")
    per_round = defaultdict(int)
    for r, *_ in SWISS:
        per_round[r] += 1
    if dict(per_round) != {1: 8, 2: 8, 3: 8, 4: 8, 5: 7}:
        problems.append(f"Swiss round sizes {dict(per_round)} != 8/8/8/8/7 (the 4-0 and 0-4 teams "
                        "stop after round 4, so round 5 has 7 series)")
    # the surviving eight are exactly the top three plus the five Elimination winners
    top3 = [t for _, t, *_ in PUBLISHED_STANDINGS[:3]]
    elim_w = [w for _, w, _, _, _ in ELIMINATION]
    if sorted(canon(t) for t in top3 + elim_w) != sorted(canon(t) for t in FINAL_EIGHT):
        problems.append("FINAL_EIGHT is not top-3 plus the five Elimination winners")
    orgs = {canon(t) for t in FINAL_EIGHT}
    if len(orgs) != 8:
        problems.append(f"alias mapping collapses the final eight to {len(orgs)} organizations")
    seated = [t for pair in UBQF.values() for t in pair]
    if sorted(seated) != sorted(FINAL_EIGHT):
        problems.append("the fixed opening bracket does not seat exactly the final eight")
    # The serve cutoff drives the h90 decay and the training filter, so a value that predates the
    # last result would silently drop it from the fit. Checked here; the upper bound (the cutoff must
    # not post-date the run consuming it) is checked by the production run, which alone knows when
    # it started.
    rows, _ = build_rows()
    last_map = max(r["start_time"] for r in rows)
    serve_ts = int(datetime.fromisoformat(SERVE_CUTOFF.replace("Z", "+00:00")).timestamp())
    if serve_ts <= last_map:
        problems.append(f"SERVE_CUTOFF {SERVE_CUTOFF} is not after the final TI15 map "
                        f"({datetime.fromtimestamp(last_map, timezone.utc).isoformat()}); the "
                        "last results would be excluded from their own serve state")
    swiss_ts = int(datetime.fromisoformat(SWISS_LOCK.replace("Z", "+00:00")).timestamp())
    if swiss_ts > min(r["start_time"] for r in rows):
        problems.append("SWISS_LOCK must not post-date the first TI15 map")
    if problems:
        raise SystemExit("TI15 RESULT RECONCILIATION FAILED:\n  - " + "\n  - ".join(problems))
    return {"swiss_series": len(SWISS), "elimination_series": len(ELIMINATION),
            "total_series": len(SWISS) + len(ELIMINATION),
            "standings_reproduced": True, "unique_surviving_orgs": len(orgs),
            "swiss_round_sizes": dict(per_round),
            "serve_cutoff": SERVE_CUTOFF,
            "last_ti15_map_utc": datetime.fromtimestamp(last_map, timezone.utc).isoformat(),
            "cutoff_is_after_last_result": True}


def build_rows(collapse_to=None, use_feed_times=True):
    """Expand the 44 series into map-level rows in the rating-universe schema.

    A 2-0 becomes two rows (a_won=1) and a 2-1 becomes three rows (two a_won=1, one a_won=0), all
    sharing one series_id so `load`'s 1/series_size weighting gives the series total weight 1.0.
    Map ORDER inside a series is not modelled and does not matter: the frozen estimator treats a
    series' maps as exchangeable observations differing only in the h90 decay weight, and the
    within-series spread is under a tenth of a day.

    `collapse_to` (ISO string) forces every TI15 row onto one instant -- the timestamp sensitivity
    arm. Returns (rows, provenance).
    """
    feed_times = feed_round1_times() if use_feed_times else {}
    rows, used_feed, assumed = [], 0, 0
    collapse_ts = int(datetime.fromisoformat(collapse_to.replace("Z", "+00:00")).timestamp()) \
        if collapse_to else None
    per_round_seq = defaultdict(int)
    for i, (rnd, w, l, wm, lm) in enumerate(SWISS + ELIMINATION):
        a, b = canon(w), canon(l)
        key = frozenset((a, b))
        seq = per_round_seq[rnd]; per_round_seq[rnd] += 1
        if collapse_ts is not None:
            ts = collapse_ts
        elif rnd == 1 and key in feed_times:
            ts = feed_times[key]; used_feed += 1
        else:
            hour = ROUND_BLOCK_HOURS[0 if seq < 4 else 1]
            ts = _ts(ROUND_DAY[rnd], hour); assumed += 1
        sid = SERIES_ID_BASE + i
        for j in range(wm + lm):
            rows.append({"match_id": str(MATCH_ID_BASE + 10 * i + j), "start_time": ts + j,
                         "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                         "leagueid": TI15_LEAGUE_ID, "league_name": "The International 2026",
                         "series_id": sid, "team_a": a, "team_b": b,
                         "a_won": 1 if j < wm else 0, "is_target": 0,
                         "ti15_round": rnd, "ti15_stage": "swiss" if rnd <= 5 else "elimination"})
    prov = {"series_expanded": len(SWISS) + len(ELIMINATION), "map_rows": len(rows),
            "round1_timestamps_from_league_feed": used_feed,
            "timestamps_assumed_from_cadence": assumed,
            "collapsed_to": collapse_to,
            "weighting": "1/series_size per map, so each Bo3 contributes total weight 1.0",
            "series_id_range": [SERIES_ID_BASE, SERIES_ID_BASE + len(SWISS) + len(ELIMINATION) - 1]}
    return rows, prov


def augmented_universe(collapse_to=None, use_stages=("swiss", "elimination")):
    """The frozen rating universe plus the requested TI15 stages, as `backtest.load` returns it.

    Returns (rows, provenance). Series weights are recomputed over the combined set exactly the way
    `load` does, so nothing about the frozen weighting convention is special-cased for TI15.
    """
    from collections import Counter
    from ti_predict.backtest import load
    uni, _, _ = load()
    base_ids = {r["series_id"] for r in uni}
    ti, prov = build_rows(collapse_to=collapse_to)
    ti = [r for r in ti if r["ti15_stage"] in use_stages]
    clash = base_ids & {r["series_id"] for r in ti}
    if clash:
        raise SystemExit(f"TI15 series ids collide with the universe: {sorted(clash)[:5]}")
    rows = list(uni) + ti
    rows.sort(key=lambda r: (r["start_time"], r["match_id"]))
    ssize = Counter(r["series_id"] for r in rows if r["series_id"])
    for r in rows:
        r["w"] = 1.0 / ssize[r["series_id"]] if r["series_id"] else 1.0
    prov.update(universe_rows=len(uni), stages_included=list(use_stages),
                combined_rows=len(rows), ti15_rows_added=len(ti))
    return rows, prov


def main():
    rep = verify_standings()
    print("TI15 result reconciliation")
    print(f"  Swiss series      : {rep['swiss_series']} (rounds {rep['swiss_round_sizes']})")
    print(f"  Elimination series: {rep['elimination_series']}")
    print(f"  total inserted    : {rep['total_series']}")
    print(f"  standings reproduced exactly from the series: {rep['standings_reproduced']}")
    print(f"  surviving organizations after alias mapping : {rep['unique_surviving_orgs']}")
    rows, prov = build_rows()
    print(f"  map rows          : {prov['map_rows']} "
          f"(r1 feed timestamps {prov['round1_timestamps_from_league_feed']}, "
          f"cadence-assumed {prov['timestamps_assumed_from_cadence']})")
    got = standings()
    print("\n  rank team              series  maps   (reconstructed)")
    for rank, team, *_ in PUBLISHED_STANDINGS:
        g = got[team]
        print(f"  {rank:>4} {team:<17} {g['sw']}-{g['sl']}    {g['mw']}-{g['ml']}"
              f"   -> {canon(team)}")


if __name__ == "__main__":
    main()
