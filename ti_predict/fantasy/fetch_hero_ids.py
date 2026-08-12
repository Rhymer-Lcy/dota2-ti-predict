"""Hero played by each TI player in each historical map, for coach-prefix trigger rates.

The eight coach prefixes are hero-conditional, so pricing them needs two things: which hero each
player played, and which colour/attribute categories Valve puts that hero in. This module fetches
the first. It is deliberately separate from the main stat fetch so that the stat table, which is
already complete and validated, is never rewritten.

Resumable and append-only, on the same ledger discipline as fetch_player_stats.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

from ti_predict.fantasy import fetch_player_stats as fp

OUT_CSV = os.path.join(fp.FANTASY_PROC, "player_map_heroes.csv")
FIELDS = ("match_id", "account_id", "player_name", "organization", "hero_id")


def _get(url, tries=4):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=fp.UA)
            with urllib.request.urlopen(req, timeout=60) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError):
            if n == tries - 1:
                return None
            time.sleep(2 ** n)
    return None


def done_matches(path=None):
    path = path or OUT_CSV
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {int(r["match_id"]) for r in csv.DictReader(fh) if r.get("match_id")}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--sleep", type=float, default=0.9)
    a.add_argument("--limit", type=int, default=0)
    a = a.parse_args(argv)
    os.makedirs(fp.FANTASY_PROC, exist_ok=True)
    players = fp.ti_players()
    targets = fp.target_matches(fp.DEFAULT_LEAGUES)
    have = done_matches()
    todo = [t for t in targets if t[0] not in have]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(targets)} matches, {len(have)} done, {len(todo)} to go", flush=True)
    new = not os.path.exists(OUT_CSV)
    failed = 0
    with open(OUT_CSV, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for n, (mid, _lg, _ts) in enumerate(todo, 1):
            m = _get(fp.API.format(mid))
            if not isinstance(m, dict) or "players" not in m:
                failed += 1
            else:
                for p in m.get("players", []):
                    acct = p.get("account_id")
                    if acct in players and p.get("hero_id"):
                        w.writerow({"match_id": mid, "account_id": acct,
                                    "player_name": players[acct][0],
                                    "organization": players[acct][1],
                                    "hero_id": p["hero_id"]})
            if n % 25 == 0:
                fh.flush()
                print(f"  {n}/{len(todo)} ({failed} failed)", flush=True)
            time.sleep(a.sleep)
    cov = len(done_matches() & {t[0] for t in targets}) / len(targets)
    print(f"hero coverage {cov:.3f}; {failed} failed this run", flush=True)
    return 0 if cov >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())
