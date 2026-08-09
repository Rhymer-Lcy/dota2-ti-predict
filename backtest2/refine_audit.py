"""Adversarial audit of the production points_refinement rule (research; no production output).

The previous round promoted a verified expected-points refinement into production on the strength of
one held-out result (+18.3 +/- 5.5 points on the uniform-sample-1 draw). This module attacks that
result and measures the deployed rule's operating characteristics on data that took NO part in its
development. All experiments run on the FROZEN 2026-08-01 data snapshot (data/ti2026/snapshot_0801)
so that the concurrent data refresh cannot contaminate the reproduction; strengths are the same
B-bt half-life-90 side-neutral configuration the original study used.

Experiments (all seeds fresh - disjoint from every previously used seed):
  claim   Reproduce the original sample-1 slates deterministically (asgA Hungarian, asgB swapped),
          then estimate the paired points gain of asgB vs asgA on N_FRESH completely new 40k-sim
          archives, plus D4-scenario variants (noisy/random deciders), strength perturbations, and
          radiant-c variants. The slates are FIXED here - no search touches these archives - so this
          is pure estimation of the promoted effect.
  null    Operating characteristics of the FULL deployed pipeline (Hungarian from the search
          archive's P -> swap search -> independent verify archive -> adopt iff paired gain > 2 se):
          replicated end-to-end on fresh archive pairs for three draws (two with no known boundary
          pair, one with the known pair). Each rep's final slate is scored against a 200k-sim
          ground-truth archive; reports proposal rate, adoption rate, true gain of adopted slates,
          false-positive count (adopted with true gain <= 0), and winner's-curse shrinkage
          (reported verify gain vs ground-truth gain).
  search  Solver adequacy: on the ground-truth archives, compare Hungarian / pairwise-swap optimum /
          multi-start / simulated annealing (2-swap + 3-cycle moves); search runs on a 40k archive,
          all found slates are scored on the 200k ground truth. Quantifies any optimality gap beyond
          the pairwise neighborhood. All results are best-found-under-procedure, not global optima.

Run: python -m backtest2.refine_audit --exp claim|null|search
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ti_predict.backtest as bt_mod
from backtest2.compare_policies import BIDX, FVEC, archive, asg_from_slate, kcur, local_search
from backtest2.solver_study import random_feasible, three_cycle
from ti_predict.assign import assign
from ti_predict.calibrate import bt_strengths, est_c
from ti_predict.contest_rules import PRODUCTION_HALF_LIFE_DAYS
from ti_predict.predict_ti15 import load_teams, parse_cutoff

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "data", "ti2026", "snapshot_0801")
REPORTS = os.path.join(REPO, "backtest2", "reports")
SNAP_CUTOFF = "2026-08-02T00:00:00Z"          # the cutoff the original study used
ORIG_SEED = 20260809                           # solver_study seed (for slate reproduction only)
N_FRESH = 6                                    # fresh 40k archives for the claim experiment
N_SIMS = 40000                                 # production simulation count
N_TRUTH = 200000                               # ground-truth archive size
FRESH_BASE = 777000                            # seed ranges never used by any prior study
NULL_BASE = 888000
TRUTH_BASE = 999000


def snapshot_strengths():
    """B-bt hl=90 strengths + radiant c from the frozen 2026-08-01 snapshot (not live processed/)."""
    if not os.path.isdir(SNAP):
        raise SystemExit(f"snapshot directory missing: {os.path.relpath(SNAP, REPO)}")
    old_proc, old_inputs = bt_mod.PROC, bt_mod.INPUTS
    bt_mod.PROC = SNAP
    bt_mod.INPUTS = SNAP
    try:
        uni, _, _ = bt_mod.load()
    finally:
        bt_mod.PROC, bt_mod.INPUTS = old_proc, old_inputs
    cut_ts, _ = parse_cutoff(SNAP_CUTOFF)
    train = [m for m in uni if m["start_time"] < cut_ts]
    smap = bt_strengths(train, cut_ts, hl=PRODUCTION_HALF_LIFE_DAYS)
    c = float(est_c(train, smap))
    names = [t["team"] for t in load_teams()]
    missing = [t for t in names if t not in smap]
    if missing:
        raise SystemExit(f"snapshot strengths missing teams: {missing}")
    return {t: float(smap[t]) for t in names}, c, names


def sample1_draw(names):
    """Reproduce solver_study's uniform-sample-1 draw exactly (same rng construction)."""
    rng = random.Random(ORIG_SEED * 13 + 1)
    order = list(names)
    rng.shuffle(order)
    return order[:8], order[8:]


