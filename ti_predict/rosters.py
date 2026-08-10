"""Lock-period roster audit: the tracked reconciliation of the 16 TI rosters.

`inputs/roster_events.csv` is the audit table -- one row per organization, carrying the status of
its lineup for the event and, when it changed, the structured provenance of the change (who left,
who joined, the role, why, the announcement time, the evidence tier and the source).

Why this is a separate table and not a column in canonical_identity.csv: that file is DERIVED from
match data (the five players actually observed on a team's side). A player who joins days before the
event has no match with the team yet, so no amount of re-deriving finds him. The roster event is
external evidence and is recorded as such -- it never silently rewrites the observed identity.

Statuses:
  CONFIRMED  -- lineup matches the announced/observed five; nothing to carry.
  CHANGED    -- an evidenced roster change (outgoing/incoming/role/reason are required).
  CONFLICT   -- sources disagree and the disagreement is unresolved.
  UNRESOLVED -- the lineup could not be established from any source.
CONFLICT and UNRESOLVED are blocking for an official run: neither may be silently resolved in favour
of whichever version happens to be in the model.
"""
import csv
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
ROSTER_EVENTS_CSV = os.path.join(INPUTS, "roster_events.csv")
STATUSES = ("CONFIRMED", "CHANGED", "CONFLICT", "UNRESOLVED")
BLOCKING = ("CONFLICT", "UNRESOLVED")
CHANGE_REQUIRED = ("role", "outgoing_player", "outgoing_account_id",
                   "incoming_player", "incoming_account_id", "reason_category", "announced_utc",
                   "evidence_tier", "source")


def _relpath(p):
    """Repo-relative path for display, tolerant of a table on a different drive/mount."""
    try:
        return os.path.relpath(p, REPO).replace("\\", "/")
    except ValueError:
        return p


def load_roster_events(path=None, orgs=None):
    """Read and validate the audit table. Returns {organization: row}.

    Validates: known statuses; every CHANGED row carries full provenance; exactly one row per
    organization; and, when `orgs` is given, that the table covers precisely those organizations.
    """
    path = path or ROSTER_EVENTS_CSV
    if not os.path.exists(path):
        raise SystemExit(f"roster audit table not found: {path}")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        org = (r.get("organization") or "").strip()
        if not org:
            raise SystemExit("roster_events.csv: a row has no organization")
        if org in out:
            raise SystemExit(f"roster_events.csv: duplicate row for {org}")
        status = (r.get("status") or "").strip().upper()
        if status not in STATUSES:
            raise SystemExit(f"roster_events.csv: {org} has status {status!r}; "
                             f"expected one of {', '.join(STATUSES)}")
        r["status"] = status
        if status == "CHANGED":
            missing = [f for f in CHANGE_REQUIRED if not (r.get(f) or "").strip()]
            if missing:
                raise SystemExit(f"roster_events.csv: {org} is CHANGED but missing "
                                 + ", ".join(missing))
            for f in ("outgoing_account_id", "incoming_account_id"):
                if not r[f].strip().isdigit():
                    raise SystemExit(f"roster_events.csv: {org} {f} must be a numeric account id, "
                                     f"found {r[f]!r} (never infer an id from a nickname)")
        out[org] = r
    if orgs is not None:
        want, have = set(orgs), set(out)
        if want != have:
            raise SystemExit("roster_events.csv must cover exactly the 16 teams; "
                             f"missing {sorted(want - have)}, unexpected {sorted(have - want)}")
    return out


def roster_audit(path=None, orgs=None):
    """Manifest-ready summary of the audit table (no personal data beyond nickname/account id)."""
    path = path or ROSTER_EVENTS_CSV
    ev = load_roster_events(path, orgs)
    changed = [{"organization": o, "role": r["role"],
                "outgoing": {"player": r["outgoing_player"], "account_id": r["outgoing_account_id"]},
                "incoming": {"player": r["incoming_player"], "account_id": r["incoming_account_id"]},
                "reason_category": r["reason_category"], "eligibility": r["eligibility"],
                "announced_utc": r["announced_utc"], "effective_status": r["effective_status"],
                "evidence_tier": r["evidence_tier"], "source": r["source"]}
               for o, r in sorted(ev.items()) if r["status"] == "CHANGED"]
    blocking = sorted(o for o, r in ev.items() if r["status"] in BLOCKING)
    return {"teams_audited": len(ev), "audit_source": _relpath(path),
            "confirmed": sum(1 for r in ev.values() if r["status"] == "CONFIRMED"),
            "changed": changed, "blocking": blocking,
            "retrieved_at": sorted({r.get("retrieved_at", "") for r in ev.values()})[-1]}


if __name__ == "__main__":
    a = roster_audit()
    print(f"audited {a['teams_audited']} teams as of {a['retrieved_at']}: "
          f"{a['confirmed']} confirmed, {len(a['changed'])} changed, "
          f"{len(a['blocking'])} blocking")
    for c in a["changed"]:
        print(f"  {c['organization']}: role {c['role']} {c['outgoing']['player']} "
              f"({c['outgoing']['account_id']}) -> {c['incoming']['player']} "
              f"({c['incoming']['account_id']}) [{c['reason_category']}, tier {c['evidence_tier']}]")
    if a["blocking"]:
        print("  BLOCKING: " + ", ".join(a["blocking"]))
