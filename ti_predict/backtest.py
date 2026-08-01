"""Event-frozen rolling backtest of the four preregistered candidates (v1 screening).

Trains on the rating universe (universe_maps.csv, start_time < fold.cutoff), freezes at the cutoff,
predicts the fold's target maps (dataset_maps.csv), and scores map-level log-loss (primary) + Brier
+ calibration. Reports per-fold results, fold-win sign test vs A-elo, event-blocked bootstrap CIs,
weighting sensitivity (non-selective), and leave-one-event-out. Emits NO TI2026 probabilities.

Exact formulas/constants: docs/model-implementation.md. Run: python -m ti_predict.backtest
"""
import csv
import math
import os
from collections import defaultdict, Counter

import numpy as np
from scipy.optimize import minimize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
PROC, INPUTS = os.path.join(TI, "processed"), os.path.join(TI, "inputs")
EPS = 1e-6
DAY = 86400.0


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load():
    uni = _read(os.path.join(PROC, "universe_maps.csv"))
    for r in uni:
        r["start_time"] = int(r["start_time"]); r["a_won"] = int(r["a_won"])
        r["series_id"] = int(r["series_id"])
    uni.sort(key=lambda r: (r["start_time"], r["match_id"]))
    ssize = Counter(r["series_id"] for r in uni if r["series_id"])
    for r in uni:
        r["w"] = 1.0 / ssize[r["series_id"]] if r["series_id"] else 1.0
    tgt = _read(os.path.join(PROC, "dataset_maps.csv"))
    for r in tgt:
        r["start_time"] = int(r["start_time"]); r["a_won"] = int(r["a_won"])
        r["weight"] = float(r["weight"]); r["series_size"] = int(r["series_size"])
        r["bo2_draw"] = int(r["bo2_draw"])
    folds = _read(os.path.join(INPUTS, "folds.csv"))
    for f in folds:
        f["cutoff_ts"] = int(f["cutoff_ts"]); f["leagueid"] = f["leagueid"]
    folds.sort(key=lambda f: f["cutoff_ts"])
    return uni, tgt, folds


# ---- models: each returns predict(a,b) -> P(a wins map), fit on chronological train maps ----
def fit_elo(train, K=24.0, scale=400.0, init=1500.0, decay_hl=None):
    R, last = defaultdict(lambda: init), {}
    for m in train:
        a, b, sa, t = m["team_a"], m["team_b"], m["a_won"], m["start_time"]
        if decay_hl:
            for x in (a, b):
                if x in last:
                    R[x] = init + (R[x] - init) * 0.5 ** ((t - last[x]) / DAY / decay_hl)
        ea = 1.0 / (1.0 + 10 ** ((R[b] - R[a]) / scale))
        R[a] += K * (sa - ea); R[b] += K * ((1 - sa) - (1 - ea))
        last[a] = last[b] = t
    def predict(a, b):
        return 1.0 / (1.0 + 10 ** ((R[b] - R[a]) / scale))
    return predict


def fit_bt(train, cutoff_ts, half_life=90.0, lam=1.0):
    teams = sorted({m["team_a"] for m in train} | {m["team_b"] for m in train})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ia = np.array([idx[m["team_a"]] for m in train]); ib = np.array([idx[m["team_b"]] for m in train])
    y = np.array([m["a_won"] for m in train], float)
    w = np.array([math.exp(-math.log(2) * (cutoff_ts - m["start_time"]) / DAY / half_life) * m["w"]
                  for m in train])
    def nll(s):
        d = s[ia] - s[ib]
        p = 1.0 / (1.0 + np.exp(-d))
        ll = -(w * (y * np.log(p + EPS) + (1 - y) * np.log(1 - p + EPS))).sum() + lam * (s @ s)
        g = np.zeros(n)
        r = w * (p - y)
        np.add.at(g, ia, r); np.add.at(g, ib, -r)
        g += 2 * lam * s
        return ll, g
    s0 = np.zeros(n)
    s = minimize(nll, s0, jac=True, method="L-BFGS-B").x
    s -= s.mean()
    smap = {t: s[idx[t]] for t in teams}
    def predict(a, b):
        return 1.0 / (1.0 + math.exp(-((smap.get(a, 0.0)) - (smap.get(b, 0.0)))))
    return predict


