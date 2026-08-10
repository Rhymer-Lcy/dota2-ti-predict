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
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
PROC = os.path.join(REPO, "data", "ti2026", "processed")
FANTASY_PROC = os.path.join(PROC, "fantasy")
UNIVERSE = os.path.join(PROC, "universe_maps.csv")
CANONICAL = os.path.join(INPUTS, "canonical_identity.csv")
OUT_CSV = os.path.join(FANTASY_PROC, "player_map_stats.csv")
OUT_PROV = os.path.join(FANTASY_PROC, "player_stats_provenance.json")
# A match can be fetched successfully and still produce no rows: the five leagues contain plenty of
# matches between teams that did not qualify for TI. Without a ledger of what was actually
# requested, those matches look permanently missing -- they would be re-requested on every resume
# and would hold measured coverage below the threshold for ever.
OUT_LEDGER = os.path.join(FANTASY_PROC, "player_stats_fetched.txt")

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


def done_matches(path=None, ledger=None):
    """Every match already requested, whether or not it yielded rows.

    Reads the ledger and unions in the ids present in the stat table, so a table written before the
    ledger existed still counts as covered rather than being re-fetched.
    """
    out = set()
    ledger = ledger or OUT_LEDGER
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as fh:
            out |= {int(x) for x in fh.read().split() if x.strip().isdigit()}
    path = path or OUT_CSV
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            out |= {int(r["match_id"]) for r in csv.DictReader(fh) if r.get("match_id")}
    return out


def _sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def coverage_report(stats_path=None, ledger=None):
    """What the table actually contains, per match, per stat, per player and per team.

    Written so that "we have the data" is a measurement rather than an assertion. A match that was
    fetched but held no TI player is a real, classified outcome, not a gap.
    """
    stats_path = stats_path or OUT_CSV
    targets = {t[0] for t in target_matches(DEFAULT_LEAGUES)}
    requested = done_matches(stats_path, ledger)
    rows = []
    with open(stats_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with_rows = {int(r["match_id"]) for r in rows}
    parsed_rows = [r for r in rows if r["parsed"] == "1"]
    stat_cols = [f for f in FIELDS if f not in
                 ("match_id", "leagueid", "start_time", "account_id", "player_name",
                  "organization", "parsed", "duration", "win")]
    usable = {c: sum(1 for r in parsed_rows if r.get(c) not in ("", "None", None))
              for c in stat_cols}
    players = ti_players()
    seen = {int(r["account_id"]) for r in parsed_rows}
    by_team = defaultdict(lambda: {"players_with_data": set(), "player_maps": 0})
    for r in parsed_rows:
        by_team[r["organization"]]["players_with_data"].add(int(r["account_id"]))
        by_team[r["organization"]]["player_maps"] += 1
    return {
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "matches": {"targeted": len(targets), "requested": len(targets & requested),
                    "with_ti_players": len(with_rows),
                    "fetched_without_ti_players": len(targets & requested) - len(with_rows),
                    "failed": len(targets - requested),
                    "coverage": round(len(targets & requested) / len(targets), 4)},
        "player_maps": {"total": len(rows), "parsed": len(parsed_rows),
                        "unparsed_dropped": len(rows) - len(parsed_rows),
                        "parse_rate": round(len(parsed_rows) / len(rows), 4) if rows else None},
        "usable_per_stat": {c: {"rows": n,
                                "rate": round(n / len(parsed_rows), 4) if parsed_rows else None}
                            for c, n in sorted(usable.items())},
        "players": {"ti_roster_size": len(players), "with_parsed_data": len(seen & set(players)),
                    "without_data": sorted(players[a][0] for a in set(players) - seen)},
        "teams": {t: {"players_with_data": len(v["players_with_data"]),
                      "player_maps": v["player_maps"]}
                  for t, v in sorted(by_team.items())},
        "stat_table_sha256": _sha256(stats_path),
        "source": API.format("{match_id}"),
    }


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--leagues", default=",".join(DEFAULT_LEAGUES))
    a.add_argument("--limit", type=int, default=0, help="stop after N new matches (0 = all)")
    a.add_argument("--sleep", type=float, default=1.05, help="seconds between requests")
    a.add_argument("--report", action="store_true",
                   help="print the coverage report for the existing table and exit")
    a = a.parse_args(argv)

    os.makedirs(FANTASY_PROC, exist_ok=True)
    if a.report:
        print(json.dumps(coverage_report(), indent=2))
        return 0
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
    failed, fetched, empty = [], 0, 0
    with open(OUT_CSV, "a", encoding="utf-8", newline="") as fh, \
            open(OUT_LEDGER, "a", encoding="utf-8") as lg:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_header:
            w.writeheader()
        for n, (mid, _lg, _ts) in enumerate(todo, 1):
            m = _get(API.format(mid))
            if not isinstance(m, dict) or "players" not in m:
                failed.append(mid)
            else:
                got = _rows_for(m, players)
                for row in got:
                    w.writerow(row)
                if not got:
                    empty += 1
                lg.write(str(mid) + "\n")
                fetched += 1
            if n % 25 == 0:
                fh.flush()
                lg.flush()
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
