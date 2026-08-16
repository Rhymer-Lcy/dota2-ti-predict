"""Does assimilating a league's earlier results improve prediction of its later results?

This is an AUXILIARY diagnostic for the frozen sequential-update procedure. It is deliberately NOT a
group/Swiss-to-playoff replay, and nothing here may be reported as one.

Why the weaker claim is the only honest one: the rating universe carries `leagueid` and timestamps
and NO stage field. There is no local record of which series belonged to a group phase and which to
an elimination bracket, and deriving one from series length or team counts would be invention. So
each league is split CHRONOLOGICALLY at a fraction of its own series and the question asked is
exactly the weak one -- given the earlier part of a league, how well is the later part predicted --
with the fraction swept rather than tuned.

That construct is a genuine test of sequential assimilation. It is not evidence about playoff
brackets specifically, and the population makes that plain: the eligible leagues include
season-long leagues running hundreds of series and streamer/exhibition events, neither of which has
a group-to-playoff arc at all. The report therefore carries two populations side by side:

  all                   every league passing the structural minimums (the broad claim);
  preregistered_folds   only the leagues in inputs/folds.csv, i.e. those already carrying
                        preregistered target maps -- discrete tournaments rather than seasons.

and two weightings (map-weight and event-equal), because three high-volume leagues would otherwise
dominate a map-weighted pooled statistic.

Four arms per league, all using the identical frozen B-bt estimator (h90, lambda=1, no calibration):
  A_pre        train = universe before the league's first map;  decay origin = that first map
  B_origin     same training data;                              decay origin = late-phase start
  C_concurrent everything before the late phase EXCEPT this league's own maps
  D_full       everything before the late phase, this league's early maps included  <- frozen update

  A->B isolates the decay origin, B->C other matches played meanwhile, C->D the league's own earlier
  results. D is what the production path does.

Audit-predeclared shrinkage diagnostic (the ONLY thing selectable here):
  s(kappa) = s_C + kappa * (s_D - s_C), kappa in {0.25, 0.50, 0.75, 1.00}; kappa=1.00 is D itself,
  the plain frozen refit, and is the default that wins every tie.

  PROVENANCE, stated exactly: this kappa set was fixed before any arm of THIS auxiliary analysis was
  scored, and no arm was added or dropped afterwards. It is NOT preregistered -- no timestamped
  earlier artifact in this repository registers it, and calling it preregistered would borrow
  credibility from the genuinely preregistered v1 validation, which it has no claim to. (The
  pre-declared ridge-lambda grid in backtest2/results-adversarial.md is a different quantity and is
  not this.) The split fractions below have the same status: fixed before scoring, not preregistered.
  The distinction is load-bearing because kappa=1 wins here, so this diagnostic changes nothing;
  had a kappa<1 won, this weaker provenance would have been a reason NOT to adopt it automatically.

SELECTION RULE for the population, fixed before any arm was scored and referring only to structure,
never to a league's observed outcomes or a model's error on it:
  1. the league must admit a chronological split with a non-empty early and late part;
  2. at least MIN_EARLY_SERIES series in the early part;
  3. at least MIN_EVAL_MAPS late maps whose BOTH teams appeared in the early part;
  4. non-empty pre-league training data (excludes leagues that open the scan window).

Run: python -m ti_predict.sequential_assimilation [--sweep] [--population all|folds] [--json OUT]
"""
import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.backtest import load
from ti_predict.calibrate import bt_strengths, est_c
from ti_predict.contest_rules import PRODUCTION_HALF_LIFE_DAYS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDS_CSV = os.path.join(REPO, "data", "ti2026", "inputs", "folds.csv")
EPS = 1e-6
KAPPAS = (0.25, 0.50, 0.75, 1.00)
MIN_EVAL_MAPS = 10          # a league enters only with this many eligible late maps
MIN_EARLY_SERIES = 6        # ... and this many early series to assimilate
SPLIT_FRACTIONS = (0.4, 0.5, 0.6, 0.7)


