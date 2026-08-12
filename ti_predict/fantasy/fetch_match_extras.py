"""Match-level facts the coach suffixes need, which the player-stat table never carried.

Four of the eight offered suffixes were previously written off as uncomputable on the grounds that
the fetched CSV had no column for them. That was the wrong test: the question is what the SOURCE
holds, not what this project happened to store.

A correction this module exists to record. An earlier revision assumed `killed_by` credits enemy
heroes only, and treated `deaths - sum(killed_by.values())` as "deaths to something that is not a
hero", hence as an upper bound on Tormentor deaths. That assumption is false. OpenDota documents
`killed_by` only as "who killed the player", with no hero restriction, and the residual it produces
on this window is 53 deaths out of 33,128 -- 0.16 percent. Deaths to towers, creeps, Roshan and
denies are certainly commoner than that in professional play, so `killed_by` is evidently
accounting for non-hero killers too, and the residual is not the quantity the old code named. It
therefore bounds nothing: a Tormentor death that IS recorded in `killed_by` contributes zero to it.

So the Tormentor is counted directly out of `killed_by` instead, and every distinct killer key seen
across the window is written out so the classification rests on an inventory rather than on a guess
about what a field name means.

Per match:
  first_blood_time            -- negative when first blood lands before the starting horn
  tormentor_deaths            -- deaths whose recorded killer is the Tormentor, counted directly
  deaths_with_no_recorded_killer -- deaths `killed_by` does not account for. Named for what it is;
                                 it is NOT "non-hero deaths" and bounds nothing.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from ti_predict.fantasy import fetch_player_stats as fp

OUT_CSV = os.path.join(fp.FANTASY_PROC, "match_extras.csv")
OUT_KILLERS = os.path.join(fp.FANTASY_PROC, "killer_key_inventory.json")
FIELDS = ("match_id", "first_blood_time", "duration",
          "roster_tormentor_damage", "roster_tormentor_deaths",
          "roster_deaths_with_no_recorded_killer", "roster_deaths",
          "all_tormentor_damage", "all_tormentor_deaths",
          "all_deaths_with_no_recorded_killer", "all_deaths")
TORMENTOR = "npc_dota_miniboss"


def is_tormentor(key):
    """Killer keys that denote the Tormentor, matched on the entity name rather than assumed."""
    k = key.lower()
    return "miniboss" in k or "tormentor" in k


def is_hero(key):
    return key.startswith("npc_dota_hero_")


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


def extract(match, players, killers=None):
    """Match-level suffix facts, counted twice: over the TI players, and over all ten.

    The Tormented's scope is not settled. The shipped string says "if any player dies to a
    Tormentor", which reads as any of the ten; the community definition says "any roster player".
    Both counts are recorded so the ambiguity is priced rather than assumed away.
    """
    out = {"match_id": match.get("match_id"),
           "first_blood_time": match.get("first_blood_time"),
           "duration": match.get("duration")}
    for tag, restrict in (("roster", True), ("all", False)):
        dmg = torm = unrec = deaths = 0
        for p in match.get("players", []):
            if restrict and p.get("account_id") not in players:
                continue
            d = p.get("deaths") or 0
            deaths += d
            kb = p.get("killed_by") or {}
            if killers is not None and not restrict:
                killers.update(kb)
            torm += sum(v for k, v in kb.items() if is_tormentor(k))
            # deaths the parser recorded no killer for at all. Not "non-hero deaths": killed_by
            # carries creep and building killers too, so this residual bounds nothing.
            unrec += max(0, d - sum(kb.values()))
            if TORMENTOR in (p.get("damage_taken") or {}):
                dmg += 1
        out[f"{tag}_tormentor_damage"] = dmg
        out[f"{tag}_tormentor_deaths"] = torm
        out[f"{tag}_deaths_with_no_recorded_killer"] = unrec
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
    killers = Counter()
    if os.path.exists(OUT_KILLERS):
        with open(OUT_KILLERS, encoding="utf-8") as fh:
            killers.update(json.load(fh).get("keys", {}))
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
                w.writerow(extract(m, players, killers))
            if n % 25 == 0:
                fh.flush()
                write_killers(killers)
                print(f"  {n}/{len(todo)} ({failed} failed), "
                      f"{len(killers)} killer keys", flush=True)
            time.sleep(a.sleep)
    write_killers(killers)
    cov = len(done_matches() & {t[0] for t in targets}) / len(targets)
    print(f"extras coverage {cov:.3f}; {failed} failed this run", flush=True)
    return 0 if cov >= 0.90 else 1


def write_killers(killers):
    """Every distinct killer key seen, so nothing about the field is inferred from its name."""
    non_hero = {k: v for k, v in killers.items() if not is_hero(k)}
    doc = {"distinct_keys": len(killers),
           "hero_keys": len(killers) - len(non_hero),
           "non_hero_keys": len(non_hero),
           "tormentor_keys": sorted(k for k in killers if is_tormentor(k)),
           "non_hero_key_counts": dict(sorted(non_hero.items(), key=lambda kv: -kv[1])),
           "keys": dict(killers)}
    with open(OUT_KILLERS, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
