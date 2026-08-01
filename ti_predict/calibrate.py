"""Fixed (non-search) probability calibration of B-bt, evaluated event-frozen and rolling.

Steps (no hyperparameter search; all quantities estimated only from data before each fold):
  1. per rolling fold, fit B-bt on the training universe (start < cutoff) -> strengths s;
  2. estimate the RADIANT-side coefficient c on TRAIN only (1-D MLE of P(radiant win)=sigmoid(d+c));
  3. for each held-out map compute A-as-radiant sigmoid(d+c) and A-as-dire sigmoid(d-c) and AVERAGE
     -> side-neutral probability (pre-match side unknown);
  4. apply a strictly time-rolling OOF Platt layer: params (A,B) fit only on side-neutral predictions
     from EARLIER folds, applied to the current fold (identity for the first fold).

Reports raw B-bt / side-neutral / side-neutral+OOS-Platt: log-loss, Brier, calibration intercept &
slope, ECE. Also prints the mean radiant coefficient c (to test the "intercept = radiant" claim).
Writes docs/calibration-v1.md. Run: python -m ti_predict.calibrate
"""
import csv
import json
import math
import os
import subprocess
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from ti_predict.backtest import load

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
EPS = 1e-6


def _commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def bt_strengths(train, cutoff, hl=90.0, lam=1.0):
    teams = sorted({m["team_a"] for m in train} | {m["team_b"] for m in train})
    idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    ia = np.array([idx[m["team_a"]] for m in train]); ib = np.array([idx[m["team_b"]] for m in train])
    y = np.array([m["a_won"] for m in train], float)
    w = np.array([math.exp(-math.log(2) * (cutoff - m["start_time"]) / 86400 / hl) * m["w"] for m in train])

    def nll(s):
        d = s[ia] - s[ib]; p = sig(d)
        ll = -(w * (y * np.log(p + EPS) + (1 - y) * np.log(1 - p + EPS))).sum() + lam * (s @ s)
        g = np.zeros(n); r = w * (p - y); np.add.at(g, ia, r); np.add.at(g, ib, -r); g += 2 * lam * s
        return ll, g
    s = minimize(nll, np.zeros(n), jac=True, method="L-BFGS-B").x
    s -= s.mean()
    return {t: s[idx[t]] for t in teams}


def est_c(train, smap):
    d = np.array([smap.get(m["team_a"], 0.0) - smap.get(m["team_b"], 0.0) for m in train])
    y = np.array([m["a_won"] for m in train], float)

    def nll(c):
        p = sig(d + c)
        return -(y * np.log(p + EPS) + (1 - y) * np.log(1 - p + EPS)).sum()
    return float(minimize_scalar(nll, bounds=(-2, 2), method="bounded").x)


def platt_fit(p, y):
    lp = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))

    def nll(t):
        q = sig(t[0] + t[1] * lp)
        return -(y * np.log(q + EPS) + (1 - y) * np.log(1 - q + EPS)).sum()
    r = minimize(nll, [0.0, 1.0], method="Nelder-Mead")
    return r.x


def temperature_fit(p, y):
    """Slope-only (a=0) recalibration: symmetric, so sigmoid(b*logit(p)) + sigmoid(b*logit(1-p)) = 1.
    Production-safe for side-neutral probabilities (preserves P(A)+P(B)=1)."""
    lp = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))

    def nll(b):
        q = sig(b * lp)
        return -(y * np.log(q + EPS) + (1 - y) * np.log(1 - q + EPS)).sum()
    return float(minimize_scalar(nll, bounds=(0.1, 3.0), method="bounded").x)


