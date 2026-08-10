"""Phase-3 policy comparison: expected-correct vs expected-official-points vs robust.

Model-conditional STRATEGY SIMULATION under the frozen B-bt strengths + the Swiss simulator. It uses
NO actual results and NO crowd pick-share, so it does NOT validate that the model predicts (that is
Phase 1/2). It answers one decision-theory question: because the group scoring f(K) is convex, does
the expected-correct-maximizing slate (policy A) leave official points on the table vs a slate that
directly maximizes E[f(K)] (policy B), and how robust is each across the C5/D4/seed assumptions
(policy C)? Dry-run only; every artifact is labeled accordingly.

Method: draw one shared archive of full simulated tournaments, build P and the policy-A assignment
from it, then evaluate any slate's E[f(K)] against the SAME archive (common random numbers). Local
search (pairwise bucket swaps) from A gives B. Re-drawing the archive under each D4 scenario gives the
robustness (C) view. Because swaps change K by a per-sim delta, E[f(K)] re-evaluation is O(sims).

Run: python -m backtest2.compare_policies --strengths bt --cutoff 2026-08-01 --sims 20000
"""
import argparse
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.predict_ti15 import (bt_strengths_for, load_teams, parse_cutoff, resolve_draw,
                                     synthetic_strengths)
from ti_predict.contest_rules import GROUP_SCORE
from ti_predict.swiss import BUCKETS, simulate_one

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIDX = {b: i for i, b in enumerate(BUCKETS)}
FVEC = np.array([GROUP_SCORE[k] for k in range(17)])


def archive(pods, strength, n, seed, elim_choice, r1=None, c=0.0):
    """Run n sims; return (teams, rb) where rb[t] is an int array of team t's realized bucket/sim."""
    rng = random.Random(seed)
    teams = list(pods[0]) + list(pods[1])
    real = {t: np.empty(n, dtype=np.int8) for t in teams}
    for k in range(n):
        bucket = simulate_one(pods, strength, rng, r1, elim_choice, c=c)
        for t, b in bucket.items():
            real[t][k] = BIDX[b]
    return teams, real


def P_from(teams, rb, n):
    return {t: {b: float(np.mean(rb[t] == BIDX[b])) for b in BUCKETS} for t in teams}


def asg_from_slate(slate):
    return {t: b for b in BUCKETS for t, _ in slate[b]}


def kcur(asg, rb, n):
    K = np.zeros(n, dtype=np.int16)
    for t, b in asg.items():
        K += (rb[t] == BIDX[b])
    return K


def ef(K):
    return float(FVEC[K].mean())


def local_search(asg, rb, n, max_pass=6):
    """Pairwise bucket-swap hill climb on E[f(K)]; capacity-preserving (swap keeps counts)."""
    asg = dict(asg)
    K = kcur(asg, rb, n)
    best = ef(K)
    teams = list(asg)
    for _ in range(max_pass):
        improved = False
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                t1, t2 = teams[i], teams[j]
                b1, b2 = asg[t1], asg[t2]
                if b1 == b2:
                    continue
                i1, i2 = BIDX[b1], BIDX[b2]
                delta = ((rb[t1] == i2).astype(np.int16) + (rb[t2] == i1)
                         - (rb[t1] == i1) - (rb[t2] == i2))
                cand = ef(K + delta)
                if cand > best + 1e-9:
                    asg[t1], asg[t2] = b2, b1
                    K = K + delta
                    best = cand
                    improved = True
        if not improved:
            break
    return asg, best


def slate_str(asg):
    inv = {b: [] for b in BUCKETS}
    for t, b in asg.items():
        inv[b].append(t)
    return " | ".join(f"{b}:{','.join(sorted(inv[b]))}" for b in BUCKETS)