def preregistered_folds(path=None):
    """The leagueids already carrying preregistered target maps (inputs/folds.csv)."""
    with open(path or FOLDS_CSV, encoding="utf-8") as fh:
        return {r["leagueid"] for r in csv.DictReader(fh)}


def _sig(x):
    return 1.0 / (1.0 + math.exp(-x))


def _metrics(rows):
    """rows: (w, y, p) -> weighted log-loss, Brier, accuracy."""
    sw = sum(w for w, _, _ in rows)
    ll = sum(w * -(y * math.log(min(max(p, EPS), 1 - EPS))
                   + (1 - y) * math.log(1 - min(max(p, EPS), 1 - EPS)))
             for w, y, p in rows) / sw
    br = sum(w * (p - y) ** 2 for w, y, p in rows) / sw
    acc = sum(w * ((p >= 0.5) == bool(y)) for w, y, p in rows) / sw
    return {"logloss": ll, "brier": br, "accuracy": acc, "n_maps": len(rows), "weight": sw}


def _predict(rows, s, c):
    """Side-aware (the eval knows the side) and raw forms, both from the frozen strengths."""
    aware, raw = [], []
    for m in rows:
        d = s.get(m["team_a"], 0.0) - s.get(m["team_b"], 0.0)
        aware.append((m["w"], m["a_won"], _sig(d + c)))
        raw.append((m["w"], m["a_won"], _sig(d)))
    return aware, raw


def league_split(uni, leagueid, frac):
    """Chronological split of one league's own maps at `frac` of its SERIES (never mid-series)."""
    ev = [m for m in uni if str(m["leagueid"]) == str(leagueid)]
    if not ev:
        return None
    by_series = defaultdict(list)
    for m in ev:
        by_series[m["series_id"] or ("solo", m["match_id"])].append(m)
    keys = sorted(by_series, key=lambda k: min(x["start_time"] for x in by_series[k]))
    cut = max(1, int(round(frac * len(keys))))
    early = [m for k in keys[:cut] for m in by_series[k]]
    late = [m for k in keys[cut:] for m in by_series[k]]
    if not early or not late:
        return None
    seen = {m["team_a"] for m in early} | {m["team_b"] for m in early}
    eligible = [m for m in late if m["team_a"] in seen and m["team_b"] in seen]
    return {"leagueid": str(leagueid), "league_start": min(m["start_time"] for m in ev),
            "late_start": min(m["start_time"] for m in late),
            "n_series": len(keys), "n_early_series": cut, "n_late_series": len(keys) - cut,
            "early": early, "late": late, "eligible": eligible,
            "league_name": ev[0]["league_name"]}


def replay_league(uni, sp):
    """Run the four arms plus the shrinkage family on one league. Returns per-arm metrics."""
    ev_ids = {m["match_id"] for m in uni if str(m["leagueid"]) == sp["leagueid"]}
    tr_pre = [m for m in uni if m["start_time"] < sp["league_start"]]
    tr_full = [m for m in uni if m["start_time"] < sp["late_start"]]
    tr_conc = [m for m in tr_full if m["match_id"] not in ev_ids]
    if not tr_pre or not tr_conc:
        return None
    hl = float(PRODUCTION_HALF_LIFE_DAYS)
    s_pre = bt_strengths(tr_pre, sp["league_start"], hl=hl)
    s_org = bt_strengths(tr_pre, sp["late_start"], hl=hl)
    s_con = bt_strengths(tr_conc, sp["late_start"], hl=hl)
    s_ful = bt_strengths(tr_full, sp["late_start"], hl=hl)
    arms = {"A_pre": (s_pre, tr_pre), "B_origin": (s_org, tr_pre),
            "C_concurrent": (s_con, tr_conc), "D_full": (s_ful, tr_full)}
    for k in KAPPAS:
        if k == 1.00:
            continue
        keys = set(s_con) | set(s_ful)
        arms[f"D_kappa{k:.2f}"] = ({t: s_con.get(t, 0.0) + k * (s_ful.get(t, 0.0)
                                                                - s_con.get(t, 0.0)) for t in keys},
                                   tr_full)
    out = {}
    for name, (s, tr) in arms.items():
        c = est_c(tr, s)
        aware, raw = _predict(sp["eligible"], s, c)
        out[name] = {"side_aware": _metrics(aware), "raw": _metrics(raw), "c": float(c)}
    movers = [t for t in s_ful if t in s_con]
    delta = np.array([s_ful[t] - s_con[t] for t in movers])
    ev_teams = {m["team_a"] for m in sp["early"]} | {m["team_b"] for m in sp["early"]}
    dev = np.array([s_ful.get(t, 0.0) - s_con.get(t, 0.0) for t in ev_teams])
    out["_movement"] = {"all_teams_rms": float(np.sqrt((delta ** 2).mean())),
                        "league_teams_rms": float(np.sqrt((dev ** 2).mean())),
                        "league_teams_max_abs": float(np.abs(dev).max()),
                        "n_league_teams": len(ev_teams)}
    return out