def sample2_draw(names):
    rng = random.Random(ORIG_SEED * 13 + 2)
    order = list(names)
    rng.shuffle(order)
    return order[:8], order[8:]


def reproduce_slates(pods, strength, c):
    """Re-run the original sample-1 optimize-half pipeline to obtain the FIXED asgA / asgB pair."""
    from backtest2.compare_policies import P_from
    seed = ORIG_SEED + 100 * 1                 # solver_study: SEED + 100*i, i=1 for sample-1
    n_half = 15000
    _, rb = archive(pods, strength, 2 * n_half, seed, "strategic", r1=None, c=c)
    rb_opt = {t: v[:n_half] for t, v in rb.items()}
    P_opt = P_from(list(rb), rb_opt, n_half)
    slate, _, _ = assign(P_opt)
    asgA = asg_from_slate(slate)
    asgB, _ = local_search(asgA, rb_opt, n_half)
    return asgA, asgB


def paired(asgX, asgY, rb, n):
    """Per-sim points difference X - Y: mean, analytic se, correct-count deltas, tail shifts."""
    d = FVEC[kcur(asgX, rb, n)].astype(np.float64) - FVEC[kcur(asgY, rb, n)]
    kx, ky = kcur(asgX, rb, n), kcur(asgY, rb, n)
    return {"gain": round(float(d.mean()), 2),
            "se": round(float(d.std(ddof=1) / np.sqrt(n)), 2),
            "d_expected_correct": round(float(kx.mean() - ky.mean()), 4),
            "d_p_ge10": round(float((kx >= 10).mean() - (ky >= 10).mean()), 5),
            "d_p_ge12": round(float((kx >= 12).mean() - (ky >= 12).mean()), 5)}


def exp_claim():
    strength, c, names = snapshot_strengths()
    pods = sample1_draw(names)
    asgA, asgB = reproduce_slates(pods, strength, c)
    moves = sorted(t for t in asgB if asgB[t] != asgA[t])
    out = {"experiment": "claim", "snapshot_cutoff": SNAP_CUTOFF, "radiant_c": round(c, 4),
           "reproduced_moves": moves, "fresh_archives": [], "d4_variants": {},
           "strength_perturbations": [], "c_variants": {}}
    for i in range(N_FRESH):
        _, rb = archive(pods, strength, N_SIMS, FRESH_BASE + i, "strategic", r1=None, c=c)
        out["fresh_archives"].append(paired(asgB, asgA, rb, N_SIMS))
    for choice in ("noisy", "random"):
        _, rb = archive(pods, strength, N_SIMS, FRESH_BASE + 50, choice, r1=None, c=c)
        out["d4_variants"][choice] = paired(asgB, asgA, rb, N_SIMS)
    rngp = np.random.default_rng(FRESH_BASE)
    for j in range(8):
        pert = {t: s + float(rngp.normal(0, 0.1)) for t, s in strength.items()}
        _, rb = archive(pods, pert, 20000, FRESH_BASE + 100 + j, "strategic", r1=None, c=c)
        out["strength_perturbations"].append(paired(asgB, asgA, rb, 20000))
    for cv in (0.05, 0.15):
        _, rb = archive(pods, strength, 20000, FRESH_BASE + 200, "strategic", r1=None, c=cv)
        out["c_variants"][str(cv)] = paired(asgB, asgA, rb, 20000)
    gains = [a["gain"] for a in out["fresh_archives"]]
    out["summary"] = {"fresh_mean_gain": round(float(np.mean(gains)), 2),
                      "fresh_min_gain": min(gains), "fresh_max_gain": max(gains),
                      "all_positive": bool(all(g > 0 for g in gains))}
    return out