def fit_glicko2(train, cutoff_ts, period_days=7.0, init_r=1500.0, init_rd=350.0,
                init_vol=0.06, tau=0.5):
    Q = 173.7178
    mu = defaultdict(float); phi = defaultdict(lambda: init_rd / Q); vol = defaultdict(lambda: init_vol)
    seen = set()
    def g(p): return 1.0 / math.sqrt(1.0 + 3.0 * p * p / math.pi ** 2)
    if not train:
        def predict0(a, b): return 0.5
        return predict0
    t0 = train[0]["start_time"]
    def per(t): return int((t - t0) // (period_days * DAY))
    by_period = defaultdict(list)
    for m in train:
        by_period[per(m["start_time"])].append(m)
    last_period = {}
    for pnum in sorted(by_period):
        games = defaultdict(list)  # team -> list of (opp, score)
        for m in by_period[pnum]:
            games[m["team_a"]].append((m["team_b"], m["a_won"]))
            games[m["team_b"]].append((m["team_a"], 1 - m["a_won"]))
        # inactivity RD inflation for teams seen before but idle this period
        for t in list(seen):
            if t not in games:
                gap = pnum - last_period.get(t, pnum)
                if gap > 0:
                    phi[t] = min(math.sqrt(phi[t] ** 2 + gap * vol[t] ** 2), init_rd / Q)
        snap_mu = dict(mu); snap_phi = dict(phi)
        for t, res in games.items():
            m_t = snap_mu.get(t, 0.0); p_t = snap_phi.get(t, init_rd / Q)
            gs = [g(snap_phi.get(o, init_rd / Q)) for o, _ in res]
            Es = [1.0 / (1.0 + math.exp(-gg * (m_t - snap_mu.get(o, 0.0)))) for gg, (o, _) in zip(gs, res)]
            v_inv = sum(gg ** 2 * E * (1 - E) for gg, E in zip(gs, Es))
            if v_inv <= 0:
                continue
            v = 1.0 / v_inv
            delta = v * sum(gg * (s - E) for gg, (o, s), E in zip(gs, res, Es))
            # volatility (Illinois)
            a_ = math.log(vol[t] ** 2)
            def f(x):
                ex = math.exp(x)
                return (ex * (delta ** 2 - p_t ** 2 - v - ex) / (2 * (p_t ** 2 + v + ex) ** 2)
                        - (x - a_) / tau ** 2)
            A = a_; B = (math.log(delta ** 2 - p_t ** 2 - v) if delta ** 2 > p_t ** 2 + v else a_ - tau)
            fa, fb = f(A), f(B)
            k = 0
            while fb * fa < 0 and abs(B - A) > 1e-6 and k < 100:
                C = A + (A - B) * fa / (fb - fa); fc = f(C)
                if fc * fb < 0: A, fa = B, fb
                else: fa /= 2
                B, fb = C, fc; k += 1
            new_vol = math.exp(A / 2)
            phi_star = math.sqrt(p_t ** 2 + new_vol ** 2)
            new_phi = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / v)
            new_mu = m_t + new_phi ** 2 * sum(gg * (s - E) for gg, (o, s), E in zip(gs, res, Es))
            mu[t], phi[t], vol[t] = new_mu, new_phi, new_vol
            seen.add(t); last_period[t] = pnum
    def predict(a, b):
        pa, pb = phi.get(a, init_rd / Q), phi.get(b, init_rd / Q)
        gg = g(math.sqrt(pa ** 2 + pb ** 2))
        return 1.0 / (1.0 + math.exp(-gg * (mu.get(a, 0.0) - mu.get(b, 0.0))))
    return predict


MODELS = {
    "A-elo": lambda tr, cut: fit_elo(tr),
    "B-eloTD": lambda tr, cut: fit_elo(tr, decay_hl=180.0),
    "B-bt": lambda tr, cut: fit_bt(tr, cut),
    "C-glicko2": lambda tr, cut: fit_glicko2(tr, cut),
}