def run(frac=0.6, uni=None, population="all", min_eval=MIN_EVAL_MAPS,
        min_early=MIN_EARLY_SERIES):
    """Replay every eligible league at one split fraction. Population is chosen structurally."""
    if uni is None:
        uni, _, _ = load()
    folds = preregistered_folds()
    leagues = sorted({str(m["leagueid"]) for m in uni if m["leagueid"]})
    if population == "folds":
        leagues = [lg for lg in leagues if lg in folds]
    elif population != "all":
        raise SystemExit("population must be 'all' or 'folds'")
    events, skipped = [], []
    for lg in leagues:
        sp = league_split(uni, lg, frac)
        if sp is None:
            skipped.append({"leagueid": lg, "reason": "no valid chronological split"})
            continue
        if len(sp["eligible"]) < min_eval or sp["n_early_series"] < min_early:
            skipped.append({"leagueid": lg, "league_name": sp["league_name"],
                            "eligible_late_maps": len(sp["eligible"]),
                            "early_series": sp["n_early_series"],
                            "reason": "below the structural minimums"})
            continue
        res = replay_league(uni, sp)
        if res is None:
            skipped.append({"leagueid": lg, "league_name": sp["league_name"],
                            "reason": "no pre-league training data (opens the scan window)"})
            continue
        events.append({"leagueid": lg, "league_name": sp["league_name"],
                       "preregistered_fold": lg in folds,
                       "n_series": sp["n_series"], "n_early_series": sp["n_early_series"],
                       "n_late_series": sp["n_late_series"],
                       "eligible_late_maps": len(sp["eligible"]),
                       "late_maps_total": len(sp["late"]), "arms": res})
    return {"split_fraction": frac, "population": population,
            "selection_rule": {"min_early_series": min_early, "min_eligible_late_maps": min_eval,
                               "requires_pre_league_training_data": True,
                               "refers_to_observed_performance": False},
            "events": events, "skipped": skipped, "n_events": len(events),
            "n_preregistered_folds_included": sum(e["preregistered_fold"] for e in events)}