def run_pipeline_once(pods, strength, c, seed):
    """One end-to-end replication of the deployed rule on fresh archives; returns decision record."""
    from backtest2.compare_policies import P_from
    _, rb_s = archive(pods, strength, N_SIMS, seed, "strategic", r1=None, c=c)
    P = P_from(list(rb_s), rb_s, N_SIMS)
    slate, _, _ = assign(P)
    asgA = asg_from_slate(slate)
    asgB, _ = local_search(asgA, rb_s, N_SIMS)
    moves = sorted(t for t in asgB if asgB[t] != asgA[t])
    if not moves:
        return {"proposed": False, "adopted": False, "moves": [], "asgA": asgA, "final": asgA}
    _, rb_v = archive(pods, strength, N_SIMS, seed + 500000, "strategic", r1=None, c=c)
    d = FVEC[kcur(asgB, rb_v, N_SIMS)].astype(np.float64) - FVEC[kcur(asgA, rb_v, N_SIMS)]
    gain = float(d.mean())
    se = float(d.std(ddof=1) / np.sqrt(N_SIMS))
    adopted = gain > 2.0 * se
    return {"proposed": True, "adopted": bool(adopted), "moves": moves,
            "verify_gain": round(gain, 2), "verify_se": round(se, 2),
            "asgA": asgA, "final": asgB if adopted else asgA, "asgB": asgB}


def exp_null(reps):
    strength, c, names = snapshot_strengths()
    draws = {"fixed-synthetic": (names[0::2], names[1::2]),
             "uniform-sample-2": sample2_draw(names),
             "uniform-sample-1": sample1_draw(names)}
    out = {"experiment": "null", "reps_per_draw": reps, "n_sims": N_SIMS, "n_truth": N_TRUTH,
           "draws": {}}
    for di, (label, pods) in enumerate(draws.items()):
        _, rb_t = archive(pods, strength, N_TRUTH, TRUTH_BASE + di, "strategic", r1=None, c=c)
        recs = []
        for r in range(reps):
            rec = run_pipeline_once(pods, strength, c, NULL_BASE + 1000 * di + r)
            row = {"proposed": rec["proposed"], "adopted": rec["adopted"], "moves": rec["moves"]}
            if rec["proposed"]:
                row["verify_gain"] = rec["verify_gain"]
                row["verify_se"] = rec["verify_se"]
                tp = paired(rec["asgB"], rec["asgA"], rb_t, N_TRUTH)
                row["truth_gain_of_proposal"] = tp["gain"]
                row["truth_se"] = tp["se"]
            recs.append(row)
        n_prop = sum(1 for r in recs if r["proposed"])
        n_adopt = sum(1 for r in recs if r["adopted"])
        fp = sum(1 for r in recs if r["adopted"] and r.get("truth_gain_of_proposal", 0) <= 0)
        out["draws"][label] = {
            "proposal_rate": f"{n_prop}/{reps}", "adoption_rate": f"{n_adopt}/{reps}",
            "false_positives_adopted_with_nonpositive_truth": fp,
            "adopted_truth_gains": [r["truth_gain_of_proposal"] for r in recs if r["adopted"]],
            "adopted_verify_gains": [r["verify_gain"] for r in recs if r["adopted"]],
            "reps": recs}
    return out


