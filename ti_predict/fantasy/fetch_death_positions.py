"""Death positions, for the one suffix still unpriced: the Cruel.

The Cruel fires when a player is killed inside their OWN fountain, which is a positional condition.
An earlier round recorded that the source carries no death positions. That was wrong, and is
withdrawn: OpenDota does expose deaths_pos -- not on the player object, but inside
teamfights[].players[]. It is therefore a partial view by construction, covering deaths that fall
inside a detected teamfight and no others, and this module measures that coverage rather than
assuming it away.

Fountain regions are calibrated from the data, never typed in from memory. Deaths credited to
dota_fountain in killed_by must by definition have happened inside a fountain -- the ENEMY one,
since that is the only fountain that can kill you -- so those deaths locate one fountain, and the
victim's side tells us which.

Per match:
  teamfight death positions, per player, with side and slot
  total deaths and teamfight-covered deaths, for coverage
  which players were killed by dota_fountain at least once, for calibration
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

OUT_CSV = os.path.join(fp.FANTASY_PROC, "death_positions.csv")
FIELDS = ("match_id", "account_id", "player_slot", "is_radiant", "deaths",
          "teamfight_deaths", "fountain_killer_deaths", "positions")
FOUNTAIN_KILLER = "dota_fountain"


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


def extract(match):
    """One row per player: their teamfight death positions, side, and fountain-kill count.

    teamfights[].players is positional -- index i is the same player as match players[i] -- which
    is what lets a death position be tied to a side at all.
    """
    players = match.get("players") or []
    acc = [{"match_id": match.get("match_id"),
            "account_id": p.get("account_id"),
            "player_slot": p.get("player_slot"),
            "is_radiant": 1 if p.get("isRadiant") else 0,
            "deaths": p.get("deaths") or 0,
            "teamfight_deaths": 0,
            "fountain_killer_deaths": sum(v for k, v in (p.get("killed_by") or {}).items()
                                          if k == FOUNTAIN_KILLER),
            "positions": []} for p in players]
    for fight in match.get("teamfights") or []:
        for i, tp in enumerate(fight.get("players") or []):
            if i >= len(acc):
                break
            for x, col in (tp.get("deaths_pos") or {}).items():
                for y, cnt in col.items():
                    acc[i]["positions"].append([int(x), int(y), int(cnt)])
                    acc[i]["teamfight_deaths"] += int(cnt)
    for row in acc:
        row["positions"] = json.dumps(row["positions"], separators=(",", ":"))
    return acc


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--sleep", type=float, default=0.9)
    a.add_argument("--limit", type=int, default=0)
    a = a.parse_args(argv)
    os.makedirs(fp.FANTASY_PROC, exist_ok=True)
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
                for row in extract(m):
                    w.writerow(row)
            if n % 25 == 0:
                fh.flush()
                print(f"  {n}/{len(todo)} ({failed} failed)", flush=True)
            time.sleep(a.sleep)
    cov = len(done_matches() & {t[0] for t in targets}) / len(targets)
    print(f"death-position coverage {cov:.3f}; {failed} failed this run", flush=True)
    return 0 if cov >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())
