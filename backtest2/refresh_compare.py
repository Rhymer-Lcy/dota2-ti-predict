"""Refresh impact study: 2026-08-01 snapshot vs refreshed universe (research; not a prediction).

Quantifies what the data refresh (matches after 2026-08-01, e.g. 1W Essence Season 2 and the Astana
event) changes: per-team B-bt strengths, the largest pairwise-probability shifts, and the
uniform-marginal provisional slate. Uses the frozen production configuration (B-bt half-life 90,
side-neutral c) for BOTH snapshots; only the data and the as-of cutoff differ. This is the data
refresh the lock-day runbook mandates, evaluated early as a rehearsal; the official prediction still
comes only from the post-draw official path at the confirmed cutoff.

Run: python -m backtest2.refresh_compare --new-cutoff 2026-08-10T00:00:00Z
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest2.pre_draw import marginal_P
from backtest2.refine_audit import snapshot_strengths
from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS
from ti_predict.predict_ti15 import bt_strengths_for, load_teams, parse_cutoff
from ti_predict.swiss import map_pn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARGINAL_SIMS = 12000
SEED = 20260810


def main():
    ap = argparse.ArgumentParser(description="Snapshot-vs-refresh strength comparison (research)")
    ap.add_argument("--new-cutoff", default="2026-08-10T00:00:00Z")
    a = ap.parse_args()

    teams = load_teams()
    names = [t["team"] for t in teams]
    region = {t["team"]: t["region"] for t in teams}

    s_old, c_old, _ = snapshot_strengths()
    cut_ts, cut_iso = parse_cutoff(a.new_cutoff)
    s_new, c_new, n_train, uni_rows, uni_max = bt_strengths_for(teams, cut_ts)

    shifts = sorted(((t, round(s_new[t] - s_old[t], 3)) for t in names),
                    key=lambda kv: -abs(kv[1]))
    rank_old = {t: i for i, t in enumerate(sorted(names, key=lambda t: -s_old[t]))}
    rank_new = {t: i for i, t in enumerate(sorted(names, key=lambda t: -s_new[t]))}

    P_old = marginal_P(names, "uniform", s_old, region, MARGINAL_SIMS, SEED, c_old)
    P_new = marginal_P(names, "uniform", s_new, region, MARGINAL_SIMS, SEED, c_new)
    _, expc_old, rows_old = assign(P_old)
    _, expc_new, rows_new = assign(P_new)
    asg_old = {t: b for t, b, _ in rows_old}
    asg_new = {t: b for t, b, _ in rows_new}
    changed = sorted(t for t in names if asg_old[t] != asg_new[t])

    biggest_pair_shift = max(((x, y, abs(map_pn(s_new[x], s_new[y], c_new)
                                         - map_pn(s_old[x], s_old[y], c_old)))
                              for i, x in enumerate(names) for y in names[i + 1:]),
                             key=lambda r: r[2])

    out = {"status": "REFRESH RESEARCH - not an official prediction",
           "old_snapshot": "2026-08-01 (cutoff 2026-08-02T00:00:00Z)",
           "new_cutoff": cut_iso, "new_train_maps": n_train,
           "new_universe": {"rows": uni_rows, "latest_map_utc": uni_max},
           "radiant_c": {"old": round(c_old, 4), "new": round(c_new, 4)},
           "strength_shifts_desc": shifts,
           "rank_changes": {t: f"{rank_old[t] + 1}->{rank_new[t] + 1}" for t in names
                            if rank_old[t] != rank_new[t]},
           "largest_pairwise_prob_shift": {"pair": biggest_pair_shift[:2],
                                           "abs_dP": round(biggest_pair_shift[2], 4)},
           "uniform_marginal_slate_old": {b: sorted(t for t in names if asg_old[t] == b)
                                          for b in BUCKETS},
           "uniform_marginal_slate_new": {b: sorted(t for t in names if asg_new[t] == b)
                                          for b in BUCKETS},
           "slate_changes": changed,
           "expected_correct": {"old": round(expc_old, 3), "new": round(expc_new, 3)}}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "refresh_compare.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[{out['status']}] new cutoff {cut_iso}, {n_train} train maps")
    print("top strength shifts:", shifts[:8])
    print("rank changes:", out["rank_changes"])
    print("slate changes old->new:", changed or "none")
    for b in BUCKETS:
        print(f"  {b:>13}: {', '.join(out['uniform_marginal_slate_new'][b])}")
    print("wrote backtest2/reports/refresh_compare.json")


if __name__ == "__main__":
    main()
