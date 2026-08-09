"""Ensemble challenger study on the frozen v1 backtest predictions (no refitting, no lookahead).

Question: do the already-fitted independent models (A-elo, B-eloTD, C-glicko2) carry stable
information that is complementary to production B-bt? Tested as logit-space mixtures on the frozen
per-fold out-of-sample predictions dumped by ti_predict.backtest (processed/backtest_preds.csv),
so every input probability is already strictly out-of-sample for its fold.

Pre-declared candidates (frozen before results):
  E-elo-50    0.5*logit(B-bt) + 0.5*logit(A-elo)
  E-eloTD-50  0.5*logit(B-bt) + 0.5*logit(B-eloTD)
  E-glicko-50 0.5*logit(B-bt) + 0.5*logit(C-glicko2)
  E-all4      equal logit average of all four models
  E-adapt     prequential: for each fold (>=4 prior folds, else pure B-bt) pick the
              (partner, weight) pair from partners x weights {0.25, 0.5, 0.75} - or pure B-bt -
              that minimizes pooled weighted log-loss on STRICTLY EARLIER folds only.

Metrics: event-weighted log-loss (primary), Brier, calibration (slope/intercept/ECE), per-fold wins
vs pure B-bt, event-blocked bootstrap 95% CI on the pooled log-loss difference. Evaluation
orientation matches the frozen v1 screening (team_a = the TI organization side); a production-aligned
side-neutral re-evaluation is only warranted if a candidate passes this screening.

Run: python -m backtest2.ensemble_study
"""
import csv
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.calibrate import metrics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(REPO, "data", "ti2026", "processed")
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
EPS = 1e-6
PARTNERS = ("A-elo", "B-eloTD", "C-glicko2")
WEIGHTS = (0.25, 0.5, 0.75)
MIN_PRIOR_FOLDS = 4
SEED = 20260809


def lgt(p):
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def sig(x):
    return 1.0 / (1.0 + math.exp(-x))


def mix(p_base, p_partner, w):
    """Logit-space mixture: sigmoid((1-w)*logit(p_base) + w*logit(p_partner))."""
    return sig((1.0 - w) * lgt(p_base) + w * lgt(p_partner))


def wll(rows):
    sw = sum(w for w, _, _ in rows)
    return sum(w * -(y * math.log(min(max(p, EPS), 1 - EPS))
                     + (1 - y) * math.log(1 - min(max(p, EPS), 1 - EPS)))
               for w, y, p in rows) / sw


