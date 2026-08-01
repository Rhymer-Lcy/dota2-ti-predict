"""B0 step 2: resolve current team identity + roster (fixes stale/wrong team_ids).

Strategy (all from the free OpenDota API, no key):
  1. scan recent /proMatches (paginated) -> for each org name/alias, the team_id actually used
     in the most recent pro matches (this re-resolves stale ids like BetBoom / LGD);
  2. for each resolved active id, fetch its 2 most recent match details -> extract the five
     account_ids on that team's side = roster_key, and check roster stability across the two;
  3. capture series_id / series_type from proMatches (map<->series linkage for gate 3).

As-of note: this reads matches up to *now*, i.e. the roster "as of today" for the live TI pick.
For the rolling backtest, rosters must be re-frozen at each event's cutoff (no post-cutoff match may
confirm an earlier roster). Writes canonical_identity.csv + recent_matches.csv + manifest.

Run:  python -m ti_predict.resolve_identity
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
UA = {"User-Agent": "dota2-ti-predict/0.1 (identity)"}
NOW = datetime.now(timezone.utc)
PAGES = 30            # ~3000 recent pro matches

# org -> accepted name aliases (lowercased) seen on OpenDota / at TI
ALIASES = {
    "Aurora Gaming": {"aurora gaming", "aurora"},
    "BetBoom Team": {"betboom team", "bb team", "betboom", "boomboys"},
    "Team Falcons": {"team falcons", "falcons"},
    "Team Liquid": {"team liquid", "liquid"},
    "Tundra Esports": {"tundra esports", "tundra"},
    "Xtreme Gaming": {"xtreme gaming", "xtreme"},
    "Team Yandex": {"team yandex", "yandex"},
    "Team Resilience": {"team resilience", "resilience"},
    "Vici Gaming": {"vici gaming", "vici"},
    "LGD Gaming": {"lgd gaming", "psg.lgd", "psg lgd", "lgd"},
    "OG": {"og"},
    "GamerLegion": {"gamerlegion", "gamer legion"},
    "Team Spirit": {"team spirit", "spirit"},
    "PARIVISION": {"parivision", "pvision", "team vision"},
    "HULIGANI": {"huligani"},
    "Nigma Galaxy": {"nigma galaxy", "nigma"},
}


def _get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    return raw, json.loads(raw)


def _manifest(endpoint, key, raw, n):
    with open(os.path.join(INPUTS, "fetch-manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"endpoint": endpoint, "key": key, "fetched_at": NOW.isoformat(),
                             "data_cutoff": NOW.isoformat(), "n_records": n,
                             "sha256": hashlib.sha256(raw).hexdigest()}, ensure_ascii=False) + "\n")


def scan_promatches():
    """Paginate /proMatches; return list of match dicts (recent-first)."""
    out, less_than = [], None
    for _ in range(PAGES):
        path = "/proMatches" + (f"?less_than_match_id={less_than}" if less_than else "")
        raw, page = _get(path)
        if not page:
            break
        out.extend(page)
        less_than = min(m["match_id"] for m in page)
        time.sleep(1.1)
    return out


def roster_from_match(mid, team_id):
    """Return (player_ids, player_names) for team_id's side of match mid, or ([],[])."""
    raw, m = _get(f"/matches/{mid}")
    time.sleep(1.1)
    with open(os.path.join(RAW, f"match_{mid}.json"), "wb") as fh:
        fh.write(raw)
    _manifest("matches", str(mid), raw, 1)
    radiant = m.get("radiant_team_id") == team_id
    ids, names = [], []
    for p in m.get("players", []):
        is_rad = p.get("player_slot", 0) < 128
        if is_rad == radiant:
            ids.append(p.get("account_id"))
            names.append(p.get("name") or p.get("personaname") or str(p.get("account_id")))
    return ids, names