def anneal(asg0, rb, n, seed, iters=30000, t0=30.0, t1=0.5):
    """Simulated annealing over 2-swaps and 3-cycles on E[f(K)]; returns best assignment found."""
    rng = random.Random(seed)
    asg = dict(asg0)
    K = kcur(asg, rb, n)
    cur = float(FVEC[K].mean())
    best_asg, best = dict(asg), cur
    teams = list(asg)
    for it in range(iters):
        temp = t0 * (t1 / t0) ** (it / iters)
        if rng.random() < 0.7:                                # 2-swap
            t1_, t2_ = rng.sample(teams, 2)
            if asg[t1_] == asg[t2_]:
                continue
            delta = ((rb[t1_] == BIDX[asg[t2_]]).astype(np.int16) + (rb[t2_] == BIDX[asg[t1_]])
                     - (rb[t1_] == BIDX[asg[t1_]]) - (rb[t2_] == BIDX[asg[t2_]]))
            nxt = float(FVEC[K + delta].mean())
            if nxt > cur or rng.random() < np.exp((nxt - cur) / max(temp, 1e-9)):
                asg[t1_], asg[t2_] = asg[t2_], asg[t1_]
                K = K + delta
                cur = nxt
        else:                                                 # 3-cycle
            t1_, t2_, t3_ = rng.sample(teams, 3)
            b1, b2, b3 = asg[t1_], asg[t2_], asg[t3_]
            if b1 == b2 == b3:
                continue
            delta = ((rb[t1_] == BIDX[b2]).astype(np.int16) - (rb[t1_] == BIDX[b1])
                     + (rb[t2_] == BIDX[b3]) - (rb[t2_] == BIDX[b2])
                     + (rb[t3_] == BIDX[b1]) - (rb[t3_] == BIDX[b3]))
            nxt = float(FVEC[K + delta].mean())
            if nxt > cur or rng.random() < np.exp((nxt - cur) / max(temp, 1e-9)):
                asg[t1_], asg[t2_], asg[t3_] = b2, b3, b1
                K = K + delta
                cur = nxt
        if cur > best + 1e-9:
            best_asg, best = dict(asg), cur
    return best_asg


def exp_search():
    from backtest2.compare_policies import P_from
    strength, c, names = snapshot_strengths()
    out = {"experiment": "search", "note": "all results best-found-under-procedure, not global",
           "draws": {}}
    for di, (label, pods) in enumerate((("fixed-synthetic", (names[0::2], names[1::2])),
                                        ("uniform-sample-1", sample1_draw(names)))):
        _, rb_s = archive(pods, strength, N_SIMS, FRESH_BASE + 300 + di, "strategic", r1=None, c=c)
        _, rb_t = archive(pods, strength, N_TRUTH, TRUTH_BASE + 10 + di, "strategic", r1=None, c=c)
        P = P_from(list(rb_s), rb_s, N_SIMS)
        slate, _, _ = assign(P)
        asgA = asg_from_slate(slate)
        asgSwap, _ = local_search(asgA, rb_s, N_SIMS)
        rng = random.Random(FRESH_BASE + 400 + di)
        best_ms, best_val = asgSwap, float(FVEC[kcur(asgSwap, rb_s, N_SIMS)].mean())
        for _ in range(50):
            cand, val = local_search(random_feasible(list(rb_s), rng), rb_s, N_SIMS)
            if val > best_val + 1e-9:
                best_ms, best_val = cand, val
        asg3, _ = three_cycle(best_ms, rb_s, N_SIMS)
        best_sa = asgSwap
        for k in range(5):
            cand = anneal(asgSwap, rb_s, N_SIMS, FRESH_BASE + 500 + 10 * di + k)
            cand, _ = local_search(cand, rb_s, N_SIMS)
            if (float(FVEC[kcur(cand, rb_s, N_SIMS)].mean())
                    > float(FVEC[kcur(best_sa, rb_s, N_SIMS)].mean()) + 1e-9):
                best_sa = cand
        rows = {}
        for nm, a in (("hungarian", asgA), ("swap", asgSwap), ("multistart50", best_ms),
                      ("swap+3cycle", asg3), ("annealx5", best_sa)):
            rows[nm] = {"truth_points": round(float(FVEC[kcur(a, rb_t, N_TRUTH)].mean()), 1),
                        "truth_gain_vs_hungarian": paired(a, asgA, rb_t, N_TRUTH)["gain"],
                        "moves_vs_hungarian": sorted(t for t in a if a[t] != asgA[t])}
        out["draws"][label] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description="Adversarial audit of points_refinement (research)")
    ap.add_argument("--exp", choices=("claim", "null", "search"), required=True)
    ap.add_argument("--reps", type=int, default=10, help="replications per draw (null experiment)")
    a = ap.parse_args()
    if a.exp == "claim":
        out = exp_claim()
    elif a.exp == "null":
        out = exp_null(a.reps)
    else:
        out = exp_search()
    out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"refine_audit_{a.exp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k not in ("draws",)}, indent=2)[:2000])
    if "draws" in out:
        for label, d in out["draws"].items():
            print(f"--- {label} ---")
            print(json.dumps({k: v for k, v in d.items() if k != "reps"}, indent=1)[:1500])
    print(f"wrote {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