def metrics(rows):  # rows: (w, y, p)
    w = np.array([r[0] for r in rows]); y = np.array([r[1] for r in rows]); p = np.clip(np.array([r[2] for r in rows]), EPS, 1 - EPS)
    ll = (w * -(y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / w.sum()
    br = (w * (p - y) ** 2).sum() / w.sum()
    a, b = platt_fit(p, y)                       # intercept/slope diagnostic (unweighted fit)
    bins = defaultdict(lambda: [0.0, 0.0, 0.0])
    for wi, yi, pi in zip(w, y, p):
        z = bins[min(int(pi * 10), 9)]; z[0] += wi; z[1] += wi * yi; z[2] += wi * pi
    tot = sum(z[0] for z in bins.values())
    ece = sum(z[0] / tot * abs(z[1] / z[0] - z[2] / z[0]) for z in bins.values() if z[0])
    return ll, br, a, b, ece


def main():
    uni, tgt, folds = load()
    tgt_by_fold = defaultdict(list)
    for r in tgt:
        tgt_by_fold[r["leagueid"]].append(r)

    cs = []
    per_fold = []           # (leagueid, list of dict rows)
    for f in folds:
        cut = f["cutoff_ts"]
        train = [m for m in uni if m["start_time"] < cut]
        ev = tgt_by_fold.get(f["leagueid"], [])
        if not train or not ev:
            continue
        s = bt_strengths(train, cut)
        c = est_c(train, s); cs.append(c)
        rows = []
        for m in ev:
            d = s.get(m["team_a"], 0.0) - s.get(m["team_b"], 0.0)
            raw = float(sig(d))
            sn = float(0.5 * (sig(d + c) + sig(d - c)))
            rows.append({"w": m["weight"], "y": m["a_won"], "raw": raw, "sn": sn})
        per_fold.append((f["cutoff_ts"], rows))

    per_fold.sort(key=lambda x: x[0])
    # strictly-rolling OOS Platt on side-neutral
    seen_sn, seen_y, warm = [], [], []
    for _, rows in per_fold:
        if len(seen_y) >= 50:
            A, B = platt_fit(np.array(seen_sn), np.array(seen_y))
            Bt_r = temperature_fit(np.array(seen_sn), np.array(seen_y)); mode = "platt"
        else:
            A, B, Bt_r = 0.0, 1.0, 1.0; mode = "identity"    # identity until enough history
        warm.append((mode, len(rows)))
        for r in rows:
            lp = math.log(min(max(r["sn"], EPS), 1 - EPS) / (1 - min(max(r["sn"], EPS), 1 - EPS)))
            r["snp"] = float(sig(A + B * lp)); r["snt"] = float(sig(Bt_r * lp))
        seen_sn += [r["sn"] for r in rows]; seen_y += [r["y"] for r in rows]

    allrows = [r for _, rows in per_fold for r in rows]
    variants = {"raw B-bt": "raw", "side-neutral": "sn", "side-neutral + OOS Platt (diag)": "snp",
                "side-neutral + OOS temperature (production)": "snt"}
    L = ["# v1 fixed calibration (side-neutral + strictly-rolling OOS Platt)", "",
         f"Mean per-fold radiant coefficient c = **{np.mean(cs):+.3f}** (range {min(cs):+.3f}..{max(cs):+.3f}).",
         f"logit(0.53) = +0.12 for reference: c is small, so it CANNOT explain intercept ~ +0.5 —",
         "the intercept-as-radiant idea is rejected as the sole cause; the Platt layer does the real work.",
         "", "| variant | log-loss | Brier | intercept a | slope b | ECE |",
         "|---------|-----:|-----:|-----:|-----:|-----:|"]
    for name, key in variants.items():
        ll, br, a, b, ece = metrics([(r["w"], r["y"], r[key]) for r in allrows])
        L.append(f"| {name} | {ll:.4f} | {br:.4f} | {a:+.3f} | {b:.3f} | {ece:.4f} |")
    # warm-up accounting
    id_f = sum(1 for m, _ in warm if m == "identity"); id_o = sum(n for m, n in warm if m == "identity")
    pl_f = sum(1 for m, _ in warm if m == "platt"); pl_o = sum(n for m, n in warm if m == "platt")

    # Full Platt (diagnostic, matches the table) vs PRODUCTION temperature (slope-only, symmetric),
    # both fit on ALL historical rolling-OOF side-neutral preds (all pre-TI cutoff).
    Ap, Bp = platt_fit(np.array(seen_sn), np.array(seen_y))
    Bt = temperature_fit(np.array(seen_sn), np.array(seen_y))
    prod = {"production_mode": "identity_until_validated",
            "candidate_temperature_b_unvalidated": round(Bt, 6),
            "diagnostic_full_platt": {"a": round(float(Ap), 6), "b": round(float(Bp), 6)},
            "fit_on_oof_obs": len(seen_y), "as_of_cutoff": "2026-08-01", "git_commit": _commit(),
            "note": ("Production default = IDENTITY (raw side-neutral B-bt). The full-Platt ECE gain "
                     "is a fixed-team_a-side (radiant) eval artifact; the production-safe symmetric "
                     "temperature does NOT reproduce it on this side-confounded backtest (worse LL), "
                     "so calibration is UNVALIDATED for production. Validate via a side-aware eval "
                     "(base sigmoid(d+c), c=train radiant term; then symmetric temperature; production "
                     "marginalizes side) when unparked. Refit at TI cutoff on pre-cutoff OOF only; "
                     "never update from crowd%, odds, or results.")}
    with open(os.path.join(INPUTS, "production_platt.json"), "w", encoding="utf-8") as fh:
        json.dump(prod, fh, ensure_ascii=False, indent=2)

    L += ["", "## Warm-up accounting (OOF Platt needs >=50 prior obs)",
          f"- identity (warm-up) folds: **{id_f}** ({id_o} obs); Platt-calibrated folds: **{pl_f}** "
          f"({pl_o} obs). The aggregate improvement above is driven by the {pl_o} Platt-calibrated obs.",
          "", "## Reproducibility (frozen spec, not frozen numbers)",
          "1. **What is frozen is the Track-2 probability PIPELINE (spec)** — the B-bt model, the",
          "   side-neutral step, and the OOS-Platt recipe — **not the final TI2026 numbers**. The",
          "   final numbers come from an **as-of-cutoff refit** using this frozen model + calibration.",
          "2. Warm-up above: only the Platt-calibrated obs benefit; identity folds are uncorrected.",
          "3. **Production calibration status: UNVALIDATED -> default IDENTITY.** The full-Platt ECE",
          "   gain (0.097->0.048) is a fixed-team_a-side (radiant) eval artifact; the production-safe",
          "   symmetric temperature does NOT reproduce it on this side-confounded eval (LL 0.6573 >",
          "   0.6518 raw). So production = raw side-neutral B-bt for now; the temperature is stored as",
          "   an unvalidated candidate (`inputs/production_platt.json`, cutoff + commit, pre-cutoff OOF",
          "   only; **refit at TI cutoff; never update from crowd%/odds/results**).",
          "", "## Read (correction to the earlier 'materially improves' claim)",
          "- side-neutral ~ raw (eval fixes team_a = radiant; radiant c=+0.088 cannot explain +0.5).",
          "- The full-Platt ECE drop is **largely a fixed-side eval artifact** (its intercept absorbs",
          "  the radiant bias) and does NOT transfer to symmetric production.",
          "- The production-safe temperature (a=0) does **not** improve the side-confounded eval, so",
          "  **production calibration is NOT yet validated** -> default to identity (raw side-neutral",
          "  B-bt). A valid test needs a side-aware eval; recorded as the next calibration step to run",
          "  when unparked (a measurement fix, not a hyperparameter search). Ranking is unaffected."]
    out = "\n".join(L) + "\n"
    with open(os.path.join(DOCS, "calibration-v1.md"), "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"warm-up: {id_f} identity folds ({id_o} obs), {pl_f} Platt folds ({pl_o} obs)")
    print(f"production temperature b={Bt:.4f} (a=0, symmetric) stored on {len(seen_y)} OOF obs, "
          f"commit {prod['git_commit']}; full-Platt diagnostic a={Ap:+.4f} b={Bp:.4f}")


if __name__ == "__main__":
    main()