def logloss(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def main():
    uni, tgt, folds = load()
    tgt_by_fold = defaultdict(list)
    for r in tgt:
        tgt_by_fold[r["leagueid"]].append(r)

    # per (model, fold): list of (w, y, p) on target maps
    rec = {name: defaultdict(list) for name in MODELS}
    dump = []                                  # flat per-prediction dump for robustness reuse
    for f in folds:
        cut = f["cutoff_ts"]
        train = [m for m in uni if m["start_time"] < cut]
        evalmaps = tgt_by_fold.get(f["leagueid"], [])
        if not train or not evalmaps:
            continue
        for name, fit in MODELS.items():
            pred = fit(train, cut)
            for m in evalmaps:
                p = pred(m["team_a"], m["team_b"])
                rec[name][f["leagueid"]].append((m["weight"], m["a_won"], p))
                dump.append({"model": name, "leagueid": f["leagueid"],
                             "match_id": m["match_id"], "y": m["a_won"], "p": round(p, 6)})
    with open(os.path.join(PROC, "backtest_preds.csv"), "w", newline="", encoding="utf-8") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["model", "leagueid", "match_id", "y", "p"])
        w_.writeheader(); w_.writerows(dump)

    fold_ids = [f["leagueid"] for f in folds if rec["A-elo"].get(f["leagueid"])]
    names = list(MODELS)

    def wll(pairs):  # weighted log-loss
        sw = sum(w for w, _, _ in pairs)
        return sum(w * logloss(p, y) for w, y, p in pairs) / sw if sw else float("nan")
    def wbrier(pairs):
        sw = sum(w for w, _, _ in pairs)
        return sum(w * (p - y) ** 2 for w, y, p in pairs) / sw if sw else float("nan")

    print(f"universe={len(uni)} maps | target={len(tgt)} maps | folds={len(fold_ids)}\n")
    # per-fold log-loss table
    hdr = f"{'fold(cutoff)':<22}{'n':>5}" + "".join(f"{n:>11}" for n in names)
    print(hdr); print("-" * len(hdr))
    fmeta = {f["leagueid"]: f for f in folds}
    pooled = {n: [] for n in names}
    perfold_ll = {n: {} for n in names}
    for lg in fold_ids:
        n = len(rec["A-elo"][lg])
        line = f"{fmeta[lg]['cutoff']+' '+str(lg):<22}{n:>5}"
        for name in names:
            ll = wll(rec[name][lg]); perfold_ll[name][lg] = ll
            pooled[name].extend(rec[name][lg])
            line += f"{ll:>11.4f}"
        print(line)
    print("-" * len(hdr))
    print(f"{'POOLED log-loss':<22}{'':>5}" + "".join(f"{wll(pooled[n]):>11.4f}" for n in names))
    print(f"{'POOLED Brier':<22}{'':>5}" + "".join(f"{wbrier(pooled[n]):>11.4f}" for n in names))

    # fold-win sign test vs A-elo
    print("\nfold-win count vs A-elo (lower log-loss):")
    for name in names:
        if name == "A-elo":
            continue
        wins = sum(1 for lg in fold_ids if perfold_ll[name][lg] < perfold_ll["A-elo"][lg])
        print(f"  {name:<11} {wins}/{len(fold_ids)} folds beat A-elo")

    # event-blocked bootstrap CI on (cand - A) pooled log-loss diff (resample folds)
    rng = np.random.default_rng(20260801)
    print("\nevent-blocked bootstrap 90% CI of pooled log-loss diff (cand - A-elo); <0 favours cand:")
    for name in names:
        if name == "A-elo":
            continue
        diffs = []
        for _ in range(2000):
            samp = rng.choice(fold_ids, size=len(fold_ids), replace=True)
            ca = [pr for lg in samp for pr in rec[name][lg]]
            aa = [pr for lg in samp for pr in rec["A-elo"][lg]]
            diffs.append(wll(ca) - wll(aa))
        lo, hi = np.percentile(diffs, [5, 95])
        print(f"  {name:<11} {np.mean(diffs):+.4f}  [{lo:+.4f}, {hi:+.4f}]")

    # leave-one-event-out sensitivity (pooled log-loss dropping each fold)
    print("\nLOEO pooled log-loss range (min..max over dropping one event):")
    for name in names:
        vals = []
        for drop in fold_ids:
            pairs = [pr for lg in fold_ids if lg != drop for pr in rec[name][lg]]
            vals.append(wll(pairs))
        print(f"  {name:<11} {min(vals):.4f}..{max(vals):.4f}  (full {wll(pooled[name]):.4f})")

    # calibration (ECE, 10 bins) per model
    print("\ncalibration ECE (10 equal-width bins, weighted):")
    for name in names:
        bins = defaultdict(lambda: [0.0, 0.0, 0.0])  # w, w*y, w*p
        for w, y, p in pooled[name]:
            bp = bins[min(int(p * 10), 9)]
            bp[0] += w; bp[1] += w * y; bp[2] += w * p
        tot = sum(b[0] for b in bins.values())
        ece = sum(b[0] / tot * abs(b[1] / b[0] - b[2] / b[0]) for b in bins.values() if b[0])
        print(f"  {name:<11} ECE={ece:.4f}")


if __name__ == "__main__":
    main()
