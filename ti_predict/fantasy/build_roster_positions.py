"""Build the authoritative TI2026 position table: one row per player, position 1-5.

Why this exists. The fantasy roles are defined on POSITIONS -- Core is 1 and 3, Mid is 2, Support
is 4 and 5 -- and positions are a fact about the roster, not something to be recovered from match
statistics. An earlier version of the baseline ranked players by median last hits and guessed the
midlaner from rune pickups. That is a reasonable exploratory heuristic and an unacceptable input to
a production ranking: it silently re-decides the roster every time the data changes.

Inputs, and what each is trusted for:
  canonical_identity.csv  -- the five ACCOUNT IDS per organisation, derived from match data. This
                             file is the identity authority and is never overridden here.
  Liquipedia participants -- the POSITION of each player. Tier 2, used only for roster and identity
                             reconciliation, which is what this project's source policy allows it
                             for. It is not used for any statistic.
  roster_events.csv       -- the lock-period roster audit. A CHANGED row replaces the outgoing
                             player at his position and marks him inactive.

The join between the two name spaces is a per-team bijection, not a fuzzy match: if the five
Liquipedia names do not map one-to-one onto the five canonical names for a team, the build fails
rather than guessing. Nicknames that differ only by decoration are listed explicitly in ALIASES so
that every substitution is visible in the diff instead of buried in a similarity score.
"""
import argparse
import csv
import io
import json
import os
import re
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
CANONICAL = os.path.join(INPUTS, "canonical_identity.csv")
OUT_CSV = os.path.join(INPUTS, "fantasy", "roster_positions.csv")

FANTASY_ROLE = {1: "core", 2: "mid", 3: "core", 4: "support", 5: "support"}
FIELDS = ("organization", "account_id", "player", "position", "fantasy_role", "active",
          "evidence", "evidence_tier", "retrieved_at", "note")

# Liquipedia's page title for a team, where it differs from this project's organisation name.
# Both are recorded because the TI brand and the roster's home organisation are not always the same.
TEAM_ALIASES = {
    "Iron Wing TI 2026": "Tundra Esports",   # Tundra's roster, competing under the Iron Wing brand
    "TEAM VISION": "PARIVISION",             # PARIVISION's TI brand
}

# Nickname spellings that differ between Liquipedia and this project's match-derived identity table.
# Every entry is a decoration or abbreviation difference, never a judgement about who someone is.
ALIASES = {
    "Ws": "Ws`", "Kataomi": "Kataomi`", "ATF": "AMMAR_THE_F", "Ace": "Ace ♠",
    "watson": "医者watson`", "Malady": "Maladych", "SumaiL": "SumaiL-",
    "Mirage`": "Mirage`雨", "not me": "not_me", "KJ": "KingJungles",
}


def load_canonical(path=None):
    """organisation -> {player name: account_id}, from the tracked identity table."""
    path = path or CANONICAL
    out = {}
    with io.open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ids = [i for i in row["player_ids"].split("|") if i]
            names = row["player_names"].split("|")
            if len(ids) != len(names):
                raise SystemExit(f"canonical_identity.csv: {row['organization']} has "
                                 f"{len(ids)} ids and {len(names)} names")
            out[row["organization"]] = dict(zip(names, (int(i) for i in ids)))
    return out


def parse_participants(wikitext):
    """Liquipedia participants block -> {team title: {position: nickname}}."""
    start = wikitext.find("{{TeamParticipants")
    if start < 0:
        raise SystemExit("no TeamParticipants block in the supplied wikitext")
    end = wikitext.find("\n==", start)
    block = wikitext[start:end if end > 0 else len(wikitext)]
    out = {}
    for chunk in re.split(r"\{\{Opponent\|", block)[1:]:
        team = chunk.split("\n", 1)[0].strip().rstrip("|").strip()
        people = re.findall(r"\{\{Person\|role=(\d)\|([^|}\n]+)", chunk)
        if people:
            out[team] = {int(r): p.strip() for r, p in people}
    return out


def load_roster_events():
    from ti_predict import rosters
    return {c["organization"]: c for c in rosters.roster_audit()["changed"]}


