"""Rebuild canonical_identity.csv in the multi-id schema (no single active_team_id).

Reads the roster-centric outputs and emits two tracked tables:
  inputs/canonical_identity.csv  — one row per organization: current roster + the FULL set of
      source_team_ids that roster used, primary (most-recently-active) id, coverage, and a
      confirmed-at-cutoff flag kept separate from continuity.
  inputs/canonical_sources.csv   — one row per (organization, source_team_id): observed window and
      map count under that id (this is the org -> many source_team_id mapping, time-versioned).

"Observed" windows come from match data (first/last seen). Evidenced valid_from/valid_to (roster
announcements) are left for manual fill — flagged, not fabricated. Run AFTER roster_coverage.py.

Run:  python -m ti_predict.build_canonical
"""
import csv
import os
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
INPUTS, PROC = os.path.join(TI, "inputs"), os.path.join(TI, "processed")


# Known organization renames/transfers where the SAME roster continued (roster continuity kept,
# org entity segmented). Confirm via public schedule before relying.
ORG_TRANSITIONS = {
    "Tundra Esports": "roster moved to 1w Team ~2026-06 (org renamed; TI entity = 1w Team)",
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    matches = _read(os.path.join(PROC, "roster_matches.csv"))
    v1 = {r["organization"]: r for r in _read(os.path.join(INPUTS, "canonical_identity.csv"))}
    teams = {r["team"]: r for r in _read(os.path.join(INPUTS, "teams.csv"))}

    by_org = defaultdict(list)
    for m in matches:
        by_org[m["organization"]].append(m)

    id_rows, src_rows = [], []
    for org, ms in by_org.items():
        ge4 = [m for m in ms if int(m["overlap"]) >= 4]
        full = [m for m in ms if int(m["overlap"]) == 5]
        # per source_team_id observation window (from >=4/5 maps)
        per_src = defaultdict(list)
        for m in ge4:
            if m.get("source_team_id"):
                per_src[m["source_team_id"]].append(m["date"])
        src_windows = {}
        for sid, dates in per_src.items():
            src_windows[sid] = (min(dates), max(dates), len(dates))
            src_rows.append({"organization": org, "source_team_id": sid,
                             "maps_ge4of5": len(dates), "first_observed": min(dates),
                             "last_observed": max(dates),
                             "valid_from_evidenced": "", "valid_to_evidenced": "",
                             "basis": "observed_matches"})
        primary = max(src_windows, key=lambda s: src_windows[s][1]) if src_windows else ""
        roster_key = Counter(m["roster_key"] for m in full).most_common(1)
        roster_key = roster_key[0][0] if roster_key else (v1.get(org, {}).get("roster_key", ""))
        v1r, tm = v1.get(org, {}), teams.get(org, {})
        id_rows.append({
            "organization": org, "ti_alias": tm.get("ti_alias", ""),
            "qualification": tm.get("qualification", ""), "region": tm.get("region", ""),
            "roster_key": roster_key, "player_ids": v1r.get("player_ids", ""),
            "player_names": v1r.get("player_names", ""),
            "source_team_ids": "|".join(sorted(per_src, key=lambda s: src_windows[s][1], reverse=True)),
            "primary_source_id": primary,
            "maps_5of5": len(full), "maps_ge4of5": len(ge4),
            "roster_confirmed_at_cutoff": "True",
            "confirmation_basis": "recent_pro_matches",
            "continuity_note": f"{len(full)} full-5 maps {min((m['date'] for m in full), default='-')}..{max((m['date'] for m in full), default='-')}",
            "note": "; ".join(x for x in [
                ORG_TRANSITIONS.get(org, ""),
                ("multi-id: " + "|".join(per_src)) if len(per_src) > 1 else ""] if x),
        })

    id_rows.sort(key=lambda r: r["organization"])
    src_rows.sort(key=lambda r: (r["organization"], r["last_observed"]))
    with open(os.path.join(INPUTS, "canonical_identity.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(id_rows[0])); w.writeheader(); w.writerows(id_rows)
    with open(os.path.join(INPUTS, "canonical_sources.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(src_rows[0])); w.writeheader(); w.writerows(src_rows)
    print(f"wrote canonical_identity.csv ({len(id_rows)} orgs) + canonical_sources.csv "
          f"({len(src_rows)} org-id rows)")
    for r in id_rows:
        print(f"  {r['organization']:<17} ids [{r['source_team_ids']}] primary {r['primary_source_id']} "
              f"| 5/5 {r['maps_5of5']}")


if __name__ == "__main__":
    main()
