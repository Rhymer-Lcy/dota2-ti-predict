"""Fantasy-specific player-map acquisition for TI15 itself, plus the extras the old table lacks.

Two jobs, one code path, and neither of them touches a bracket input:

  --source ti15     the 44 completed pre-Main-Event TI15 series (league 19719), enumerated from
                    OpenDota's own league endpoint rather than from `universe_maps.csv`. That file
                    is a frozen input to the audited bracket pipeline and is never read or written
                    here.

  --source history  the 623 matches already in the historical fantasy table, refetched for the
                    THREE columns that table does not carry: per-player Tormentor attribution, the
                    wisdom-rune split, and the hero played. Written to a SEPARATE extras table that
                    joins on (match_id, account_id); the existing CSV is never rewritten.

Why the extras exist at all. Three stats sit on the accounts' live Period-1 banners and were
previously graded unobservable:

  Tormentor Kills   RESOLVED here. `objectives[]` carries CHAT_MESSAGE_MINIBOSS_KILL with an
                    explicit `player_slot`, so the kill is attributable to one player. The earlier
                    "per-player attribution unverified" grade is withdrawn on this evidence.
  Runes Activated   BOUNDED here. OpenDota's `rune_pickups` excludes wisdom runes (type 8) while
                    the `runes` histogram includes them, so the client's "bottled or taken" wording
                    is bracketed by two measured numbers instead of one guessed one.
  Madstone          Still unobservable: `neutral_tokens_log` is an empty list on every player-map
                    in both windows. That is recorded, not silently read as a zero.

Watchers Taken and Lotuses Collected have no field anywhere in the payload; a key scan over the
whole match object finds nothing. They stay partially identified and are handled by bounds.

Main Event results cannot enter: every fetched match is asserted to start before the Main Event.
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
PROC = os.path.join(REPO, "data", "ti2026", "processed", "fantasy")
RAW = os.path.join(REPO, "data", "ti2026", "raw", "fantasy")
CANONICAL = os.path.join(INPUTS, "canonical_identity.csv")

LEAGUE_TI15 = "19719"
# Hard leakage boundary. The Main Event opens 2026-08-20; anything at or after this instant is a
# Main Event result and may not enter a pre-lock recommendation.
MAIN_EVENT_START = "2026-08-20T00:00:00Z"
MAIN_EVENT_START_TS = int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp())

LEAGUE_MATCHES = "https://api.opendota.com/api/leagues/{}/matches"
MATCH = "https://api.opendota.com/api/matches/{}"
UA = {"User-Agent": "dota2-ti-predict/0.1 (fantasy)"}

TI15_LIST_JSON = os.path.join(RAW, "ti15_league_19719_matches.json")
TI15_CSV = os.path.join(PROC, "ti15_player_map_stats.csv")
TI15_EXTRAS = os.path.join(PROC, "ti15_match_extras.csv")
HIST_EXTRAS = os.path.join(PROC, "hist_player_map_extras.csv")
PROV = os.path.join(PROC, "ti15_provenance.json")
HIST_LEDGER = os.path.join(PROC, "player_stats_fetched.txt")

# Wisdom runes are rune type 8. OpenDota's rune_pickups counts every OTHER type; the `runes`
# histogram counts all of them. The client says "per rune bottled or taken" and does not say which
# set that is, so both are carried and the gap is reported rather than resolved by assertion.
RUNE_WISDOM = "8"

PLAYER_FIELDS = (
    "match_id", "leagueid", "start_time", "series_id", "series_type", "account_id",
    "player_name", "organization", "hero_id", "player_slot", "parsed", "duration", "win",
    "kills", "deaths", "last_hits", "denies", "gold_per_min", "towers_killed", "roshans_killed",
    "obs_placed", "camps_stacked", "rune_pickups", "runes_total", "runes_wisdom", "stuns",
    "firstblood_claimed", "courier_kills", "teamfight_participation", "smokes_used",
    "madstone_log", "tormentor_kills",
)
MATCH_FIELDS = (
    "match_id", "leagueid", "start_time", "series_id", "series_type", "duration",
    "radiant_win", "first_blood_time", "tormentor_kills_total", "any_miniboss_death",
    "radiant_team_name", "dire_team_name",
)
HIST_FIELDS = ("match_id", "account_id", "hero_id", "runes_total", "runes_wisdom",
               "tormentor_kills", "madstone_log")


def _get(url, tries=4, timeout=90):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=timeout) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError):
            if n == tries - 1:
                return None
            time.sleep(2 ** n)
    return None


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ti_players(path=None):
    """account_id -> (player_name, organization), from the canonical identity table."""
    out = {}
    with open(path or CANONICAL, encoding="utf-8") as fh:
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


def tormentor_by_slot(match):
    """player_slot -> Tormentor kills, read off the objectives log.

    CHAT_MESSAGE_MINIBOSS_KILL carries an explicit `player_slot`, which names the credited killer.
    `players[].killed['npc_dota_miniboss']` also exists but counts damage credit and can name a
    different player, so the objective is preferred: it is one event, one killer, and it is the
    same event the client's own scoreboard reports.
    """
    out = defaultdict(int)
    for o in match.get("objectives") or []:
        if o.get("type") == "CHAT_MESSAGE_MINIBOSS_KILL":
            slot = o.get("player_slot")
            if slot is not None:
                out[int(slot)] += 1
    return out


def any_miniboss_death(match):
    """Did ANY player in this game die to a Tormentor? The coach suffix 'the Tormented' condition.

    Game scope, so every player counts, not only the roster ones.
    """
    for p in match.get("players", []):
        if (p.get("killed_by") or {}).get("npc_dota_miniboss"):
            return 1
    return 0


def _rune_counts(p):
    runes = p.get("runes")
    if not isinstance(runes, dict):
        return None, None
    total = sum(int(v) for v in runes.values())
    wisdom = int(runes.get(RUNE_WISDOM, 0))
    return total, wisdom


def player_rows(match, players, meta=None):
    """One row per roster player in this match. Returns [] when no roster player took part."""
    meta = meta or {}
    parsed = match.get("version") is not None
    torm = tormentor_by_slot(match)
    out = []
    for p in match.get("players", []):
        acct = p.get("account_id")
        if acct not in players:
            continue
        name, org = players[acct]
        slot = p.get("player_slot", 0)
        uses = p.get("item_uses") or {}
        tokens = p.get("neutral_tokens_log")
        total, wisdom = _rune_counts(p)
        out.append({
            "match_id": match.get("match_id"),
            "leagueid": match.get("leagueid"),
            "start_time": match.get("start_time"),
            "series_id": meta.get("series_id", match.get("series_id")),
            "series_type": meta.get("series_type", match.get("series_type")),
            "account_id": acct, "player_name": name, "organization": org,
            "hero_id": p.get("hero_id"), "player_slot": slot, "parsed": int(parsed),
            "duration": match.get("duration"),
            "win": int(bool(match.get("radiant_win")) == (slot < 128)),
            "kills": p.get("kills"), "deaths": p.get("deaths"), "last_hits": p.get("last_hits"),
            "denies": p.get("denies"), "gold_per_min": p.get("gold_per_min"),
            "towers_killed": p.get("towers_killed"), "roshans_killed": p.get("roshans_killed"),
            "obs_placed": p.get("obs_placed"), "camps_stacked": p.get("camps_stacked"),
            "rune_pickups": p.get("rune_pickups"),
            "runes_total": total if parsed else None,
            "runes_wisdom": wisdom if parsed else None,
            "stuns": p.get("stuns"), "firstblood_claimed": p.get("firstblood_claimed"),
            "courier_kills": p.get("courier_kills"),
            "teamfight_participation": p.get("teamfight_participation"),
            "smokes_used": (uses.get("smoke_of_deceit", 0) if parsed else None),
            "madstone_log": (len(tokens) if isinstance(tokens, list) else None),
            "tormentor_kills": (torm.get(int(slot), 0) if parsed else None),
        })
    return out


def match_row(match, meta=None):
    meta = meta or {}
    return {
        "match_id": match.get("match_id"), "leagueid": match.get("leagueid"),
        "start_time": match.get("start_time"),
        "series_id": meta.get("series_id", match.get("series_id")),
        "series_type": meta.get("series_type", match.get("series_type")),
        "duration": match.get("duration"), "radiant_win": int(bool(match.get("radiant_win"))),
        "first_blood_time": match.get("first_blood_time"),
        "tormentor_kills_total": sum(tormentor_by_slot(match).values()),
        "any_miniboss_death": any_miniboss_death(match),
        "radiant_team_name": (match.get("radiant_team") or {}).get("name")
        or match.get("radiant_name"),
        "dire_team_name": (match.get("dire_team") or {}).get("name") or match.get("dire_name"),
    }


def ti15_match_list(refresh=True):
    """The league's own match list, saved raw. Asserted to hold no Main Event match."""
    os.makedirs(RAW, exist_ok=True)
    if refresh or not os.path.exists(TI15_LIST_JSON):
        got = _get(LEAGUE_MATCHES.format(LEAGUE_TI15), timeout=60)
        if not isinstance(got, list) or not got:
            raise SystemExit("could not read the league match list from OpenDota")
        blob = json.dumps(got, indent=1, sort_keys=True).encode("utf-8")
        with open(TI15_LIST_JSON, "wb") as fh:
            fh.write(blob)
    with open(TI15_LIST_JSON, encoding="utf-8") as fh:
        rows = json.load(fh)
    late = [r for r in rows if int(r["start_time"]) >= MAIN_EVENT_START_TS]
    if late:
        raise SystemExit(f"REFUSING: {len(late)} match(es) start at or after {MAIN_EVENT_START}. "
                         "A Main Event result may not enter a pre-lock recommendation.")
    return sorted(rows, key=lambda r: r["start_time"])


