"""Bounded challenger: B-bt ridge (uncertainty shrinkage) sweep, nested prequential (research).

The admissibility audit (backtest2/results-adversarial.md) found exactly one orthogonal candidate
that current data supports without lookahead risk: the Bradley-Terry ridge strength lam (frozen at
1.0), which acts as uncertainty-aware shrinkage toward the mean - strongest for thin-sample teams.
Pre-declared grid {0.5, 1.0, 2.0, 4.0}; protocol identical to the D2 half-life sweep: 23 frozen 2026
event folds from the 2026-08-01 snapshot; for each fold the nested choice minimizes pooled weighted
log-loss on STRICTLY EARLIER folds (first MIN_PRIOR_FOLDS folds use the frozen lam=1). Primary
metric event-weighted log-loss; event-blocked bootstrap on the nested-minus-frozen difference.

Run: python -m backtest2.lambda_study
"""
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ti_predict.backtest as bt_mod
from ti_predict.backtest import EPS, fit_bt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "data", "ti2026", "snapshot_0801")
LAMBDAS = [0.5, 1.0, 2.0, 4.0]        # pre-declared, frozen before results
FROZEN_LAM = 1.0
MIN_PRIOR_FOLDS = 4
SEED = 20260810


def _ll(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def wll(rows):
    sw = sum(w for w, _, _ in rows)
    return sum(w * _ll(p, y) for w, y, p in rows) / sw if sw else float("nan")


def main():
    old = bt_mod.PROC, bt_mod.INPUTS
    bt_mod.PROC = SNAP
    bt_mod.INPUTS = SNAP
    try:
        uni, tgt, folds = bt_mod.load()
    finally:
        bt_mod.PROC, bt_mod.INPUTS = old
    tgt_by_fold = defaultdict(list)
    for r in tgt:
        tgt_by_fold[r["leagueid"]].append(r)
    folds = sorted((f for f in folds if tgt_by_fold.get(f["leagueid"])),
                   key=lambda f: f["cutoff_ts"])

    preds = {lam: {} for lam in LAMBDAS}
    for f in folds:
        cut = f["cutoff_ts"]
        train = [m for m in uni if m["start_time"] < cut]
        ev = tgt_by_fold[f["leagueid"]]
        if not train:
            continue
        for lam in LAMBDAS:
            pred = fit_bt(train, cut, lam=lam)
            preds[lam][f["leagueid"]] = [(m["weight"], m["a_won"],
                                          pred(m["team_a"], m["team_b"])) for m in ev]
    order = [f["leagueid"] for f in folds if f["leagueid"] in preds[FROZEN_LAM]]

    chosen, nested = {}, {}
    for i, lg in enumerate(order):
        if i < MIN_PRIOR_FOLDS:
            lam = FROZEN_LAM
        else:
            prior = order[:i]
            lam = min(LAMBDAS, key=lambda L: wll([r for l in prior for r in preds[L][l]]))
        chosen[lg] = lam
        nested[lg] = preds[lam][lg]

    pooled = {f"lam_{lam}": round(wll([r for lg in order for r in preds[lam][lg]]), 4)
              for lam in LAMBDAS}
    pooled["nested"] = round(wll([r for lg in order for r in nested[lg]]), 4)
    wins = sum(1 for lg in order if wll(nested[lg]) < wll(preds[FROZEN_LAM][lg]) - 1e-9)

    rng = random.Random(SEED)
    diffs = []
    for _ in range(2000):
        samp = [order[rng.randrange(len(order))] for _ in order]
        diffs.append(wll([r for l in samp for r in nested[l]])
                     - wll([r for l in samp for r in preds[FROZEN_LAM][l]]))
    diffs.sort()
    ci = (round(diffs[50], 4), round(diffs[1949], 4))

    out = {"grid": LAMBDAS, "frozen_lam": FROZEN_LAM, "n_folds": len(order),
           "pooled_logloss": pooled,
           "nested_fold_wins_vs_frozen": f"{wins}/{len(order)}",
           "nested_minus_frozen_pooled": round(pooled["nested"] - pooled["lam_1.0"], 4),
           "event_blocked_bootstrap_ci95": ci,
           "lam_chosen_sequence": [chosen[lg] for lg in order],
           "note": ("nested prequential on the frozen 2026-08-01 snapshot folds; grid pre-declared; "
                    "production changes only under the promotion gate")}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "lambda_study.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
