"""Per-player, per-map fantasy stats for the TI2026 field, fetched from OpenDota.

Scope: the matches already in the frozen track's universe that belong to a configured set of recent
top-tier leagues. Reusing the universe means this module never re-decides which matches exist -- it
only adds the player dimension the team-level pipeline never needed.

Two properties this has to hold, both learned the hard way elsewhere in this repo:
  - resumable and append-only, so a rate-limited or interrupted run never silently produces a short
    table that later looks complete;
  - fail closed on coverage, so a run that could not reach most of its matches exits non-zero
    instead of handing a partial table to the baseline.

Parse status matters more here than anywhere else in the project. Thirteen of the eighteen fantasy
stats only exist on a PARSED match; on an unparsed one OpenDota returns nulls that are not zeros.
Every row therefore carries `parsed`, and the baseline is required to filter on it rather than
averaging nulls into existence.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
PROC = os.path.join(REPO, "data", "ti2026", "processed")
FANTASY_PROC = os.path.join(PROC, "fantasy")
UNIVERSE = os.path.join(PROC, "universe_maps.csv")
CANONICAL = os.path.join(INPUTS, "canonical_identity.csv")
OUT_CSV = os.path.join(FANTASY_PROC, "player_map_stats.csv")
OUT_PROV = os.path.join(FANTASY_PROC, "player_stats_provenance.json")

API = "https://api.opendota.com/api/matches/{}"
# OpenDota answers 403 to the default urllib agent; every fetcher in this repo identifies itself.
UA = {"User-Agent": "dota2-ti-predict/0.1 (fantasy)"}
# The five recent top-tier events that make up the current-form window. Chosen to match the window
# the public 2026 fantasy calculator uses, so the two can be compared like for like.
DEFAULT_LEAGUES = ("19101", "19543", "19696", "19785", "20009")
MIN_COVERAGE = 0.95

FIELDS = ("match_id", "leagueid", "start_time", "account_id", "player_name", "organization",
          "parsed", "duration", "win", "kills", "deaths", "last_hits", "denies", "gold_per_min",
          "towers_killed", "roshans_killed", "obs_placed", "camps_stacked", "rune_pickups",
          "stuns", "firstblood_claimed", "courier_kills", "teamfight_participation",
          "smokes_used", "madstone")


def _get(url, tries=4):
    """One GET with backoff. Returns the decoded body or None; never raises on a transient error."""
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError):
            if n == tries - 1:
                return None
            time.sleep(2 ** n)
    return None


def ti_players(path=None):
    """account_id -> (player_name, organization) for the 16 TI rosters."""
    path = path or CANONICAL
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ids = [i for i in row["player_ids"].split("|") if i]
            names = row["player_names"].split("|")
            if len(ids) != len(names):
                raise SystemExit(f"canonical_identity.csv: {row['organization']} has "
                                 f"{len(ids)} ids and {len(names)} names")
            for i, n in zip(ids, names):
                out[int(i)] = (n, row["organization"])
    if not out:
        raise SystemExit("canonical_identity.csv produced no players")
    return out


def target_matches(leagues, path=None):
    """The universe matches belonging to the configured leagues, oldest first."""
    path = path or UNIVERSE
    if not os.path.exists(path):
        raise SystemExit(f"universe not found: {path}; run the frozen track's data build first")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["leagueid"] in leagues:
                rows.append((int(r["match_id"]), r["leagueid"], int(r["start_time"])))
    return sorted(set(rows), key=lambda t: t[2])


def _rows_for(match, players):
    """Extract one row per TI player in this match. Returns [] when no TI player took part."""
    out = []
    parsed = match.get("version") is not None
    for p in match.get("players", []):
        acct = p.get("account_id")
        if acct not in players:
            continue
        name, org = players[acct]
        slot = p.get("player_slot", 0)
        win = int(bool(match.get("radiant_win")) == (slot < 128))
        uses = p.get("item_uses") or {}
        tokens = p.get("neutral_tokens_log")
        out.append({
            "match_id": match.get("match_id"), "leagueid": match.get("leagueid"),
            "start_time": match.get("start_time"), "account_id": acct, "player_name": name,
            "organization": org, "parsed": int(parsed), "duration": match.get("duration"),
            "win": win,
            "kills": p.get("kills"), "deaths": p.get("deaths"), "last_hits": p.get("last_hits"),
            "denies": p.get("denies"), "gold_per_min": p.get("gold_per_min"),
            "towers_killed": p.get("towers_killed"), "roshans_killed": p.get("roshans_killed"),
            "obs_placed": p.get("obs_placed"), "camps_stacked": p.get("camps_stacked"),
            "rune_pickups": p.get("rune_pickups"), "stuns": p.get("stuns"),
            "firstblood_claimed": p.get("firstblood_claimed"),
            "courier_kills": p.get("courier_kills"),
            "teamfight_participation": p.get("teamfight_participation"),
            # absent key means the item was never used, which is a real zero, but only on a parse
            "smokes_used": (uses.get("smoke_of_deceit", 0) if parsed else None),
            "madstone": (len(tokens) if isinstance(tokens, list) else (0 if parsed else None)),
        })
    return out


def done_matches(path=None):
    path = path or OUT_CSV
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {int(r["match_id"]) for r in csv.DictReader(fh) if r.get("match_id")}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--leagues", default=",".join(DEFAULT_LEAGUES))
    a.add_argument("--limit", type=int, default=0, help="stop after N new matches (0 = all)")
    a.add_argument("--sleep", type=float, default=1.05, help="seconds between requests")
    a = a.parse_args(argv)

    os.makedirs(FANTASY_PROC, exist_ok=True)
    leagues = tuple(x.strip() for x in a.leagues.split(",") if x.strip())
    players = ti_players()
    targets = target_matches(leagues)
    if not targets:
        raise SystemExit(f"no universe matches in leagues {leagues}")
    have = done_matches()
    todo = [t for t in targets if t[0] not in have]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(players)} TI players, {len(targets)} matches in {len(leagues)} leagues, "
          f"{len(have)} already fetched, {len(todo)} to go", flush=True)

    new_header = not os.path.exists(OUT_CSV)
    failed, fetched = [], 0
    with open(OUT_CSV, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_header:
            w.writeheader()
        for n, (mid, _lg, _ts) in enumerate(todo, 1):
            m = _get(API.format(mid))
            if not isinstance(m, dict) or "players" not in m:
                failed.append(mid)
            else:
                for row in _rows_for(m, players):
                    w.writerow(row)
                fetched += 1
            if n % 25 == 0:
                fh.flush()
                print(f"  {n}/{len(todo)} ({len(failed)} failed)", flush=True)
            time.sleep(a.sleep)

    covered = done_matches()
    coverage = len(covered & {t[0] for t in targets}) / len(targets)
    prov = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "https://api.opendota.com/api/matches/{match_id}",
            "leagues": list(leagues), "matches_targeted": len(targets),
            "matches_covered": len(covered & {t[0] for t in targets}),
            "coverage": round(coverage, 4), "fetched_this_run": fetched,
            "failed_this_run": failed[:50], "failed_count": len(failed),
            "ti_players": len(players), "min_coverage": MIN_COVERAGE}
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=2)
    print(f"coverage {coverage:.3f} over {len(targets)} matches; "
          f"{len(failed)} failed this run", flush=True)
    if coverage < MIN_COVERAGE:
        sys.exit(f"COVERAGE TOO LOW ({coverage:.3f} < {MIN_COVERAGE}); refusing to declare the "
                 "player-stat table complete. Re-run to resume.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