def main():
    preds = defaultdict(dict)                        # (leagueid, match_id) -> {model: p}, plus y
    y_of, fold_of = {}, defaultdict(list)
    with open(os.path.join(PROC, "backtest_preds.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["leagueid"], r["match_id"])
            preds[key][r["model"]] = float(r["p"])
            y_of[key] = int(r["y"])
    weight_of = {r["match_id"]: float(r["weight"])
                 for r in csv.DictReader(open(os.path.join(PROC, "dataset_maps.csv"),
                                              encoding="utf-8"))}
    folds = [f["leagueid"] for f in
             sorted(csv.DictReader(open(os.path.join(INPUTS, "folds.csv"), encoding="utf-8")),
                    key=lambda f: int(f["cutoff_ts"]))]
    for key in preds:
        fold_of[key[0]].append(key)
    folds = [lg for lg in folds if fold_of.get(lg)]

    def rows_for(lg, fn):
        out = []
        for key in fold_of[lg]:
            p = fn(preds[key])
            out.append((weight_of[key[1]], y_of[key], p))
        return out

    candidates = {"B-bt (production)": lambda m: m["B-bt"]}
    for pt in PARTNERS:
        candidates[f"E-{pt}-50"] = (lambda m, _pt=pt: mix(m["B-bt"], m[_pt], 0.5))
    candidates["E-all4"] = lambda m: sig(sum(lgt(m[k]) for k in
                                             ("B-bt", "A-elo", "B-eloTD", "C-glicko2")) / 4.0)

    per_fold = {name: {lg: rows_for(lg, fn) for lg in folds} for name, fn in candidates.items()}

    # E-adapt: prequential partner/weight selection on strictly earlier folds
    adapt_rows, chosen_seq = {}, []
    for i, lg in enumerate(folds):
        if i < MIN_PRIOR_FOLDS:
            choice = ("none", 0.0)
        else:
            prior = folds[:i]
            options = [("none", 0.0)] + [(pt, w) for pt in PARTNERS for w in WEIGHTS]

            def prior_ll(opt):
                pt, w = opt
                fn = (lambda m: m["B-bt"]) if pt == "none" else (
                    lambda m, _pt=pt, _w=w: mix(m["B-bt"], m[_pt], _w))
                return wll([r for l in prior for r in rows_for(l, fn)])
            choice = min(options, key=prior_ll)
        chosen_seq.append(f"{choice[0]}@{choice[1]}")
        pt, w = choice
        fn = (lambda m: m["B-bt"]) if pt == "none" else (
            lambda m, _pt=pt, _w=w: mix(m["B-bt"], m[_pt], _w))
        adapt_rows[lg] = rows_for(lg, fn)
    per_fold["E-adapt"] = adapt_rows

    base = per_fold["B-bt (production)"]
    rng = random.Random(SEED)
    report = {}
    for name, by_fold in per_fold.items():
        pooled = [r for lg in folds for r in by_fold[lg]]
        ll, br, a, b, ece = metrics(pooled)
        wins = sum(1 for lg in folds if wll(by_fold[lg]) < wll(base[lg]) - 1e-9)
        if name == "B-bt (production)":
            ci = (0.0, 0.0)
            delta = 0.0
        else:
            diffs = []
            for _ in range(2000):
                samp = [folds[rng.randrange(len(folds))] for _ in folds]
                diffs.append(wll([r for l in samp for r in by_fold[l]])
                             - wll([r for l in samp for r in base[l]]))
            diffs.sort()
            ci = (round(diffs[50], 4), round(diffs[1949], 4))
            delta = ll - metrics([r for lg in folds for r in base[lg]])[0]
        report[name] = {"pooled_logloss": round(ll, 4), "pooled_brier": round(br, 4),
                        "cal_intercept": round(a, 3), "cal_slope": round(b, 3),
                        "ece": round(ece, 4),
                        "fold_wins_vs_bbt": f"{wins}/{len(folds)}",
                        "delta_ll_vs_bbt": round(delta, 4),
                        "blocked_bootstrap_ci95": ci}

    out = {"note": ("logit mixtures on the frozen v1 out-of-sample predictions; no refits; E-adapt "
                    "selects partner/weight on strictly earlier folds only"),
           "n_folds": len(folds), "n_maps": len(preds), "seed": SEED,
           "adapt_choice_sequence": chosen_seq,
           "results": report}
    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "ensemble_study.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"{len(folds)} folds, {len(preds)} maps. Candidates vs production B-bt "
          f"(event-weighted log-loss):\n")
    print(f"{'candidate':<20} {'logloss':>8} {'dLL':>8} {'CI95':>20} {'wins':>6} "
          f"{'Brier':>7} {'slope':>6} {'ECE':>7}")
    for name, r in report.items():
        print(f"{name:<20} {r['pooled_logloss']:>8} {r['delta_ll_vs_bbt']:>8} "
              f"{str(r['blocked_bootstrap_ci95']):>20} {r['fold_wins_vs_bbt']:>6} "
              f"{r['pooled_brier']:>7} {r['cal_slope']:>6} {r['ece']:>7}")
    print(f"\nE-adapt choices over folds: {', '.join(chosen_seq)}")
    print("\nwrote backtest2/reports/ensemble_study.json")


if __name__ == "__main__":
    main()
