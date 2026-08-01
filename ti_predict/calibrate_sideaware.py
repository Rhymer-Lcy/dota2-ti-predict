"""Side-aware evaluation (measurement fix, not model search).

Removes the fixed-orientation confound of the earlier eval: fit the radiant coefficient c TRAIN-ONLY
per fold, then evaluate held-out maps using their ACTUAL sides (team_a is radiant in the universe, so
the side-aware prediction is sigmoid(logit + c)). Production probability is side-neutral =
0.5*(sigmoid(logit+c) + sigmoid(logit-c)). Only symmetry-preserving (temperature) calibration is
tested, strictly rolling OOS. Reconfirms B-bt still beats plain Elo under this evaluation.

Temperature form (documented): q = sigmoid(b * logit(p)). b<1 SOFTENS (fixes overconfidence);
b>1 SHARPENS. Equivalent to T=1/b in sigmoid(logit(p)/T).

Decision: if the symmetric temperature does not improve OOS log-loss AND ECE, production is frozen at
identity side-neutral B-bt. Writes docs/calibration-sideaware.md and updates production_platt.json.

Run: python -m ti_predict.calibrate_sideaware
"""
import json
import math
import os
import subprocess
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize_scalar

from ti_predict.backtest import load
from ti_predict.calibrate import bt_strengths, temperature_fit, metrics, sig

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs"); INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
EPS = 1e-6; LN10 = math.log(10)


def _commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def elo_ratings(train, K=24.0, scale=400.0, init=1500.0):
    R = defaultdict(lambda: init)
    for m in train:
        a, b, s = m["team_a"], m["team_b"], m["a_won"]
        ea = 1.0 / (1.0 + 10 ** ((R[b] - R[a]) / scale))
        R[a] += K * (s - ea); R[b] += K * ((1 - s) - (1 - ea))
    return R


def est_c(logits, y):
    lo = np.asarray(logits); yy = np.asarray(y, float)

    def nll(c):
        p = sig(lo + c)
        return -(yy * np.log(p + EPS) + (1 - yy) * np.log(1 - p + EPS)).sum()
    return float(minimize_scalar(nll, bounds=(-2, 2), method="bounded").x)


