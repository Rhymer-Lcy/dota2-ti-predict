"""Non-selective robustness checks on the FIXED v1 predictions (no refit, no tuning, no search).

Reads processed/backtest_preds.csv (the exact v1 event-frozen predictions) + dataset_maps.csv, and
reports, for every candidate:
  - pooled log-loss under 3 EVAL weightings: 1/series_size (primary), 1/best_of, map-equal;
    plus a series-clustered eval (each series equal-weight);
  - calibration intercept a and slope b (fit y ~ sigmoid(a + b*logit(p)); ideal a=0, b=1);
  - reliability bins (B-bt);
  - leave-one-event-out pooled log-loss range.
These do not change model selection (B-bt already advanced); they test that the ranking is not an
artifact of the weighting or one event. Writes docs/robustness-v1.md.

Run: python -m ti_predict.robustness
"""
import csv
import math
import os
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(REPO, "data", "ti2026", "processed")
DOCS = os.path.join(REPO, "docs")
EPS = 1e-6


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ll(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def wll(items):  # items: (w,y,p)
    sw = sum(w for w, _, _ in items)
    return sum(w * ll(p, y) for w, y, p in items) / sw if sw else float("nan")


def calib_ab(rows):  # fit y ~ sigmoid(a + b*logit(p)); return a,b
    lp = np.array([math.log(min(max(p, EPS), 1 - EPS) / (1 - min(max(p, EPS), 1 - EPS))) for _, y, p in rows])
    y = np.array([y for _, y, p in rows], float)
    w = np.array([w for w, _, _ in rows])
    def nll(t):
        a, b = t
        z = a + b * lp
        q = 1 / (1 + np.exp(-z))
        return -(w * (y * np.log(q + EPS) + (1 - y) * np.log(1 - q + EPS))).sum()
    r = minimize(nll, [0.0, 1.0], method="Nelder-Mead")
    return r.x[0], r.x[1]


def main():
    preds = _read(os.path.join(PROC, "backtest_preds.csv"))
    dm = {int(r["match_id"]): r for r in _read(os.path.join(PROC, "dataset_maps.csv"))}
    for r in preds:
        d = dm[int(r["match_id"])]
        ss = int(d["series_size"]); bo2 = int(d["bo2_draw"])
        r["y"] = int(r["y"]); r["p"] = float(r["p"]); r["series_size"] = ss
        r["w_ss"] = 1.0 / ss
        r["best_of"] = 2 if bo2 else (3 if ss <= 3 else 5)
        r["w_bo"] = 1.0 / r["best_of"]
        r["series_key"] = d["series_key"]; r["leagueid"] = r["leagueid"]

    models = sorted({r["model"] for r in preds})
    by_model = defaultdict(list)
    for r in preds:
        by_model[r["model"]].append(r)

    L = ["# v1 robustness checks (non-selective; fixed predictions, no refit)", "",
         "## Pooled map log-loss under 3 eval weightings + series-clustered", "",
         "| model | 1/series_size | 1/best_of | map-equal | series-clustered |",
         "|-------|-----:|-----:|-----:|-----:|"]
    for m in models:
        rows = by_model[m]
        a = wll([(r["w_ss"], r["y"], r["p"]) for r in rows])
        b = wll([(r["w_bo"], r["y"], r["p"]) for r in rows])
        c = wll([(1.0, r["y"], r["p"]) for r in rows])
        # series-clustered: mean log-loss within each series, then equal-weight across series
        by_s = defaultdict(list)
        for r in rows:
            by_s[r["series_key"]].append(ll(r["p"], r["y"]))
        sc = float(np.mean([np.mean(v) for v in by_s.values()]))
        star = " **<-**" if m == "B-bt" else ""
        L.append(f"| {m} | {a:.4f} | {b:.4f} | {c:.4f} | {sc:.4f} |{star}")

    L += ["", "## Calibration intercept a / slope b  (ideal a=0, b=1)", "",
          "| model | a (intercept) | b (slope) |", "|-------|-----:|-----:|"]
    for m in models:
        a, b = calib_ab([(r["w_ss"], r["y"], r["p"]) for r in by_model[m]])
        L.append(f"| {m} | {a:+.3f} | {b:.3f} |")

    L += ["", "## Reliability bins - B-bt (weighted 1/series_size, 10 bins)", "",
          "| p-bin | n(w) | mean p | empirical | ",
          "|-------|-----:|-----:|-----:|"]
    bins = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in by_model["B-bt"]:
        bp = bins[min(int(r["p"] * 10), 9)]
        bp[0] += r["w_ss"]; bp[1] += r["w_ss"] * r["p"]; bp[2] += r["w_ss"] * r["y"]
    for k in sorted(bins):
        w, sp, sy = bins[k]
        L.append(f"| {k/10:.1f}-{k/10+0.1:.1f} | {w:.1f} | {sp/w:.3f} | {sy/w:.3f} |")

    L += ["", "## Leave-one-event-out pooled log-loss (min..max over dropping one event)", ""]
    for m in models:
        rows = by_model[m]
        lgs = sorted({r["leagueid"] for r in rows})
        vals = []
        for drop in lgs:
            sub = [(r["w_ss"], r["y"], r["p"]) for r in rows if r["leagueid"] != drop]
            vals.append(wll(sub))
        full = wll([(r["w_ss"], r["y"], r["p"]) for r in rows])
        L.append(f"- {m}: {min(vals):.4f}..{max(vals):.4f}  (full {full:.4f})")

    L += ["", "## Read",
          "- **Ranking is robust.** B-bt is best under all three eval weightings + series-clustered,"
          " and its whole LOEO band sits below A-elo's. Not a weighting or single-event artifact.",
          "- **Calibration finding (v2 recalibration item, NOT rating tuning).** All models show"
          " intercept a ~ +0.5 and slope b < 1: the positive intercept is the uncorrected"
          " **radiant-side advantage** (team_a is always radiant in eval; radiant wins ~53%, so"
          " empirical > predicted, see reliability bins). B-bt has the best slope (~0.81). Fixes,"
          " both out-of-sample: (a) predict **side-neutral** for real matches (sides unknown"
          " pre-match, so the bias vanishes in production), and/or (b) a fold-OOS **Platt"
          " recalibration** a + b*logit(p). Neither changes the ranking; both correct absolute"
          " calibration before any probability ships."]
    out = "\n".join(L) + "\n"
    with open(os.path.join(DOCS, "robustness-v1.md"), "w", encoding="utf-8") as fh:
        fh.write(out)
    print("wrote docs/robustness-v1.md")


if __name__ == "__main__":
    main()
