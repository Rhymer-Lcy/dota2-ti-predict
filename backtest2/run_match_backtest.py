"""Phase 1 / D2 - pre-registered B-bt half-life sweep on 2026 events, NESTED (inner tuning).

Pre-registered grid (frozen before results): B-bt time-decay half-life in {45,60,90,120,180} days.
Protocol (docs/validation-plan-v2.md sec 1): folds = 2026 events ordered by cutoff. For each outer
fold E, the half-life is chosen to minimize pooled weighted log-loss on folds STRICTLY EARLIER than E
(no lookahead), frozen, then applied to E ("nested"). Compared against frozen B-bt (fixed hl=90) and
each fixed hl. Primary metric: event-level weighted log-loss; also pooled Brier and a fold-win count;
uncertainty via an event-blocked bootstrap on the nested-minus-fixed90 pooled log-loss difference.

This is the INNER tuning set (2026 events only). The config it freezes is later tested ONCE on the
TI2024/TI2025 outer held-out sets (D3) with no further tuning. Selection here does not by itself
change production: per the plan's rule, a variant must clearly and stably beat frozen B-bt.

Run: python -m backtest2.run_match_backtest
"""
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.backtest import EPS, fit_bt, load

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HALF_LIVES = [45, 60, 90, 120, 180]      # pre-registered, frozen before results
FROZEN_HL = 90                            # current production B-bt
MIN_PRIOR_FOLDS = 4                       # need this many earlier folds before trusting a choice


def _ll(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def wll(pairs):
    sw = sum(w for w, _, _ in pairs)
    return sum(w * _ll(p, y) for w, y, p in pairs) / sw if sw else float("nan")


def brier(pairs):
    sw = sum(w for w, _, _ in pairs)
    return sum(w * (p - y) ** 2 for w, y, p in pairs) / sw if sw else float("nan")


def main():
    uni, tgt, folds = load()
    tgt_by_fold = defaultdict(list)
    for r in tgt:
        tgt_by_fold[r["leagueid"]].append(r)
    folds = [f for f in folds if tgt_by_fold.get(f["leagueid"])]      # keep folds with target maps
    folds.sort(key=lambda f: f["cutoff_ts"])

    # per (hl, fold) -> list of (w, y, p) on that fold's target maps
    preds = {hl: {} for hl in HALF_LIVES}
    for f in folds:
        cut = f["cutoff_ts"]
        train = [m for m in uni if m["start_time"] < cut]
        ev = tgt_by_fold[f["leagueid"]]
        if not train:
            continue
        for hl in HALF_LIVES:
            pred = fit_bt(train, cut, half_life=hl)
            preds[hl][f["leagueid"]] = [(m["weight"], m["a_won"], pred(m["team_a"], m["team_b"]))
                                        for m in ev]

    order = [f["leagueid"] for f in folds if f["leagueid"] in preds[FROZEN_HL]]

    # nested choice: for fold i, pick hl minimizing pooled wll on folds[0..i-1]; else FROZEN_HL
    chosen, nested_pairs = {}, {}
    for i, lg in enumerate(order):
        if i < MIN_PRIOR_FOLDS:
            hl = FROZEN_HL
        else:
            prior = order[:i]
            hl = min(HALF_LIVES, key=lambda h: wll([pr for l in prior for pr in preds[h][l]]))
        chosen[lg] = hl
        nested_pairs[lg] = preds[hl][lg]

    # per-fold table + pooled metrics
    rows = []
    for lg in order:
        rows.append({"leagueid": lg, "n": len(preds[FROZEN_HL][lg]),
                     "ll_fixed90": round(wll(preds[FROZEN_HL][lg]), 4),
                     "ll_nested": round(wll(nested_pairs[lg]), 4),
                     "hl_chosen": chosen[lg]})
    pooled = {f"fixed_hl{hl}": round(wll([pr for lg in order for pr in preds[hl][lg]]), 4)
              for hl in HALF_LIVES}
    pooled["nested"] = round(wll([pr for lg in order for pr in nested_pairs[lg]]), 4)
    brier_pooled = {"fixed_hl90": round(brier([pr for lg in order for pr in preds[FROZEN_HL][lg]]), 4),
                    "nested": round(brier([pr for lg in order for pr in nested_pairs[lg]]), 4)}

    # fold-win: nested strictly better than fixed90 on per-fold wll
    wins = sum(1 for lg in order if wll(nested_pairs[lg]) < wll(preds[FROZEN_HL][lg]) - 1e-9)

    # event-blocked bootstrap on pooled (nested - fixed90) log-loss difference
    rng = random.Random(20260813)
    diffs = []
    for _ in range(2000):
        samp = [order[rng.randrange(len(order))] for _ in order]
        a = wll([pr for lg in samp for pr in nested_pairs[lg]])
        b = wll([pr for lg in samp for pr in preds[FROZEN_HL][lg]])
        diffs.append(a - b)
    diffs.sort()
    ci = (round(diffs[int(0.025 * len(diffs))], 4), round(diffs[int(0.975 * len(diffs))], 4))

    out = {"grid": HALF_LIVES, "frozen_hl": FROZEN_HL, "n_folds": len(order),
           "pooled_logloss": pooled, "pooled_brier": brier_pooled,
           "nested_fold_wins_vs_fixed90": f"{wins}/{len(order)}",
           "nested_minus_fixed90_pooled": round(pooled["nested"] - pooled["fixed_hl90"], 4),
           "event_blocked_bootstrap_ci95": ci,
           "hl_chosen_sequence": [chosen[lg] for lg in order],
           "per_fold": rows,
           "note": ("INNER tuning on 2026 events only; grid pre-registered. A negative "
                    "nested_minus_fixed90 with a CI excluding 0 would favour adaptive half-life; "
                    "otherwise keep frozen B-bt (hl=90). Outer TI2024/TI2025 test is separate (D3).")}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "match_backtest_hl.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"2026 inner tuning: {len(order)} folds | grid {HALF_LIVES} | frozen hl={FROZEN_HL}")
    print("pooled weighted log-loss:")
    for k in [f"fixed_hl{hl}" for hl in HALF_LIVES] + ["nested"]:
        print(f"  {k:<12} {pooled[k]:.4f}")
    print(f"pooled Brier: fixed90={brier_pooled['fixed_hl90']}  nested={brier_pooled['nested']}")
    print(f"nested - fixed90 pooled logloss: {out['nested_minus_fixed90_pooled']:+.4f}  "
          f"(event-blocked 95% CI {ci})")
    print(f"nested fold-wins vs fixed90: {wins}/{len(order)}")
    print(f"chosen half-life over time: {out['hl_chosen_sequence']}")
    print(f"\nwrote backtest2/reports/match_backtest_hl.json  ({out['note']})")


if __name__ == "__main__":
    main()