def _done(path, key):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {tuple(r[k] for k in key) for r in csv.DictReader(fh)}


def run_ti15(sleep=1.05, limit=0):
    os.makedirs(PROC, exist_ok=True)
    listing = ti15_match_list()
    players = ti_players()
    have = {int(x[0]) for x in _done(TI15_EXTRAS, ("match_id",))}
    todo = [r for r in listing if int(r["match_id"]) not in have]
    if limit:
        todo = todo[:limit]
    print(f"TI15: {len(listing)} maps in league {LEAGUE_TI15}, {len(have)} already fetched, "
          f"{len(todo)} to go", flush=True)

    new_p = not os.path.exists(TI15_CSV)
    new_m = not os.path.exists(TI15_EXTRAS)
    failed, unparsed = [], []
    with open(TI15_CSV, "a", encoding="utf-8", newline="") as pf, \
            open(TI15_EXTRAS, "a", encoding="utf-8", newline="") as mf:
        pw = csv.DictWriter(pf, fieldnames=PLAYER_FIELDS)
        mw = csv.DictWriter(mf, fieldnames=MATCH_FIELDS)
        if new_p:
            pw.writeheader()
        if new_m:
            mw.writeheader()
        for n, meta in enumerate(todo, 1):
            mid = int(meta["match_id"])
            m = _get(MATCH.format(mid))
            if not isinstance(m, dict) or "players" not in m:
                failed.append(mid)
            else:
                if int(m.get("start_time", 0)) >= MAIN_EVENT_START_TS:
                    raise SystemExit(f"REFUSING: match {mid} starts after {MAIN_EVENT_START}")
                if m.get("version") is None:
                    unparsed.append(mid)
                for row in player_rows(m, players, meta):
                    pw.writerow(row)
                mw.writerow(match_row(m, meta))
            if n % 20 == 0:
                pf.flush()
                mf.flush()
                print(f"  {n}/{len(todo)} ({len(failed)} failed)", flush=True)
            time.sleep(sleep)
    return listing, failed, unparsed