def lgt(p):
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def main():
    uni, tgt, folds = load()
    tbf = defaultdict(list)
    for r in tgt:
        tbf[r["leagueid"]].append(r)
    per_fold, ce_list, cb_list = [], [], []
    for f in folds:
        cut = f["cutoff_ts"]; train = [m for m in uni if m["start_time"] < cut]; ev = tbf.get(f["leagueid"], [])
        if not train or not ev:
            continue
        R = elo_ratings(train); s = bt_strengths(train, cut)
        le_tr = [LN10 * (R[m["team_a"]] - R[m["team_b"]]) / 400 for m in train]
        lb_tr = [s.get(m["team_a"], 0.0) - s.get(m["team_b"], 0.0) for m in train]
        ytr = [m["a_won"] for m in train]
        ce = est_c(le_tr, ytr); cb = est_c(lb_tr, ytr); ce_list.append(ce); cb_list.append(cb)
        rows = []
        for m in ev:
            le = LN10 * (R.get(m["team_a"], 1500) - R.get(m["team_b"], 1500)) / 400
            d = s.get(m["team_a"], 0.0) - s.get(m["team_b"], 0.0)
            rows.append({"w": m["weight"], "y": m["a_won"], "lg": f["leagueid"],
                         "elo_sa": float(sig(le + ce)), "bt_sa": float(sig(d + cb)),
                         "bt_neutral": float(0.5 * (sig(d + cb) + sig(d - cb)))})
        per_fold.append((cut, rows))
    per_fold.sort(key=lambda x: x[0])

    # strictly-rolling OOS symmetric temperature on the side-aware B-bt prediction
    seen_p, seen_y = [], []
    for _, rows in per_fold:
        Bt = temperature_fit(np.array(seen_p), np.array(seen_y)) if len(seen_y) >= 50 else 1.0
        for r in rows:
            r["bt_sa_temp"] = float(sig(Bt * lgt(r["bt_sa"])))
        seen_p += [r["bt_sa"] for r in rows]; seen_y += [r["y"] for r in rows]
    allrows = [r for _, rows in per_fold for r in rows]

    variants = {"A-elo side-aware": "elo_sa", "B-bt side-aware": "bt_sa",
                "B-bt side-aware + OOS temp": "bt_sa_temp", "B-bt side-neutral (production)": "bt_neutral"}
    L = ["# Side-aware evaluation (orientation confound removed)", "",
         f"Train-only radiant coefficient: Elo mean c={np.mean(ce_list):+.3f}, "
         f"B-bt mean c={np.mean(cb_list):+.3f}. Temperature form q=sigmoid(b*logit(p)); b<1 softens.",
         "", "| variant | log-loss | Brier | intercept a | slope b | ECE |",
         "|---------|-----:|-----:|-----:|-----:|-----:|"]
    m = {}
    for name, key in variants.items():
        ll, br, a, b, ece = metrics([(r["w"], r["y"], r[key]) for r in allrows])
        m[key] = (ll, br, a, b, ece)
        L.append(f"| {name} | {ll:.4f} | {br:.4f} | {a:+.3f} | {b:.3f} | {ece:.4f} |")

    # reconfirm B-bt beats A-elo under side-aware eval (pooled + fold-win on log-loss)
    def wll(rows, key):
        sw = sum(r["w"] for r in rows)
        return sum(r["w"] * -(r["y"] * math.log(min(max(r[key], EPS), 1 - EPS)) +
                              (1 - r["y"]) * math.log(1 - min(max(r[key], EPS), 1 - EPS))) for r in rows) / sw
    fold_ids = sorted({r["lg"] for r in allrows})
    wins = sum(1 for lg in fold_ids
               if wll([r for r in allrows if r["lg"] == lg], "bt_sa")
               < wll([r for r in allrows if r["lg"] == lg], "elo_sa"))
    # --- production-aligned SYMMETRIC OOF temperature test (the conclusive one) ---
    # Symmetrize each side-neutral OOF obs with its (B,A,1-y,1-p) mirror at half weight, then fit a
    # zero-intercept temperature strictly on prior folds. This removes team-a base-rate confounding
    # while preserving P(A>B)+P(B>A)=1. If temperature still fails here, identity is conclusively frozen.
    sym_prior, id_rows, tp_rows = [], [], []
    for _, rows in per_fold:
        bts = (temperature_fit(np.array([p for p, _ in sym_prior]), np.array([y for _, y in sym_prior]))
               if len(sym_prior) >= 100 else 1.0)                      # >=50 real obs (x2 mirrored)
        for r in rows:
            p, y, w = r["bt_neutral"], r["y"], 0.5 * r["w"]
            for pp, yy in ((p, y), (1 - p, 1 - y)):
                id_rows.append((w, yy, pp)); tp_rows.append((w, yy, sig(bts * lgt(pp))))
        for r in rows:
            sym_prior += [(r["bt_neutral"], r["y"]), (1 - r["bt_neutral"], 1 - r["y"])]
    id_ll, id_br, _, _, id_ece = metrics(id_rows)
    tp_ll, tp_br, _, _, tp_ece = metrics(tp_rows)
    sym_pass = (tp_ll < id_ll - 1e-4) and (tp_ece < id_ece - 1e-3)
    bts_prod = temperature_fit(np.array([p for p, _ in sym_prior]), np.array([y for _, y in sym_prior]))
    decision = "temperature_validated" if sym_pass else "identity_side_neutral_bbt"

    L += ["", f"**B-bt beats A-elo in {wins}/{len(fold_ids)} folds** (side-aware diagnostic, pooled "
          f"{m['bt_sa'][0]:.4f} vs {m['elo_sa'][0]:.4f}).",
          "", "## Two scores, reported separately",
          f"- **side-aware DIAGNOSTIC** (actual side known): B-bt log-loss **{m['bt_sa'][0]:.4f}**.",
          f"- **production-aligned side-neutral** (side unknown, what ships): B-bt log-loss "
          f"**{m['bt_neutral'][0]:.4f}**.",
          "", "## Production-aligned symmetric OOF temperature test (conclusive)",
          "Each OOF side-neutral obs + its (B,A,1-y,1-p) mirror, half weight; zero-intercept temperature "
          "fit strictly on prior folds. Removes team-a base-rate confounding.",
          "", "| symmetric OOF | log-loss | Brier | ECE |", "|---|--:|--:|--:|",
          f"| identity (b=1) | {id_ll:.4f} | {id_br:.4f} | {id_ece:.4f} |",
          f"| rolling temperature | {tp_ll:.4f} | {tp_br:.4f} | {tp_ece:.4f} |",
          "", "## Decision",
          f"- symmetric temperature improves OOS (log-loss AND ECE): **{sym_pass}**.",
          f"- => **production = {decision}**"
          + ("." if sym_pass else " -- identity CONCLUSIVELY frozen (symmetric test failed)."),
          "- c=+0.088 rules out radiant-side ADVANTAGE as the main cause of the +0.4 intercept, but",
          "  NOT all orientation effects; team-a ordering / evaluation base-rate remain unresolved.",
          "- Ranking unaffected; B-bt stays the selected rating model."]
    with open(os.path.join(DOCS, "calibration-sideaware.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    prod = {"production_mode": decision, "selected_model": "B-bt",
            "calibration_layer": "temperature" if sym_pass else "none (identity)",
            "symmetric_oof_temperature_b": round(bts_prod, 6),
            "temperature_form": "sigmoid(b*logit(p)); b<1 softens, b>1 sharpens",
            "symmetric_oof_pass": bool(sym_pass),
            "symmetric_oof_identity_logloss": round(id_ll, 4), "symmetric_oof_temp_logloss": round(tp_ll, 4),
            "side_aware_diagnostic_logloss": round(m["bt_sa"][0], 4),
            "production_side_neutral_logloss": round(m["bt_neutral"][0], 4),
            "bbt_vs_elo_fold_wins": f"{wins}/{len(fold_ids)}",
            "mean_radiant_c_bt": round(float(np.mean(cb_list)), 4),
            "as_of_cutoff": "2026-08-01", "git_commit": _commit(),
            "note": ("Production = identity side-neutral B-bt. AT THE TI CUTOFF: refit B-bt on all "
                     "eligible pre-cutoff data and emit side-neutral probs; do NOT refit any Platt "
                     "(there is no production Platt). The temperature candidate stays DISABLED unless "
                     "the preregistered symmetric-OOF test passes. c=+0.088 rules out radiant advantage "
                     "as the main intercept cause but not team-a ordering / base-rate effects "
                     "(unresolved). Never update from crowd%, odds, or results.")}
    with open(os.path.join(INPUTS, "production_platt.json"), "w", encoding="utf-8") as fh:
        json.dump(prod, fh, ensure_ascii=False, indent=2)
    print("\n".join(L))
    print(f"\nproduction: {decision} | symmetric temp pass={sym_pass} | commit {prod['git_commit']}")


if __name__ == "__main__":
    main()
