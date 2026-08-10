"""Read the OFFICIAL Valve league data feed (league_id 19719) into the posted draw.

The feed is the machine-readable source behind the game client (contest_rules.LEAGUE_FEED_URL). It
carries the Swiss node group (max_rounds, win_loss_limit, advancing teams) and, once the draw is
published, the round-1 nodes with both team ids and their scheduled start times.

Two things this module deliberately does NOT do:
  - it never invents a pod partition. The feed exposes ONE undivided 16-team Swiss node group; if no
    pod split is present the parsed draw is marked pods_status="unresolved" and the consumer decides
    how to handle it (the official pipeline fails closed).
  - it never maps a team by name similarity. Feed team ids are resolved through
    inputs/canonical_identity.csv source_team_ids, which is the tracked id->organization table.

Run:  python -m ti_predict.league_feed            (parse the saved snapshot, print the draw)
      python -m ti_predict.league_feed --fetch    (re-download the feed first, then parse)
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.contest_rules import LEAGUE_FEED_URL

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
RAW, INPUTS = os.path.join(TI, "raw"), os.path.join(TI, "inputs")
FEED_JSON = os.path.join(RAW, "league_19719_feed.json")
UA = {"User-Agent": "dota2-ti-predict/0.1 (league-feed)"}


def fetch(url=LEAGUE_FEED_URL, path=FEED_JSON):
    """Download the feed and store it verbatim. Returns (path, sha256, retrieved_at)."""
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    json.loads(raw)                                   # fail before overwriting a good snapshot
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)
    return path, hashlib.sha256(raw).hexdigest(), datetime.now(timezone.utc).isoformat(
        timespec="seconds")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def id_to_org(canon_csv=None):
    """{source_team_id: organization} from the tracked canonical identity table."""
    canon_csv = canon_csv or os.path.join(INPUTS, "canonical_identity.csv")
    with open(canon_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        for sid in (r["source_team_ids"] or "").split("|"):
            if sid.strip():
                out[int(sid)] = r["organization"]
    return out


def _groups(feed):
    """Depth-first walk of the node_group tree."""
    stack, out = list(feed.get("node_groups") or []), []
    while stack:
        g = stack.pop()
        out.append(g)
        stack.extend(g.get("node_groups") or [])
    return out


def parse_draw(feed=None, canon_csv=None):
    """Parse the feed into the posted draw.

    Returns a dict with r1_pairings (organization names), r1_status, pods_status, the Swiss format
    parameters the feed asserts, and the round-1 scheduled times. Raises SystemExit on any id that
    cannot be resolved to a tracked organization -- a silent drop would corrupt the draw.
    """
    if feed is None:
        if not os.path.exists(FEED_JSON):
            raise SystemExit(f"league feed snapshot not found: {FEED_JSON}\n"
                             "run: python -m ti_predict.league_feed --fetch")
        with open(FEED_JSON, encoding="utf-8") as fh:
            feed = json.load(fh)
    swiss = [g for g in _groups(feed) if g.get("max_rounds") and g.get("win_loss_limit")]
    if len(swiss) != 1:
        raise SystemExit(f"expected exactly one Swiss node group in the feed, found {len(swiss)}")
    sw = swiss[0]
    fmt = {"team_count": sw.get("team_count"), "max_rounds": sw.get("max_rounds"),
           "win_loss_limit": sw.get("win_loss_limit"), "advancing": sw.get("advancing_team_count")}

    id2org = id_to_org(canon_csv)
    pairs, sched, unresolved = [], [], []
    for n in sorted(sw.get("nodes") or [], key=lambda n: n.get("node_id", 0)):
        a, b = n.get("team_id_1"), n.get("team_id_2")
        if not a or not b:
            continue
        for tid in (a, b):
            if tid not in id2org:
                unresolved.append(tid)
        pairs.append((id2org.get(a, f"team_id:{a}"), id2org.get(b, f"team_id:{b}")))
        sched.append({"node": n.get("name") or str(n.get("node_id")),
                      "scheduled_time": n.get("scheduled_time"),
                      "scheduled_utc": (datetime.fromtimestamp(n["scheduled_time"], timezone.utc)
                                        .isoformat() if n.get("scheduled_time") else None)})
    if unresolved:
        raise SystemExit("league feed team ids not in canonical_identity.csv source_team_ids: "
                         + ", ".join(str(t) for t in sorted(set(unresolved))))

    flat = [t for p in pairs for t in p]
    r1_status = "official" if len(pairs) == 8 and len(set(flat)) == 16 else "incomplete"
    # The feed has no pod field. A pod split, if one exists, is not machine-readable anywhere.
    pods_status = "unresolved"
    return {"league_id": 19719, "source": LEAGUE_FEED_URL, "feed_sha256": _sha256(FEED_JSON)
            if os.path.exists(FEED_JSON) else None,
            "swiss_format": fmt, "r1_status": r1_status, "r1_pairings": [list(p) for p in pairs],
            "r1_schedule": sched, "pods_status": pods_status,
            "pods_evidence": "Valve league feed exposes a single undivided 16-team Swiss node group; "
                             "no pod partition is published in any machine-readable source",
            "first_match_utc": min((s["scheduled_utc"] for s in sched if s["scheduled_utc"]),
                                   default=None)}


def write_draw(d, path=None, retrieved_at=None):
    """Write the parsed draw to inputs/draw.json (the file the pipeline consumes)."""
    path = path or os.path.join(INPUTS, "draw.json")
    out = dict(d)
    out.pop("r1_schedule", None)
    out["retrieved_at"] = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out["_comment"] = ("Generated from the official Valve league feed by "
                       "`python -m ti_predict.league_feed --write-draw`. Team names are canonical "
                       "organizations (teams.csv 'team'). pods_status='unresolved' means no pod "
                       "partition is published; the official pipeline fails closed on it.")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def main():
    ap = argparse.ArgumentParser(description="parse the official league feed into the posted draw")
    ap.add_argument("--fetch", action="store_true", help="re-download the feed before parsing")
    ap.add_argument("--write-draw", action="store_true",
                    help="write inputs/draw.json from the parsed feed")
    a = ap.parse_args()
    at = None
    if a.fetch:
        path, sha, at = fetch()
        print(f"fetched {os.path.relpath(path, REPO)} sha256={sha[:16]} at {at}")
    d = parse_draw()
    if a.write_draw:
        print("wrote " + os.path.relpath(write_draw(d, retrieved_at=at), REPO))
    print(f"swiss format: {d['swiss_format']}")
    print(f"r1_status={d['r1_status']}  pods_status={d['pods_status']}")
    print(f"first scheduled match (UTC): {d['first_match_utc']}")
    for (a_, b_), s in zip(d["r1_pairings"], d["r1_schedule"]):
        print(f"  {s['node']:<10} {a_:<18} vs {b_:<18} {s['scheduled_utc']}")


if __name__ == "__main__":
    main()
