"""B0 step 3 (corrected): roster-centric coverage — the current five, SAME SIDE, layered.

A match counts for a roster only when the players are on the SAME team that game; coverage is layered
by how many of the five were on that side; maps are de-duped by map_id (= OpenDota match_id);
series_id is kept for series-weight capping.

"Official match" test: `/players/{id}/matches` carries NO leagueid, so we intersect each player's
match list with the **pro-match universe** from the proMatches snapshot (raw/promatches_scan.json),
which is by construction professional matches and also supplies each map's team_ids + series_id.
Coverage therefore spans the snapshot window (currently ~2026-05-15 .. 08-01, i.e. recent form);
extend by scanning more proMatches pages if deeper history is needed.

Layers (usage contract from review): 5/5 direct history; 4/5 stand-in (discount); 3/5 player-prior
only; <3 ignored for the roster. Tracking the five players stitches games across ALL team_ids, so a
split/renamed org (Xtreme 8261500/10208071; Tundra->1w 8291895/10182357; Resilience
5017210/10207984) is reunited by roster, while LGD's three rosters stay separate (different players).

Writes processed/roster_coverage.csv + processed/roster_matches.csv (gitignored). Manifest appended.
Run:  python -m ti_predict.roster_coverage
"""
import csv
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
RAW, INPUTS, PROC = (os.path.join(TI, d) for d in ("raw", "inputs", "processed"))
BASE = "https://api.opendota.com/api"
UA = {"User-Agent": "dota2-ti-predict/0.1 (coverage)"}
NOW = datetime.now(timezone.utc)
LOOKBACK_DAYS = 400


def _get(path, tries=4):
    """GET with retries. OpenDota fronts a CDN that returns 5xx in bursts (521/522 observed
    2026-08-10); without retries a transient outage silently costs a whole team its coverage."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(BASE + path, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
            return raw, json.loads(raw)
        except Exception as ex:                       # transient HTTP/network/JSON failure
            last = ex
            if i < tries - 1:
                time.sleep(2.0 * (i + 1))
    raise last


def _manifest(endpoint, key, raw, n):
    with open(os.path.join(INPUTS, "fetch-manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"endpoint": endpoint, "key": key, "fetched_at": NOW.isoformat(),
                             "data_cutoff": NOW.isoformat(), "n_records": n,
                             "sha256": hashlib.sha256(raw).hexdigest()}, ensure_ascii=False) + "\n")


def pro_universe():
    """match_id -> {radiant, dire, series_id, series_type, start} from the proMatches snapshot."""
    p = os.path.join(RAW, "promatches_scan.json")
    out = {}
    for m in json.load(open(p, encoding="utf-8")):
        out[m["match_id"]] = {"radiant": m.get("radiant_team_id"), "dire": m.get("dire_team_id"),
                              "series_id": m.get("series_id"), "series_type": m.get("series_type"),
                              "start": m.get("start_time")}
    return out


def collect_agg(pids, pro):
    """match_id -> {'rad':set,'dire':set,'start':ts} over the five's PRO matches (intersect pro)."""
    agg = {}
    for aid in pids:
        raw, ms = _get(f"/players/{aid}/matches?date={LOOKBACK_DAYS}")
        time.sleep(1.1)
        for m in ms:
            mid = m.get("match_id")
            if mid is None or mid not in pro:          # keep only official pro matches
                continue
            e = agg.setdefault(mid, {"rad": set(), "dire": set(), "start": pro[mid]["start"]})
            (e["rad"] if (m.get("player_slot", 0) < 128) else e["dire"]).add(aid)
    return agg


