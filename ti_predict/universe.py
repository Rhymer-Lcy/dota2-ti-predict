"""Build the rating universe + the frozen event-fold table (pre-fit data layer).

Rating universe: EVERY professional map in the as-of window (the proMatches scan), not just maps
involving the 16 TI rosters -- opponents need their other games or their strength is unidentified.
Identities: our 16 rosters -> organization (their source_team_ids collapsed); every other pro team
-> "t{team_id}" (that org's roster changes are ignored; they exist only to calibrate opponents).

Evaluation stays restricted to the preregistered target rows (dataset_maps.csv, current-roster
maps, overlap>=4). This script only prepares data + folds; no model is fit here.

Fold table: one fold per leagueid, but training eligibility is by TIME, not league membership:
`train = universe maps with start_time < fold.cutoff` (cutoff = the fold event's first map), which is
robust to temporally overlapping events. Frozen to inputs/folds.csv.

Writes processed/universe_maps.csv (gitignored) + inputs/folds.csv (tracked). Prints sizes.
Run: python -m ti_predict.universe
"""
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
PROC, INPUTS, RAW = (os.path.join(TI, d) for d in ("processed", "inputs", "raw"))


def _d(ts):
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def main():
    scan = json.load(open(os.path.join(RAW, "promatches_scan.json"), encoding="utf-8"))
    canon = list(csv.DictReader(open(os.path.join(INPUTS, "canonical_identity.csv"), encoding="utf-8")))
    id2org = {int(sid): r["organization"] for r in canon
              for sid in (r["source_team_ids"] or "").split("|") if sid}
    target = {int(r["match_id"]): r for r in csv.DictReader(
        open(os.path.join(PROC, "dataset_maps.csv"), encoding="utf-8"))}

    def ident(tid):
        return id2org.get(int(tid), f"t{tid}")

    # universe: every scan map with both team ids + a winner + a time
    uni = {}
    for m in scan:
        mid = m["match_id"]
        rt, dt_, st = m.get("radiant_team_id"), m.get("dire_team_id"), m.get("start_time")
        if not rt or not dt_ or st is None or m.get("radiant_win") is None:
            continue
        uni[mid] = {"match_id": mid, "start_time": st, "date": _d(st),
                    "leagueid": m.get("leagueid"), "league_name": m.get("league_name", ""),
                    "series_id": m.get("series_id") or 0,
                    "team_a": ident(rt), "team_b": ident(dt_),
                    "a_won": int(bool(m["radiant_win"])),
                    "is_target": int(mid in target)}
    rows = sorted(uni.values(), key=lambda r: (r["start_time"], r["match_id"]))
    os.makedirs(PROC, exist_ok=True)
    with open(os.path.join(PROC, "universe_maps.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    # folds: one per leagueid that contains target maps; cutoff = first target map of that league
    fold_targets = defaultdict(list)
    for r in rows:
        if r["is_target"]:
            fold_targets[r["leagueid"]].append(r)
    folds = []
    for lg, ts in fold_targets.items():
        cutoff = min(t["start_time"] for t in ts)
        n_train = sum(1 for r in rows if r["start_time"] < cutoff)
        name = ts[0]["league_name"]
        folds.append({"leagueid": lg, "league_name": name,
                      "start": _d(min(t["start_time"] for t in ts)),
                      "end": _d(max(t["start_time"] for t in ts)),
                      "cutoff_ts": cutoff, "cutoff": _d(cutoff),
                      "n_target": len(ts), "n_train_universe": n_train})
    folds.sort(key=lambda f: f["cutoff_ts"])
    with open(os.path.join(INPUTS, "folds.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(folds[0])); w.writeheader(); w.writerows(folds)

    print(f"rating universe: {len(rows)} pro maps ({_d(rows[0]['start_time'])}..{_d(rows[-1]['start_time'])})")
    print(f"evaluation target: {sum(r['is_target'] for r in rows)} maps (must be 1177)")
    print(f"folds (events with target maps): {len(folds)}\n")
    print(f"{'cutoff':<11}{'lg':>7} {'n_tgt':>6} {'n_train':>8}  league")
    for f in folds:
        print(f"{f['cutoff']:<11}{str(f['leagueid']):>7} {f['n_target']:>6} {f['n_train_universe']:>8}  {f['league_name'][:40]}")


if __name__ == "__main__":
    main()
