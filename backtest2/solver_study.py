"""Solver study: can a stronger optimizer beat the Hungarian slate on expected official points?

Protocol (guards against optimizing Monte-Carlo noise): each draw's simulation archive is split into
an OPTIMIZE half and an EVALUATE half. Policies are constructed using the optimize half only, then
scored on the untouched evaluate half with a bootstrap standard error. A policy is only interesting
if its evaluate-half gain over the Hungarian baseline exceeds noise consistently across draws.

Policies:
  A       Hungarian assignment maximizing expected correct (production).
  B-swap  pairwise-swap hill climb on E[f(K)] from A (the existing local search).
  B-multi B-swap from A plus 30 random feasible starts; best optimize-half E[f(K)] kept.
  B-3cyc  B-multi followed by exhaustive 3-cycle rotation passes.
All "B" policies are LOCAL-search candidates; none is claimed to be a global optimum.

Draws: the fixed synthetic split plus two uniform-sampled draws (draw uncertainty check).
Run: python -m backtest2.solver_study
"""
import json
import os
import random
import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest2.compare_policies import (BIDX, archive, asg_from_slate, ef, kcur, local_search,
                                        P_from)
from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.predict_ti15 import bt_strengths_for, load_teams, parse_cutoff

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20260809
N_HALF = 15000
N_STARTS = 30
CUTOFF = "2026-08-02T00:00:00Z"      # end of locally available universe data


def split_archive(rb, n_half):
    a = {t: v[:n_half] for t, v in rb.items()}
    b = {t: v[n_half:] for t, v in rb.items()}
    return a, b


def random_feasible(names, rng):
    slots = [b for b in BUCKETS for _ in range(CAPACITY[b])]
    order = list(names)
    rng.shuffle(order)
    return dict(zip(order, slots))


def three_cycle(asg, rb, n, max_pass=4):
    """Exhaustive 3-team rotation passes on E[f(K)] (both orientations per triple)."""
    asg = dict(asg)
    K = kcur(asg, rb, n)
    best = ef(K)
    teams = list(asg)
    for _ in range(max_pass):
        improved = False
        for t1, t2, t3 in combinations(teams, 3):
            b1, b2, b3 = asg[t1], asg[t2], asg[t3]
            if b1 == b2 == b3:
                continue
            for nb1, nb2, nb3 in ((b2, b3, b1), (b3, b1, b2)):
                delta = ((rb[t1] == BIDX[nb1]).astype(np.int16) - (rb[t1] == BIDX[b1])
                         + (rb[t2] == BIDX[nb2]) - (rb[t2] == BIDX[b2])
                         + (rb[t3] == BIDX[nb3]) - (rb[t3] == BIDX[b3]))
                cand = ef(K + delta)
                if cand > best + 1e-9:
                    asg[t1], asg[t2], asg[t3] = nb1, nb2, nb3
                    K = K + delta
                    best = cand
                    improved = True
                    break
        if not improved:
            break
    return asg, best


def boot_se(asg, rb, n, reps=500, seed=1):
    rng = random.Random(seed)
    K = kcur(asg, rb, n)
    vals = []
    for _ in range(reps):
        idx = np.array([rng.randrange(n) for _ in range(n)])
        vals.append(ef(K[idx]))
    return float(np.std(vals))


def paired_gain(asg, asgA, rb, n, reps=500, seed=2):
    """Bootstrap mean and se of the PER-SIM points difference vs the Hungarian baseline.

    The paired difference removes shared simulation noise, so it is the correct significance check
    for a proposed slate change (the per-policy level se overstates the uncertainty)."""
    rng = random.Random(seed)
    from ti_predict.contest_rules import GROUP_SCORE
    fvec = np.array([GROUP_SCORE[k] for k in range(17)])
    d = fvec[kcur(asg, rb, n)].astype(np.float64) - fvec[kcur(asgA, rb, n)]
    vals = []
    for _ in range(reps):
        idx = np.array([rng.randrange(n) for _ in range(n)])
        vals.append(float(d[idx].mean()))
    return float(d.mean()), float(np.std(vals))


def study_draw(label, pods, strength, c, seed):
    teams, rb = archive(pods, strength, 2 * N_HALF, seed, "strategic", r1=None, c=c)
    rb_opt, rb_eval = split_archive(rb, N_HALF)
    P_opt = P_from(teams, rb_opt, N_HALF)
    slate, expK, _ = assign(P_opt)
    asgA = asg_from_slate(slate)

    asgB, _ = local_search(asgA, rb_opt, N_HALF)
    rng = random.Random(seed + 7)
    best_asg, best_val = asgB, ef(kcur(asgB, rb_opt, N_HALF))
    for _ in range(N_STARTS):
        cand, val = local_search(random_feasible(teams, rng), rb_opt, N_HALF)
        if val > best_val + 1e-9:
            best_asg, best_val = cand, val
    asgM = best_asg
    asgC, _ = three_cycle(asgM, rb_opt, N_HALF)

    rows = {}
    for name, asg_ in (("A-hungarian", asgA), ("B-swap", asgB), ("B-multi", asgM),
                       ("B-3cyc", asgC)):
        pg, pg_se = paired_gain(asg_, asgA, rb_eval, N_HALF, seed=seed + 13)
        rows[name] = {
            "opt_half_points": round(ef(kcur(asg_, rb_opt, N_HALF)), 1),
            "eval_half_points": round(ef(kcur(asg_, rb_eval, N_HALF)), 1),
            "eval_se": round(boot_se(asg_, rb_eval, N_HALF, seed=seed + 11), 1),
            "paired_gain_vs_A": round(pg, 1), "paired_gain_se": round(pg_se, 1),
            "differs_from_A": sorted(t for t in asg_ if asg_[t] != asgA[t]),
        }
    return {"draw": label, "policies": rows}


def main():
    teams_rows = load_teams()
    names = [t["team"] for t in teams_rows]
    cut_ts, cut_iso = parse_cutoff(CUTOFF)
    strength, c, _, _, _ = bt_strengths_for(teams_rows, cut_ts)

    draws = [("fixed-synthetic", (names[0::2], names[1::2]))]
    for k in (1, 2):
        rng = random.Random(SEED * 13 + k)
        order = list(names)
        rng.shuffle(order)
        draws.append((f"uniform-sample-{k}", (order[:8], order[8:])))

    results = [study_draw(lbl, pods, strength, c, SEED + 100 * i)
               for i, (lbl, pods) in enumerate(draws)]
    out = {"note": ("optimize-half/evaluate-half protocol; all B policies are local-search "
                    "candidates, not global optima; strengths B-bt @ " + cut_iso),
           "n_half": N_HALF, "n_starts": N_STARTS, "seed": SEED, "results": results}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "solver_study.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    for res in results:
        print(f"--- draw: {res['draw']} ---")
        for name, r in res["policies"].items():
            diff = f" (moves: {', '.join(r['differs_from_A'])})" if r["differs_from_A"] else ""
            print(f"  {name:<12} opt={r['opt_half_points']:>7}  eval={r['eval_half_points']:>7} "
                  f"+/-{r['eval_se']:<5} paired_gain={r['paired_gain_vs_A']:>6}"
                  f"+/-{r['paired_gain_se']:<4}{diff}")
    print("\nwrote backtest2/reports/solver_study.json")


if __name__ == "__main__":
    main()