def main():
    ap = argparse.ArgumentParser(description="Phase-3 policy comparison (model-conditional dry-run)")
    ap.add_argument("--strengths", choices=("synthetic", "bt"), default="synthetic")
    ap.add_argument("--cutoff", help="YYYY-MM-DD or full ISO timestamp (required for bt)")
    ap.add_argument("--draw", help="path to draw.json (real pods + round-1 pairings)")
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20260813)
    a = ap.parse_args()

    teams_rows = load_teams()
    c = 0.0
    if a.strengths == "bt":
        if not a.cutoff:
            sys.exit("--strengths bt requires --cutoff")
        cut_ts, cut_iso = parse_cutoff(a.cutoff)
        strength, c, _, _, _ = bt_strengths_for(teams_rows, cut_ts)
        ssrc = f"B-bt @ {cut_iso} (c={c:+.3f})"
    else:
        strength, ssrc = synthetic_strengths(teams_rows), "synthetic (non-predictive)"
    pods, r1, draw_src = resolve_draw(teams_rows, a.draw)
    if pods is None:            # membership unpublished -> take one admissible split
        from ti_predict.swiss import admissible_two_pod_partitions
        pods = admissible_two_pod_partitions(r1)[0]
        draw_src += " (one admissible pod membership; this study compares POLICIES)"

    # primary scenario (strategic D4): archive -> P -> policy A -> policy B
    teams, rb = archive(pods, strength, a.sims, a.seed, "strategic", r1=r1, c=c)
    P = P_from(teams, rb, a.sims)
    slate, expK, _ = assign(P)
    asgA = asg_from_slate(slate)
    KA = kcur(asgA, rb, a.sims)
    asgB, efB = local_search(asgA, rb, a.sims)
    efA = ef(KA)

    # robustness (policy C view): re-evaluate A and B under each D4 scenario's own archive
    scen_pts = {"A": {}, "B": {}}
    for sc in ("strategic", "noisy", "random"):
        _, rbx = archive(pods, strength, a.sims, a.seed + 1, sc, r1=r1, c=c)
        scen_pts["A"][sc] = ef(kcur(asgA, rbx, a.sims))
        scen_pts["B"][sc] = ef(kcur(asgB, rbx, a.sims))
    worst = {p: min(scen_pts[p].values()) for p in ("A", "B")}
    robust_choice = "B" if worst["B"] >= worst["A"] else "A"

    out = {
        "status": "MODEL-CONDITIONAL STRATEGY SIMULATION - NOT an empirical backtest; no crowd%",
        "strengths": ssrc, "radiant_c": round(c, 4), "draw": draw_src,
        "sims": a.sims, "seed": a.seed,
        "policy_A_max_expected_correct": {
            "expected_correct": round(expK, 3), "expected_points": round(efA, 1),
            "slate": slate_str(asgA)},
        "policy_B_points_local_search": {
            "method": "pairwise-swap hill climb from A (LOCAL optimum, not proven global)",
            "expected_correct": round(float(kcur(asgB, rb, a.sims).mean()), 3),
            "expected_points": round(efB, 1), "slate": slate_str(asgB)},
        "points_gain_B_over_A": round(efB - efA, 1),
        "robustness_across_D4_scenarios": scen_pts,
        "worst_case_points": {p: round(worst[p], 1) for p in worst},
        "robust_choice": robust_choice,
        "scoring_table": "group f(K), convex (docs/contest-official-ti15.md sec 3)",
        "caveat": ("optimizes E[f(K)] under the model only; does NOT prove the model predicts "
                   "(Phase 1/2); no player pick-share, so no anti-crowd policy is attempted"),
    }
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "policy_compare.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[{out['status']}]")
    print(f"strengths={ssrc} | sims={a.sims} | seed={a.seed}\n")
    print(f"A  max E[correct]      : E[correct]={expK:.2f}  E[points]={efA:.0f}")
    print(f"B  local-search E[pts] : E[correct]={kcur(asgB, rb, a.sims).mean():.2f}  "
          f"E[points]={efB:.0f}  (+{efB - efA:.0f} vs A; local optimum, not proven global)")
    print("\nrobustness E[points] across D4 scenarios:")
    for p in ("A", "B"):
        row = "  ".join(f"{sc}={scen_pts[p][sc]:.0f}" for sc in ("strategic", "noisy", "random"))
        print(f"  policy {p}: {row}  | worst={worst[p]:.0f}")
    print(f"\nrobust choice (best worst-case): {robust_choice}")
    print(f"A slate: {slate_str(asgA)}")
    if asgB != asgA:
        print(f"B slate: {slate_str(asgB)}")
    else:
        print("B slate: identical to A (convexity did not move the optimum here)")
    print(f"\nwrote backtest2/reports/policy_compare.json  ({out['caveat']})")


if __name__ == "__main__":
    main()
