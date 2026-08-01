"""Training-set assembly (modeling track, per backtest-protocol.md).

Turns the roster-centric maps into a clean chronological dataset for the rating baselines:
one row per official map with both teams' canonical identities, the winner, the series it belongs
to, a series-cap weight, and Bo2/missing-series flags. No model is fit here; this is just the data
interface the baselines + rolling backtest consume.

Identity: our 16 rosters -> organization name (collapsing their multiple source_team_ids);
opponents -> their OpenDota team_id (or org if they are also a TI team). TI-vs-TI maps are recorded
once (deduped by match_id).

Series cap: weight = 1 / (maps sharing that series_id in this dataset); a map with no series_id is
its own singleton (weight 1). Bo2 = a 2-map series split 1-1 -> flagged (kept for map-eval, excluded
from binary series-win eval per protocol sec 4).

Writes processed/dataset_maps.csv + processed/dataset_series.csv (gitignored). Prints stats.
Run: python -m ti_predict.build_dataset
"""
import csv
import json
import os
from collections import defaultdict, Counter
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
PROC = os.path.join(TI, "processed")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    scan = {m["match_id"]: m for m in json.load(open(os.path.join(TI, "raw", "promatches_scan.json"), encoding="utf-8"))}
    matches = _read(os.path.join(PROC, "roster_matches.csv"))
    canon = _read(os.path.join(TI, "inputs", "canonical_identity.csv"))
    id2org = {}
    for r in canon:
        for sid in (r["source_team_ids"] or "").split("|"):
            if sid:
                id2org[int(sid)] = r["organization"]

    def ident(team_id):
        return id2org.get(int(team_id), f"ext:{team_id}") if team_id else None

    # one record per match_id (dedupe TI-vs-TI)
    seen = {}
    for m in matches:
        mid = int(m["match_id"])
        if mid in seen:
            continue
        sc = scan.get(mid)
        if not sc or not sc.get("radiant_team_id") or not sc.get("dire_team_id"):
            continue
        our_side = m["side"]                       # 'rad' | 'dire'
        our_id = int(m["source_team_id"])
        opp_id = sc["dire_team_id"] if our_side == "rad" else sc["radiant_team_id"]
        a_won = (sc["radiant_win"] is True) == (our_side == "rad")
        sid = sc.get("series_id") or 0
        seen[mid] = {"match_id": mid, "start_time": sc.get("start_time"),
                     "date": datetime.fromtimestamp(sc["start_time"], timezone.utc).date().isoformat() if sc.get("start_time") else "",
                     "team_a": ident(our_id), "team_b": ident(opp_id),
                     "a_won": int(bool(a_won)), "series_id": sid, "overlap_a": int(m["overlap"])}

    rows = sorted(seen.values(), key=lambda r: (r["start_time"] or 0, r["match_id"]))

    # series-level: size, cap weight, Bo2-draw detection (series_id 0 => singletons)
    by_series = defaultdict(list)
    for r in rows:
        key = f"s{r['series_id']}" if r["series_id"] else f"m{r['match_id']}"   # missing -> singleton
        r["series_key"] = key
        by_series[key].append(r)
    series_rows, bo2_draw_keys = [], set()
    for key, ms in by_series.items():
        size = len(ms)
        a_wins = sum(m["a_won"] for m in ms)      # from team_a-of-first-map perspective is not stable; count per map
        # Bo2 draw = exactly 2 maps and the two maps had opposite winners *relative to a fixed team*.
        is_bo2_draw = False
        if size == 2:
            t = ms[0]["team_a"]
            wins_t = sum((m["a_won"] if m["team_a"] == t else (1 - m["a_won"])) for m in ms)
            is_bo2_draw = (wins_t == 1)
        if is_bo2_draw:
            bo2_draw_keys.add(key)
        series_rows.append({"series_key": key, "size": size, "is_singleton": int(str(key).startswith("m")),
                            "is_bo2_draw": int(is_bo2_draw),
                            "teams": "|".join(sorted({m["team_a"] for m in ms} | {m["team_b"] for m in ms}))})
    for r in rows:
        r["series_size"] = len(by_series[r["series_key"]])
        r["weight"] = round(1.0 / r["series_size"], 4)
        r["bo2_draw"] = int(r["series_key"] in bo2_draw_keys)

    os.makedirs(PROC, exist_ok=True)
    cols = ["match_id", "start_time", "date", "team_a", "team_b", "a_won", "series_key",
            "series_size", "weight", "bo2_draw", "overlap_a"]
    with open(os.path.join(PROC, "dataset_maps.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with open(os.path.join(PROC, "dataset_series.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["series_key", "size", "is_singleton", "is_bo2_draw", "teams"])
        w.writeheader(); w.writerows(series_rows)

    n_ti_vs_ti = sum(1 for r in rows if not r["team_a"].startswith("ext:") and not r["team_b"].startswith("ext:"))
    missing = sum(1 for r in rows if r["series_key"].startswith("m"))
    sizes = Counter(s["size"] for s in series_rows if not s["is_singleton"])
    print(f"dataset_maps: {len(rows)} maps, {rows[0]['date']}..{rows[-1]['date']}")
    print(f"  TI-vs-TI maps: {n_ti_vs_ti} | maps w/o real series_id (singletons): {missing}")
    print(f"  series: {len(series_rows)} ({sum(s['is_singleton'] for s in series_rows)} singletons); "
          f"Bo2-draw series: {len(bo2_draw_keys)}")
    print(f"  real-series size histogram: {dict(sorted(sizes.items()))}")
    print(f"  wrote dataset_maps.csv + dataset_series.csv")


if __name__ == "__main__":
    main()