def build(wikitext, retrieved_at, evidence):
    canon = load_canonical()
    parsed = parse_participants(wikitext)
    changed = load_roster_events()
    rows, seen_ids = [], {}
    for team, by_pos in parsed.items():
        org = TEAM_ALIASES.get(team, team)
        if org not in canon:
            raise SystemExit(f"Liquipedia team {team!r} maps to {org!r}, which is not one of the "
                             f"16 organisations in canonical_identity.csv")
        if sorted(by_pos) != [1, 2, 3, 4, 5]:
            raise SystemExit(f"{org}: Liquipedia gives positions {sorted(by_pos)}, expected 1..5")
        want = dict(canon[org])
        change = changed.get(org)
        for pos in range(1, 6):
            nick = by_pos[pos]
            name = ALIASES.get(nick, nick)
            if name not in want:
                raise SystemExit(
                    f"{org} position {pos}: Liquipedia nickname {nick!r} does not match any of the "
                    f"canonical names {sorted(want)}. Add an explicit entry to ALIASES; this build "
                    "never matches names by similarity.")
            acct = want.pop(name)
            active, note = True, ""
            if change and int(change["outgoing"]["account_id"]) == acct:
                # the departed player keeps his row, marked inactive, so the exclusion is auditable
                rows.append({"organization": org, "account_id": acct, "player": name,
                             "position": pos, "fantasy_role": FANTASY_ROLE[pos], "active": False,
                             "evidence": change["source"], "evidence_tier": change["evidence_tier"],
                             "retrieved_at": change["announced_utc"],
                             "note": f"replaced at position {pos} ({change['reason_category']})"})
                acct = int(change["incoming"]["account_id"])
                name = change["incoming"]["player"]
                note = f"roster change: replaces {change['outgoing']['player']}"
            rows.append({"organization": org, "account_id": acct, "player": name, "position": pos,
                         "fantasy_role": FANTASY_ROLE[pos], "active": active,
                         "evidence": evidence, "evidence_tier": 2,
                         "retrieved_at": retrieved_at, "note": note})
            if active:
                if acct in seen_ids:
                    raise SystemExit(f"account_id {acct} appears for both {seen_ids[acct]} "
                                     f"and {org}")
                seen_ids[acct] = org
        if want:
            raise SystemExit(f"{org}: canonical players {sorted(want)} were never assigned a "
                             "position; the two rosters do not agree")
    if len(parsed) != 16:
        raise SystemExit(f"expected 16 teams, parsed {len(parsed)}")
    return rows


def load_positions(path=None):
    """Read and validate the position table. Returns {organization: {fantasy_role: [account_id]}}.

    Fails closed on every invariant the fantasy rules depend on: sixteen organisations, five active
    players each, positions 1..5 exactly once, the Core/Mid/Support split implied by those
    positions, and globally unique account ids among active players. An inactive row is kept in the
    file for audit but never reaches a roster.
    """
    path = path or OUT_CSV
    if not os.path.exists(path):
        raise SystemExit(f"position table not found: {path}; run "
                         "python -m ti_predict.fantasy.build_roster_positions")
    with io.open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_org, seen = {}, {}
    for r in rows:
        if r["active"].strip().lower() != "true":
            continue
        org, pos = r["organization"], int(r["position"])
        acct = int(r["account_id"])
        if FANTASY_ROLE[pos] != r["fantasy_role"]:
            raise SystemExit(f"{org} position {pos} is labelled {r['fantasy_role']!r}; "
                             f"position {pos} is {FANTASY_ROLE[pos]}")
        slot = by_org.setdefault(org, {})
        if pos in slot:
            raise SystemExit(f"{org} has more than one active player at position {pos}")
        slot[pos] = (acct, r["player"])
        if acct in seen:
            raise SystemExit(f"account_id {acct} is active for both {seen[acct]} and {org}")
        seen[acct] = org
    if len(by_org) != 16:
        raise SystemExit(f"expected 16 organisations, found {len(by_org)}")
    out = {}
    for org, slot in by_org.items():
        if sorted(slot) != [1, 2, 3, 4, 5]:
            raise SystemExit(f"{org} has active positions {sorted(slot)}, expected 1..5")
        roles = {"core": [], "mid": [], "support": []}
        for pos, (acct, _name) in sorted(slot.items()):
            roles[FANTASY_ROLE[pos]].append(acct)
        if [len(roles[r]) for r in ("core", "mid", "support")] != [2, 1, 2]:
            raise SystemExit(f"{org} does not split into 2 core / 1 mid / 2 support")
        out[org] = roles
    return out


def inactive_accounts(path=None):
    """Account ids explicitly marked inactive: they may never enter a fantasy roster."""
    path = path or OUT_CSV
    if not os.path.exists(path):
        return set()
    with io.open(path, encoding="utf-8") as fh:
        return {int(r["account_id"]) for r in csv.DictReader(fh)
                if r["active"].strip().lower() != "true"}


def player_names(path=None):
    path = path or OUT_CSV
    with io.open(path, encoding="utf-8") as fh:
        return {int(r["account_id"]): r["player"] for r in csv.DictReader(fh)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--wikitext", required=True,
                   help="file holding the Liquipedia TI2026 page wikitext")
    a.add_argument("--evidence",
                   default="https://liquipedia.net/dota2/The_International/2026 (Participants)")
    a.add_argument("--out", default=OUT_CSV)
    a = a.parse_args(argv)
    with io.open(a.wikitext, encoding="utf-8") as fh:
        wikitext = fh.read()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = build(wikitext, stamp, a.evidence)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["organization"], r["position"], not r["active"])):
            w.writerow(r)
    active = sum(1 for r in rows if r["active"])
    print(json.dumps({"rows": len(rows), "active": active,
                      "inactive": len(rows) - active,
                      "organizations": len({r["organization"] for r in rows}),
                      "out": os.path.relpath(a.out, REPO).replace("\\", "/")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