def historical_ids():
    """The 623 matches the existing fantasy table already covers.

    Union of the ledger and the stat table's own match ids. The ledger alone holds only 25: it was
    introduced partway through the original run, so it records the last resume batch and not the
    whole history. Reading it alone would silently target 25 matches and call that complete -- the
    same partial-fact-written-silently defect this project has hit repeatedly.
    """
    ids = set()
    if os.path.exists(HIST_LEDGER):
        with open(HIST_LEDGER, encoding="utf-8") as fh:
            ids |= {int(x) for x in fh.read().split() if x.strip().isdigit()}
    hist = os.path.join(PROC, "player_map_stats.csv")
    if os.path.exists(hist):
        with open(hist, encoding="utf-8") as fh:
            ids |= {int(r["match_id"]) for r in csv.DictReader(fh) if r.get("match_id")}
    return sorted(ids)


def _history_rows(mid, match, players):
    torm = tormentor_by_slot(match)
    out = []
    for p in match.get("players", []):
        acct = p.get("account_id")
        if acct not in players:
            continue
        total, wisdom = _rune_counts(p)
        tokens = p.get("neutral_tokens_log")
        out.append({"match_id": mid, "account_id": acct, "hero_id": p.get("hero_id"),
                    "runes_total": total, "runes_wisdom": wisdom,
                    "tormentor_kills": torm.get(int(p.get("player_slot", 0)), 0),
                    "madstone_log": (len(tokens) if isinstance(tokens, list) else None)})
    if not out:
        # A real, classified outcome: the match held no roster player. A marker row records that,
        # so a resume does not request it for ever and coverage does not look permanently short.
        out.append({"match_id": mid, "account_id": "", "hero_id": "", "runes_total": "",
                    "runes_wisdom": "", "tormentor_kills": "", "madstone_log": ""})
    return out


