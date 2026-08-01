"""B0 data-audit fetcher: pull OpenDota coverage + roster for the TI 2026 teams.

Free OpenDota API (no key; 60 req/min). Writes raw JSON to data/ti2026/raw/ (gitignored), a
tracked provenance line per pull to data/ti2026/inputs/fetch-manifest.jsonl, and a machine summary
to data/ti2026/processed/b0_audit.csv (gitignored). Prints a human summary.

This is an AUDIT, not a model: it establishes match coverage, recency, opponent count, and current
roster so we can judge which data are usable before fitting anything (see docs/modeling-plan.md).

Run:  python -m ti_predict.fetch_opendota
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
UA = {"User-Agent": "dota2-ti-predict/0.1 (audit)"}
NOW = datetime.now(timezone.utc)


def _get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    return raw, json.loads(raw)


def _manifest(endpoint, team, team_id, raw, n):
    os.makedirs(INPUTS, exist_ok=True)
    line = {"endpoint": endpoint, "team": team, "team_id": team_id,
            "fetched_at": NOW.isoformat(), "data_cutoff": NOW.isoformat(),
            "n_records": n, "sha256": hashlib.sha256(raw).hexdigest()}
    with open(os.path.join(INPUTS, "fetch-manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def audit():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(PROC, exist_ok=True)
    teams = list(csv.DictReader(open(os.path.join(INPUTS, "teams.csv"), encoding="utf-8")))
    rows = []
    for t in teams:
        tid = (t.get("opendota_team_id") or "").strip()
        name = t["team"]
        if not tid:
            print(f"[skip] {name}: no team_id"); continue
        try:
            mraw, matches = _get(f"/teams/{tid}/matches"); time.sleep(1.1)
            praw, players = _get(f"/teams/{tid}/players"); time.sleep(1.1)
        except Exception as e:
            print(f"[err ] {name} ({tid}): {e!r}"); continue
        with open(os.path.join(RAW, f"{tid}_matches.json"), "wb") as fh: fh.write(mraw)
        with open(os.path.join(RAW, f"{tid}_players.json"), "wb") as fh: fh.write(praw)
        _manifest("teams/matches", name, tid, mraw, len(matches))
        _manifest("teams/players", name, tid, praw, len(players))

        starts = [m["start_time"] for m in matches if m.get("start_time")]
        wins = sum(1 for m in matches if m.get("radiant") == m.get("radiant_win"))
        d90 = sum(1 for s in starts if (NOW.timestamp() - s) <= 90 * 86400)
        d365 = sum(1 for s in starts if (NOW.timestamp() - s) <= 365 * 86400)
        leagues = len({m.get("leagueid") for m in matches})
        earliest = datetime.fromtimestamp(min(starts), timezone.utc).date().isoformat() if starts else "-"
        latest = datetime.fromtimestamp(max(starts), timezone.utc).date().isoformat() if starts else "-"
        cur = [p for p in players if p.get("is_current_team_member")]
        rows.append({
            "team": name, "team_id": tid, "maps": len(matches), "wins": wins,
            "losses": len(matches) - wins, "earliest": earliest, "latest": latest,
            "maps_90d": d90, "maps_365d": d365, "leagues": leagues,
            "current_roster": len(cur),
            "roster_min_games": min([p.get("games_played", 0) for p in cur], default=0),
        })
        print(f"{name:<17}{tid:>9} | maps {len(matches):>4} ({wins}-{len(matches)-wins}) "
              f"| {earliest}→{latest} | 90d {d90:>3} 365d {d365:>4} | leagues {leagues:>3} "
              f"| roster {len(cur)} (min games {rows[-1]['roster_min_games']})")

    if rows:
        with open(os.path.join(PROC, "b0_audit.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        print(f"\nwrote {len(rows)} rows -> data/ti2026/processed/b0_audit.csv "
              f"(raw + manifest also written)")


if __name__ == "__main__":
    audit()