def summarize(rep, form="side_aware", metric="logloss", weighting="map"):
    """Pool per-league results: deltas, sign test, league-blocked bootstrap CI.

    `weighting` is 'map' (by evaluation weight) or 'event' (each league counts once). The two are
    reported together because a handful of season-long leagues carry most of the map weight.
    """
    arms = [a for a in rep["events"][0]["arms"] if not a.startswith("_")]
    per = {a: np.array([e["arms"][a][form][metric] for e in rep["events"]]) for a in arms}
    wts = (np.array([e["arms"]["D_full"][form]["weight"] for e in rep["events"]])
           if weighting == "map" else np.ones(len(rep["events"])))
    out = {"form": form, "metric": metric, "weighting": weighting,
           "n_events": len(rep["events"]), "population": rep["population"],
           "pooled": {a: float((per[a] * wts).sum() / wts.sum()) for a in arms}}
    rng = np.random.default_rng(20260816)
    n = len(rep["events"])
    comparisons = {"D_full_vs_A_pre": ("D_full", "A_pre"),
                   "D_full_vs_B_origin": ("D_full", "B_origin"),
                   "D_full_vs_C_concurrent": ("D_full", "C_concurrent")}
    for k in KAPPAS:
        if k != 1.00:
            comparisons[f"kappa{k:.2f}_vs_D_full"] = (f"D_kappa{k:.2f}", "D_full")
    out["comparisons"] = {}
    for name, (a, b) in comparisons.items():
        d = per[a] - per[b]                       # negative favours arm `a` for log-loss/Brier
        boots = []
        for _ in range(4000):
            i = rng.integers(0, n, n)
            boots.append(float((d[i] * wts[i]).sum() / wts[i].sum()))
        lo, hi = np.percentile(boots, [5, 95])
        out["comparisons"][name] = {
            "pooled_delta": float((d * wts).sum() / wts.sum()),
            "mean_event_delta": float(d.mean()),
            "events_improved": int((d < 0).sum()), "events_worsened": int((d > 0).sum()),
            "league_blocked_90ci": [float(lo), float(hi)],
            "significant": bool(hi < 0 or lo > 0)}
    return out


def manifest(rep):
    """The exact league manifest behind a report -- what was in, what was out, and why."""
    return {"population": rep["population"], "selection_rule": rep["selection_rule"],
            "included": [{k: e[k] for k in ("leagueid", "league_name", "preregistered_fold",
                                            "n_series", "n_early_series", "n_late_series",
                                            "eligible_late_maps")}
                         for e in sorted(rep["events"], key=lambda x: -x["eligible_late_maps"])],
            "excluded": rep["skipped"]}


def main():
    ap = argparse.ArgumentParser(
        description="within-league early->late sequential-assimilation diagnostic "
                    "(NOT a group-to-playoff replay)")
    ap.add_argument("--frac", type=float, default=0.6)
    ap.add_argument("--sweep", action="store_true",
                    help="run every split fraction fixed for this audit")
    ap.add_argument("--population", choices=("all", "folds", "both"), default="both")
    ap.add_argument("--json", help="write the full report here")
    a = ap.parse_args()
    uni, _, _ = load()
    fracs = SPLIT_FRACTIONS if a.sweep else (a.frac,)
    pops = ("all", "folds") if a.population == "both" else (a.population,)
    out = {}
    for pop in pops:
        for f in fracs:
            rep = run(f, uni=uni, population=pop)
            if not rep["events"]:
                print(f"{pop} @ {f}: no eligible leagues"); continue
            block = {"report": rep, "manifest": manifest(rep)}
            for wt in ("map", "event"):
                block[f"side_aware_logloss_{wt}"] = summarize(rep, "side_aware", "logloss", wt)
            out[f"{pop}@{f}"] = block
            s = block["side_aware_logloss_map"]
            se = block["side_aware_logloss_event"]
            print(f"\n=== population={pop} split={f} | {rep['n_events']} leagues "
                  f"({rep['n_preregistered_folds_included']} preregistered) | "
                  f"{sum(e['eligible_late_maps'] for e in rep['events'])} eligible late maps ===")
            for name in s["comparisons"]:
                cm, ce = s["comparisons"][name], se["comparisons"][name]
                print(f"  {name:<26} map {cm['pooled_delta']:+.4f} "
                      f"[{cm['league_blocked_90ci'][0]:+.4f},{cm['league_blocked_90ci'][1]:+.4f}]"
                      f"{'*' if cm['significant'] else ' '} | "
                      f"event {ce['pooled_delta']:+.4f} "
                      f"[{ce['league_blocked_90ci'][0]:+.4f},{ce['league_blocked_90ci'][1]:+.4f}]"
                      f"{'*' if ce['significant'] else ' '} | "
                      f"{cm['events_improved']}/{cm['events_improved']+cm['events_worsened']}")
    if a.json:
        os.makedirs(os.path.dirname(a.json), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1, default=float)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
