"""Pre-draw uncertainty decomposition at high precision (research; not a prediction).

Separates the sources of uncertainty in each team's assigned-bucket probability under the neutral
(uniform legal) pre-draw model:
  mc        Monte Carlo standard error at the marginal sample size (analytic sqrt(p(1-p)/n)).
  draw      spread across individual legal draws: sd over K_DRAWS fixed draws of the per-draw
            bucket probability (each estimated with M_SIMS sims; includes an MC component of about
            sqrt(p(1-p)/M_SIMS), stated, not subtracted).
  strength  spread under strength-estimation uncertainty: sd of the marginal probability across
            N_BOOT event-block-bootstrap refits of B-bt (training events resampled with
            replacement; same simulation seeds -> common random numbers damp the MC part).
  d4        |marginal P(strategic) - marginal P(random)| for the decider opponent-choice policy.
Also reports each team's assigned bucket, second-best bucket, and probability gap, and classifies
slots as draw-independent or draw-sensitive.

Runs on the LIVE (refreshed) universe via the production strength loader.
Run: python -m backtest2.predraw_decompose --cutoff 2026-08-10T00:00:00Z
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ti_predict.backtest as bt_mod
from backtest2.pre_draw import marginal_P, sample_pods
from ti_predict.assign import assign
from ti_predict.calibrate import bt_strengths, est_c
from ti_predict.contest_rules import BUCKETS, PRODUCTION_HALF_LIFE_DAYS
from ti_predict.predict_ti15 import load_teams, parse_cutoff
from ti_predict.swiss import monte_carlo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARGINAL_SIMS = 40000
K_DRAWS = 60
M_SIMS = 1000
N_BOOT = 20
BOOT_SIMS = 6000
SEED = 20260811


def bootstrap_strengths(cut_ts, n_boot, seed):
    """Event-block bootstrap of the training maps -> B-bt refits (uncertainty in strengths)."""
    uni, _, _ = bt_mod.load()
    train = [m for m in uni if m["start_time"] < cut_ts]
    by_event = defaultdict(list)
    for m in train:
        by_event[m["leagueid"]].append(m)
    events = sorted(by_event)
    rng = random.Random(seed)
    reps = []
    for _ in range(n_boot):
        samp = [ev for _ in events for ev in [events[rng.randrange(len(events))]]]
        rows = [m for ev in samp for m in by_event[ev]]
        smap = bt_strengths(rows, cut_ts, hl=PRODUCTION_HALF_LIFE_DAYS)
        reps.append((smap, float(est_c(rows, smap))))
    return reps


def main():
    ap = argparse.ArgumentParser(description="Pre-draw uncertainty decomposition (research)")
    ap.add_argument("--cutoff", default="2026-08-10T00:00:00Z")
    a = ap.parse_args()
    teams = load_teams()
    names = [t["team"] for t in teams]
    region = {t["team"]: t["region"] for t in teams}
    cut_ts, cut_iso = parse_cutoff(a.cutoff)
    from ti_predict.predict_ti15 import bt_strengths_for
    strength, c, n_train, _, _ = bt_strengths_for(teams, cut_ts)

    # marginal P at high precision + assignment
    P = marginal_P(names, "uniform", strength, region, MARGINAL_SIMS, SEED, c)
    _, exp_c, rows = assign(P)
    asg = {t: b for t, b, _ in rows}

    # draw spread: per-draw P over fixed draws
    per_draw = {t: [] for t in names}
    for d in range(K_DRAWS):
        pods = sample_pods(names, "uniform", random.Random(SEED * 31 + d), strength, region)
        Pd = monte_carlo(pods, strength, n=M_SIMS, seed=SEED + 7 * d, c=c)
        for t in names:
            per_draw[t].append(Pd[t][asg[t]])

    # strength spread: bootstrap refits, marginal P with common seeds
    reps = bootstrap_strengths(cut_ts, N_BOOT, SEED)
    per_boot = {t: [] for t in names}
    for smap, cb in reps:
        sb = {t: float(smap.get(t, 0.0)) for t in names}
        Pb = marginal_P(names, "uniform", sb, region, BOOT_SIMS, SEED, cb)
        for t in names:
            per_boot[t].append(Pb[t][asg[t]])

    # d4 policy spread
    P_rand = marginal_P(names, "uniform", strength, region, 20000, SEED + 999, c)
    # marginal_P uses strategic; recompute with random choice via a local variant
    from ti_predict.swiss import simulate_one
    tally = {t: {b: 0 for b in BUCKETS} for t in names}
    for k in range(20000):
        base = (SEED + 999) * 1_000_003 + k
        pods = sample_pods(names, "uniform", random.Random(base * 5 + 1), strength, region)
        bucket = simulate_one(pods, strength, random.Random(base * 5 + 2), None, "random", c=c)
        for t, b in bucket.items():
            tally[t][b] += 1
    P_d4rand = {t: {b: tally[t][b] / 20000 for b in BUCKETS} for t in names}

    table = []
    for t in names:
        b = asg[t]
        p = P[t][b]
        ranked = sorted(BUCKETS, key=lambda x: -P[t][x])
        second = ranked[1] if ranked[0] == b else ranked[0]
        table.append({
            "team": t, "assigned": b, "p": round(p, 4),
            "second": second, "second_p": round(P[t][second], 4),
            "gap": round(p - P[t][second], 4),
            "mc_se": round(float(np.sqrt(p * (1 - p) / MARGINAL_SIMS)), 4),
            "draw_sd": round(float(np.std(per_draw[t], ddof=1)), 4),
            "strength_sd": round(float(np.std(per_boot[t], ddof=1)), 4),
            "d4_abs_dp": round(abs(P_rand[t][b] - P_d4rand[t][b]), 4),
        })
    table.sort(key=lambda r: r["gap"])
    out = {"status": "PRE-DRAW RESEARCH - uncertainty decomposition; not an official prediction",
           "cutoff": cut_iso, "train_maps": n_train, "radiant_c": round(c, 4),
           "marginal_sims": MARGINAL_SIMS, "k_draws": K_DRAWS, "m_sims_per_draw": M_SIMS,
           "n_bootstrap": N_BOOT, "seed": SEED,
           "expected_correct": round(exp_c, 3),
           "note": ("draw_sd includes an MC component of about sqrt(p(1-p)/M_SIMS); strength_sd "
                    "uses common seeds so its MC component is damped; d4_abs_dp compares "
                    "strategic vs random decider opponent choice on 20000-sim marginals"),
           "table": table}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "predraw_decompose.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[{out['status']}] cutoff {cut_iso}, E[correct]={out['expected_correct']}")
    print(f"{'team':<17} {'slot':>13} {'p':>6} {'2nd':>13} {'gap':>6} "
          f"{'mc':>6} {'draw':>6} {'str':>6} {'d4':>6}")
    for r in table:
        print(f"{r['team']:<17} {r['assigned']:>13} {r['p']:>6} {r['second']:>13} {r['gap']:>6} "
              f"{r['mc_se']:>6} {r['draw_sd']:>6} {r['strength_sd']:>6} {r['d4_abs_dp']:>6}")
    print("wrote backtest2/reports/predraw_decompose.json")


if __name__ == "__main__":
    main()
