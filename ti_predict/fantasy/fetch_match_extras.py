"""Match-level facts the coach suffixes need, which the player-stat table never carried.

Four of the eight offered suffixes were previously written off as uncomputable on the grounds that
the fetched CSV had no column for them. That was the wrong test: the question is what the SOURCE
holds, not what this project happened to store. OpenDota does carry first_blood_time, and it carries
enough per-player attribution to bound a Tormentor death, so two of the four become exactly
computable and a third becomes bounded.

Per match:
  first_blood_time       -- negative when first blood lands before the starting horn
  tormentor_damage_taken -- players who took damage from npc_dota_miniboss
  unattributed_deaths    -- deaths not credited to an enemy hero in killed_by, which is the only
                            handle on "died to something that is not a hero"
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

OUT_CSV = os.path.join(fp.FANTASY_PROC, "match_extras.csv")
FIELDS = ("match_id", "first_blood_time", "duration",
          "roster_tormentor_damage", "roster_unattributed_deaths", "roster_deaths",
          "all_tormentor_damage", "all_unattributed_deaths", "all_deaths")
TORMENTOR = "npc_dota_miniboss"


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


def extract(match, players):
    """Match-level suffix facts, counted twice: over the TI players, and over all ten.

    The Tormented's scope is not settled. The shipped string says "if any player dies to a
    Tormentor", which reads as any of the ten; the community definition says "any roster player".
    Both counts are recorded so the ambiguity is priced rather than assumed away.
    """
    out = {"match_id": match.get("match_id"),
           "first_blood_time": match.get("first_blood_time"),
           "duration": match.get("duration")}
    for tag, restrict in (("roster", True), ("all", False)):
        torm = unattr = deaths = 0
        for p in match.get("players", []):
            if restrict and p.get("account_id") not in players:
                continue
            d = p.get("deaths") or 0
            deaths += d
            by_hero = sum((p.get("killed_by") or {}).values())
            # killed_by credits enemy heroes only, so the remainder died to something else;
            # a zero here is an EXACT negative: nobody died to a Tormentor in that match
            unattr += max(0, d - by_hero)
            if TORMENTOR in (p.get("damage_taken") or {}):
                torm += 1
        out[f"{tag}_tormentor_damage"] = torm
        out[f"{tag}_unattributed_deaths"] = unattr
        out[f"{tag}_deaths"] = deaths
    return out


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
                w.writerow(extract(m, players))
            if n % 25 == 0:
                fh.flush()
                print(f"  {n}/{len(todo)} ({failed} failed)", flush=True)
            time.sleep(a.sleep)
    cov = len(done_matches() & {t[0] for t in targets}) / len(targets)
    print(f"extras coverage {cov:.3f}; {failed} failed this run", flush=True)
    return 0 if cov >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())
