"""B0 step 2: resolve current team identity + roster (fixes stale/wrong team_ids).

Strategy (all from the free OpenDota API, no key):
  1. scan recent /proMatches (paginated) -> for each org name/alias, the team_id actually used
     in the most recent pro matches (this re-resolves stale ids like BetBoom / LGD);
  2. for each resolved active id, fetch its 2 most recent match details -> extract the five
     account_ids on that team's side = roster_key, and check roster stability across the two;
  3. capture series_id / series_type from proMatches (map<->series linkage for gate 3).

As-of note: this reads matches up to *now*, i.e. the roster "as of today" for the live TI pick.
For the rolling backtest, rosters must be re-frozen at each event's cutoff (no post-cutoff match may
confirm an earlier roster).

Outputs and their contract (both fail closed):
  - processed/identity_resolved.csv  — this module's only table; roster_coverage and
      build_canonical read it. The tracked inputs/canonical_identity.csv is written by
      build_canonical alone, so a partial run here can never erase the multi-id mapping the rating
      universe depends on. A run that fails to resolve all 16 five-player rosters exits non-zero.
  - raw/promatches_scan.json         — MERGED, never replaced (the deep scan from
      scan_promatches.py defines the training window; this module only pages the recent window).

Run:  python -m ti_predict.resolve_identity
"""
import csv
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

# Player nicknames may contain characters outside the Windows console codepage (e.g. card suits);
# without this the pipeline crashes mid-run on such a print (observed 2026-08-09 rehearsal).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

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


def _get(path, tries=4):
    """GET with retries. OpenDota fronts a CDN that returns 5xx in bursts (521/522 observed
    2026-08-10); a single attempt turns a transient outage into missing roster data."""
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


def merge_scan(fetched, path):
    """Merge a fresh shallow scan into the stored pro-match universe; coverage NEVER shrinks.

    This module only needs the RECENT window to re-resolve team ids, but it shares one file with
    scan_promatches.py, whose deep scan defines the rating-universe window. Overwriting turned the
    universe from 9146 maps (2026-02-27..) into 3000 maps (2026-05-17..) and silently shortened every
    training window downstream (observed 2026-08-09 and again 2026-08-10) -- so merge, never replace.
    """
    uniq = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for m in json.load(fh):
                uniq[m["match_id"]] = m
    before = (len(uniq), min((m["start_time"] for m in uniq.values()), default=None))
    for m in fetched:
        uniq[m["match_id"]] = m
    merged = sorted(uniq.values(), key=lambda m: -m["start_time"])
    after = (len(merged), min(m["start_time"] for m in merged))
    if before[1] is not None and (after[0] < before[0] or after[1] > before[1]):
        raise SystemExit(f"pro-match scan coverage regressed ({before} -> {after}); refusing to write")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh)
    return merged


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
    fetched = scan_promatches()
    pm = merge_scan(fetched, os.path.join(RAW, "promatches_scan.json"))
    _manifest("proMatches", f"{PAGES}pages+merge", json.dumps(pm).encode(), len(pm))
    print(f"proMatches: {len(fetched)} fetched -> {len(pm)} in the merged universe, "
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

    # This module writes ONLY to processed/. The tracked inputs/canonical_identity.csv has a single
    # writer, build_canonical.py: when resolve_identity also wrote it, an interrupted or partly
    # failed chain left the tracked table in this intermediate schema with every source_team_ids
    # mapping erased -- and the rating universe resolves TI organizations through exactly that column
    # (observed 2026-08-10, when an OpenDota 5xx burst emptied 14 of 16 rosters).
    with open(os.path.join(PROC, "identity_resolved.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(id_rows[0])); w.writeheader(); w.writerows(id_rows)
    with open(os.path.join(PROC, "recent_matches.csv"), "w", newline="", encoding="utf-8") as fh:
        if rec_rows:
            w = csv.DictWriter(fh, fieldnames=list(rec_rows[0])); w.writeheader(); w.writerows(rec_rows)
    print(f"\nwrote processed/identity_resolved.csv ({len(id_rows)} teams) + recent_matches.csv "
          f"({len(rec_rows)} rows)")
    incomplete = [r["organization"] for r in id_rows if len(r["player_ids"].split("|")) != 5]
    if incomplete:
        raise SystemExit(
            "identity resolution INCOMPLETE for: " + ", ".join(incomplete)
            + "\nRe-run when the match API is healthy; do not continue the chain on a partial "
              "roster (roster_coverage would silently skip those teams).")


if __name__ == "__main__":
    main()