def main():
    os.makedirs(RAW, exist_ok=True); os.makedirs(INPUTS, exist_ok=True); os.makedirs(PROC, exist_ok=True)
    teams = list(csv.DictReader(open(os.path.join(INPUTS, "teams.csv"), encoding="utf-8")))
    pm = scan_promatches()
    with open(os.path.join(RAW, "promatches_scan.json"), "w", encoding="utf-8") as fh:
        json.dump(pm, fh)
    _manifest("proMatches", f"{PAGES}pages", json.dumps(pm).encode(), len(pm))
    print(f"proMatches scanned: {len(pm)} matches, "
          f"{datetime.fromtimestamp(min(m['start_time'] for m in pm), timezone.utc).date()} .. "
          f"{datetime.fromtimestamp(max(m['start_time'] for m in pm), timezone.utc).date()}")

    # index recent matches by team_id (name + latest)
    seen = {}  # team_id -> {"name","latest","matches":[(start,mid,opp_id,opp_name,win,series_id,series_type,leagueid)]}
    for m in pm:
        for side in ("radiant", "dire"):
            tid = m.get(f"{side}_team_id")
            if not tid:
                continue
            opp = "dire" if side == "radiant" else "radiant"
            win = m.get("radiant_win") == (side == "radiant")
            e = seen.setdefault(tid, {"name": m.get(f"{side}_name") or "", "latest": 0, "matches": []})
            e["name"] = e["name"] or (m.get(f"{side}_name") or "")
            e["latest"] = max(e["latest"], m["start_time"])
            e["matches"].append((m["start_time"], m["match_id"], m.get(f"{opp}_team_id"),
                                 m.get(f"{opp}_name"), win, m.get("series_id"),
                                 m.get("series_type"), m.get("leagueid")))

    rec_rows, id_rows = [], []
    for t in teams:
        org = t["team"]; alias = ALIASES[org]
        # candidate ids whose recent name matches an alias
        cands = [(tid, e) for tid, e in seen.items() if e["name"].strip().lower() in alias]
        cands.sort(key=lambda x: -x[1]["latest"])
        if cands:
            tid, e = cands[0]
            active = str(tid)
            latest = datetime.fromtimestamp(e["latest"], timezone.utc).date().isoformat()
            n_recent = len(e["matches"])
            src = "proMatches"
            for (st, mid, oid, oname, win, sid, stype, lid) in e["matches"]:
                rec_rows.append({"org": org, "team_id": tid, "match_id": mid,
                                 "date": datetime.fromtimestamp(st, timezone.utc).date().isoformat(),
                                 "opp_id": oid, "opp_name": oname, "win": int(win),
                                 "series_id": sid, "series_type": stype, "leagueid": lid})
            # roster from the 2 most recent matches
            recent_mids = [mid for _, mid, *_ in sorted(e["matches"], reverse=True)][:2]
            rosters = []
            for mid in recent_mids:
                try:
                    ids, names = roster_from_match(mid, tid)
                    if ids:
                        rosters.append((ids, names))
                except Exception as ex:
                    print(f"  [match err] {org} {mid}: {ex!r}")
            if rosters:
                ids0, names0 = rosters[0]
                key = "-".join(sorted(str(a) for a in ids0 if a))
                overlap = (len(set(ids0) & set(rosters[1][0])) if len(rosters) > 1 else len(ids0))
                stable = len(rosters) > 1 and overlap == 5
                conf = "high" if stable and len([a for a in ids0 if a]) == 5 else "medium"
            else:
                key, names0, ids0, stable, conf = "", [], [], False, "low"
            id_rows.append({"organization": org, "ti_alias": t.get("ti_alias", ""),
                            "old_teams_csv_id": t.get("opendota_team_id", ""), "active_team_id": active,
                            "active_source": src, "latest_match_date": latest,
                            "n_recent_maps_seen": n_recent, "roster_key": key,
                            "player_ids": "|".join(str(a) for a in ids0),
                            "player_names": "|".join(names0), "roster_stable": stable,
                            "confidence": conf,
                            "note": "" if active == (t.get("opendota_team_id") or "") else "RE-RESOLVED id"})
            print(f"{org:<17} active {active:>9} ({latest}, {n_recent} recent maps) "
                  f"conf={conf} roster=[{', '.join(names0)}]"
                  + ("" if active == (t.get('opendota_team_id') or '') else "  <-- RE-RESOLVED"))
        else:
            id_rows.append({"organization": org, "ti_alias": t.get("ti_alias", ""),
                            "old_teams_csv_id": t.get("opendota_team_id", ""),
                            "active_team_id": "", "active_source": "not-in-proMatches",
                            "latest_match_date": "", "n_recent_maps_seen": 0, "roster_key": "",
                            "player_ids": "", "player_names": "", "roster_stable": False,
                            "confidence": "low", "note": "not seen in recent proMatches; check Liquipedia"})
            print(f"{org:<17} NOT FOUND in recent proMatches -> manual/Liquipedia check")

    with open(os.path.join(INPUTS, "canonical_identity.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(id_rows[0])); w.writeheader(); w.writerows(id_rows)
    with open(os.path.join(PROC, "recent_matches.csv"), "w", newline="", encoding="utf-8") as fh:
        if rec_rows:
            w = csv.DictWriter(fh, fieldnames=list(rec_rows[0])); w.writeheader(); w.writerows(rec_rows)
    print(f"\nwrote canonical_identity.csv ({len(id_rows)} teams) + recent_matches.csv "
          f"({len(rec_rows)} rows)")


if __name__ == "__main__":
    main()