def main():
    pro = pro_universe()
    ident = os.path.join(PROC, "identity_resolved.csv")
    if not os.path.exists(ident):
        raise SystemExit(f"{ident} not found; run python -m ti_predict.resolve_identity first")
    teams = list(csv.DictReader(open(ident, encoding="utf-8")))
    summary, match_rows, failed = [], [], []
    for t in teams:
        org = t["organization"]
        pids = [int(x) for x in (t.get("player_ids") or "").split("|") if x.strip().lstrip("-").isdigit()]
        if len(pids) < 4:
            failed.append(f"{org}: only {len(pids)} account_ids in identity_resolved.csv")
            continue
        try:
            agg = collect_agg(pids, pro)
        except Exception as e:
            # Never drop a team quietly. build_canonical writes the TRACKED identity table from
            # this output, so a skipped org disappears from it together with its source_team_ids --
            # and the rating universe resolves organizations through exactly that column. On
            # 2026-08-10 an API error burst dropped Aurora Gaming and BetBoom Team this way, taking
            # 79 target maps with them.
            failed.append(f"{org}: {e!r}")
            continue

        rows, src_ids, series = [], set(), {5: set(), 4: set()}
        for mid, e in agg.items():
            side = "rad" if len(e["rad"]) >= len(e["dire"]) else "dire"
            k = len(e[side])
            if k < 3:
                continue
            sc = pro[mid]
            src = sc["radiant"] if side == "rad" else sc["dire"]
            if src:
                src_ids.add(src)
            if k in (5, 4) and sc.get("series_id"):
                series[k].add(sc["series_id"])
            rows.append({"organization": org, "match_id": mid,
                         "date": datetime.fromtimestamp(e["start"], timezone.utc).date().isoformat() if e["start"] else "",
                         "start": e["start"], "overlap": k, "side": side,
                         "roster_key": "-".join(sorted(str(a) for a in e[side])),
                         "series_id": sc.get("series_id"), "source_team_id": src})

        n = {j: sum(r["overlap"] == j for r in rows) for j in (5, 4, 3)}
        st = [r["start"] for r in rows if r["overlap"] >= 4 and r["start"]]
        d90 = sum(1 for s in st if NOW.timestamp() - s <= 90 * 86400)
        d365 = sum(1 for s in st if NOW.timestamp() - s <= 365 * 86400)
        summary.append({"organization": org, "maps_5of5": n[5], "maps_4of5": n[4], "maps_3of5": n[3],
                        "series_5of5": len(series[5]), "series_4of5": len(series[4]),
                        "earliest_ge4": datetime.fromtimestamp(min(st), timezone.utc).date().isoformat() if st else "-",
                        "latest_ge4": datetime.fromtimestamp(max(st), timezone.utc).date().isoformat() if st else "-",
                        "maps_90d_ge4": d90, "maps_365d_ge4": d365,
                        "source_team_ids": "|".join(str(i) for i in sorted(src_ids))})
        match_rows.extend({k: v for k, v in r.items() if k != "start"} for r in rows)
        s = summary[-1]
        print(f"{org:<17} 5/5 {n[5]:>3}  4/5 {n[4]:>3}  3/5 {n[3]:>3} | series5 {len(series[5]):>3} "
              f"| {s['earliest_ge4']}..{s['latest_ge4']} | 90d {d90:>3} 365d {d365:>4} "
              f"| ids {s['source_team_ids'] or '-'}")

    if failed or len(summary) != len(teams):
        missing = [t["organization"] for t in teams
                   if t["organization"] not in {r["organization"] for r in summary}]
        raise SystemExit(
            "roster coverage INCOMPLETE - refusing to hand a partial table to build_canonical.\n"
            + "\n".join("  " + f for f in failed)
            + (f"\n  missing from the output: {', '.join(missing)}" if missing else "")
            + f"\n({len(summary)}/{len(teams)} organizations collected; processed/*.csv left "
              "unchanged). Re-run when the match API is healthy.")

    _manifest("players/matches", f"{len(teams)}x5 vs pro-universe", json.dumps(summary).encode(), len(summary))
    with open(os.path.join(PROC, "roster_coverage.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    with open(os.path.join(PROC, "roster_matches.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(match_rows[0])); w.writeheader(); w.writerows(match_rows)
    print(f"\nwrote roster_coverage.csv ({len(summary)}) + roster_matches.csv ({len(match_rows)})")


if __name__ == "__main__":
    main()