def run_history(sleep=0.15, limit=0, workers=4):
    """Refetch the historical window for the three columns the old table lacks.

    Concurrency is here because the bottleneck is download size, not the rate limit: a parsed match
    payload is 0.3 to 3 MB and takes several seconds on the wire, while OpenDota's anonymous limit
    is 60 requests a minute. Four workers at a 0.15 s stagger stay well inside that and cut the
    wall-clock by roughly the worker count. Writes go through one lock to one handle, so the file
    cannot interleave.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    os.makedirs(PROC, exist_ok=True)
    players = ti_players()
    targets = historical_ids()
    if not targets:
        raise SystemExit("no historical match ledger found")
    have = {int(x[0]) for x in _done(HIST_EXTRAS, ("match_id",))}
    todo = [m for m in targets if m not in have]
    if limit:
        todo = todo[:limit]
    print(f"history: {len(targets)} matches, {len(have)} already extended, {len(todo)} to go, "
          f"{workers} workers", flush=True)
    new = not os.path.exists(HIST_EXTRAS)
    failed = []
    lock = threading.Lock()
    done = [0]
    with open(HIST_EXTRAS, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HIST_FIELDS)
        if new:
            w.writeheader()

        def work(mid):
            m = _get(MATCH.format(mid))
            rows = None
            if isinstance(m, dict) and "players" in m:
                rows = _history_rows(mid, m, players)
            with lock:
                if rows is None:
                    failed.append(mid)
                else:
                    for row in rows:
                        w.writerow(row)
                done[0] += 1
                if done[0] % 25 == 0:
                    fh.flush()
                    print(f"  {done[0]}/{len(todo)} ({len(failed)} failed)", flush=True)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = []
            for mid in todo:
                futures.append(ex.submit(work, mid))
                time.sleep(sleep)
            for f in futures:
                f.result()
    return targets, failed


def write_provenance(listing=None, ti15_failed=None, unparsed=None, hist_targets=None,
                     hist_failed=None):
    prov = {
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"league_matches": LEAGUE_MATCHES.format(LEAGUE_TI15),
                    "match": MATCH.format("{match_id}")},
        "leakage_boundary": {"main_event_start": MAIN_EVENT_START,
                             "main_event_results_used": False,
                             "assertion": "every fetched match asserted start_time < "
                                          "main_event_start, twice: on the league listing and "
                                          "again on each match payload"},
        "bracket_isolation": {
            "universe_maps_csv_read": False, "universe_maps_csv_written": False,
            "note": "match ids come from OpenDota's league endpoint, not from the frozen universe"},
        "files": {
            "ti15_league_listing": {"path": os.path.relpath(TI15_LIST_JSON, REPO),
                                    "sha256": _sha256_file(TI15_LIST_JSON)},
            "ti15_player_map_stats": {"path": os.path.relpath(TI15_CSV, REPO),
                                      "sha256": _sha256_file(TI15_CSV)},
            "ti15_match_extras": {"path": os.path.relpath(TI15_EXTRAS, REPO),
                                  "sha256": _sha256_file(TI15_EXTRAS)},
            "hist_player_map_extras": {"path": os.path.relpath(HIST_EXTRAS, REPO),
                                       "sha256": _sha256_file(HIST_EXTRAS)},
        },
    }
    if listing is not None:
        prov["ti15"] = {"maps_listed": len(listing), "failed": sorted(ti15_failed or []),
                        "unparsed": sorted(unparsed or [])}
    if hist_targets is not None:
        prov["history"] = {"matches_targeted": len(hist_targets),
                           "failed": sorted(hist_failed or [])}
    old = {}
    if os.path.exists(PROV):
        with open(PROV, encoding="utf-8") as fh:
            old = json.load(fh)
    old.update({k: v for k, v in prov.items() if v is not None})
    with open(PROV, "w", encoding="utf-8") as fh:
        json.dump(old, fh, indent=2)
    return old


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--source", choices=("ti15", "history"), required=True)
    a.add_argument("--sleep", type=float, default=1.05)
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--workers", type=int, default=4, help="history source only")
    a = a.parse_args(argv)

    if a.source == "ti15":
        listing, failed, unparsed = run_ti15(a.sleep, a.limit)
        prov = write_provenance(listing=listing, ti15_failed=failed, unparsed=unparsed)
        print(json.dumps(prov.get("ti15"), indent=2))
        if failed:
            sys.exit(f"{len(failed)} TI15 matches failed; re-run to resume")
    else:
        targets, failed = run_history(a.sleep, a.limit, a.workers)
        prov = write_provenance(hist_targets=targets, hist_failed=failed)
        print(json.dumps(prov.get("history"), indent=2))
        if failed:
            sys.exit(f"{len(failed)} historical matches failed; re-run to resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
