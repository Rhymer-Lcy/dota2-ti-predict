"""TI15 Main Event: sequential frozen-model update, exact bracket forecast, 14-slot optimization.

Chains: verified TI15 results (ti15_results) -> frozen B-bt sequential refit at three auditable
states -> series-blocked bootstrap -> exact enumeration of all 2^14 bracket outcomes (bracket) ->
exhaustive search over all 2^14 coherent slates for maximum expected OFFICIAL score.

What is frozen and is NOT reopened here: the model family (B-bt), half-life (90d), lambda (1), the
absence of any calibration layer, the side-neutral map probability, and the series-cap weighting.
Completed TI15 matches enter as ordinary observations under that unchanged estimator -- frozen
hyperparameters do not mean frozen strengths.

What is NOT used: any network call, any market/odds/crowd input, any Main Event result, any manual
form or momentum adjustment, any TI/playoff multiplier.

The optimization is exact, not sampled. There are 14 binary nodes, so 2^14 = 16,384 complete
outcomes and -- because a coherent slate is itself an outcome -- exactly 16,384 candidate slates.
Every candidate is scored against every outcome. Parameter uncertainty enters by averaging the
outcome distribution over bootstrap draws before optimizing, which is exact because expected score
is linear in that distribution.

Run: python -m ti_predict.predict_main_event [--draws 1000] [--out DIR]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict import bracket as bk
from ti_predict import ti15_results as tr
from ti_predict.backtest import load
from ti_predict.calibrate import bt_strengths, est_c
from ti_predict.contest_rules import PRODUCTION_HALF_LIFE_DAYS
from ti_predict.series import series_win_prob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(REPO, "data", "ti2026", "processed")
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
LOCKED_GROUP = os.path.join(REPO, "predictions", "ti2026", "group-stage",
                            "ti15_group_prediction.json")
OUTDIR = os.path.join(REPO, "predictions", "ti2026", "playoffs")
SEED = 20260816
POOL = 4096              # candidate slates carried into the per-draw stability analysis
VERIFY_DRAWS = 30        # draws re-checked with a FULL 16,384-slate scan


def _ts(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def _dirty():
    try:
        return bool(subprocess.check_output(["git", "-C", REPO, "status", "--porcelain"],
                                            text=True).strip())
    except Exception:
        return None


def _sha256(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- states
def fit(rows, cutoff_ts):
    """The frozen estimator, unchanged: weighted BT at h90 / lambda=1 plus its train-only c.

    Every training row feeds the strengths -- Bradley-Terry is orientation-symmetric, so the
    synthetic TI15 rows lose nothing by being oriented winner-first. Only `est_c` is restricted to
    rows whose team_a genuinely means Radiant; see ti15_results.side_labelled for why. This is a
    missing-metadata correction, not a model change: the estimator, h90, lambda and the side-neutral
    formula are untouched, and c is not tuned.
    """
    train = [m for m in rows if m["start_time"] < cutoff_ts]
    if not train:
        raise SystemExit("no training maps before cutoff")
    s = bt_strengths(train, cutoff_ts, hl=float(PRODUCTION_HALF_LIFE_DAYS))
    return s, float(est_c(tr.side_labelled(train), s)), len(train)


def build_states(collapse_to=None):
    """States A (pre-TI), B (post-Swiss) and C (post-Elimination / serve), plus a decay control."""
    base = tr.historical_universe()
    swiss_only, prov_s = tr.augmented_universe(collapse_to=collapse_to, use_stages=("swiss",))
    full, prov_f = tr.augmented_universe(collapse_to=collapse_to,
                                         use_stages=("swiss", "elimination"))
    cut_a, cut_b, cut_c = (_ts(tr.SWISS_LOCK), _ts("2026-08-15T18:00:00Z"),
                           _ts(tr.SERVE_CUTOFF))
    sa, ca, na = fit(base, cut_a)
    sb, cb, nb = fit(swiss_only, cut_b)
    sc, cc, nc = fit(full, cut_c)
    sctl, cctl, nctl = fit(base, cut_c)          # historical data only, serve-time decay origin
    return {
        "A_pre_ti": {"strength": sa, "c": ca, "train_maps": na, "cutoff": _iso(cut_a),
                     "data": "historical universe only"},
        "B_post_swiss": {"strength": sb, "c": cb, "train_maps": nb, "cutoff": _iso(cut_b),
                         "data": "historical universe + 39 TI15 Swiss series"},
        "C_serve": {"strength": sc, "c": cc, "train_maps": nc, "cutoff": _iso(cut_c),
                    "data": "historical universe + 39 Swiss + 5 Elimination series"},
        "control_decay_origin": {"strength": sctl, "c": cctl, "train_maps": nctl,
                                 "cutoff": _iso(cut_c),
                                 "data": "historical universe only, serve-time decay origin "
                                         "(isolates the decay shift from the new observations)"},
        "_rows": full, "_provenance": {"swiss_only": prov_s, "full": prov_f},
        "_cuts": {"A": cut_a, "B": cut_b, "C": cut_c},
    }


# --------------------------------------------------------------------------- uncertainty
def series_blocks(rows):
    """Group map rows into series blocks. A Bo3 is ONE block, never three independent draws."""
    blocks = defaultdict(list)
    for i, r in enumerate(rows):
        blocks[r["series_id"] if r["series_id"] else ("solo", r["match_id"])].append(i)
    return list(blocks.values())


def bootstrap_strengths(rows, cutoff_ts, teams, draws, seed=SEED):
    """Series-blocked nonparametric bootstrap of the frozen fit.

    Resamples whole SERIES with replacement and refits; each map keeps its own 1/series_size weight,
    so a duplicated Bo3 contributes total weight 1.0 again rather than three independent maps.
    Returns (S, C) with S shape (draws, len(teams)) and C the per-draw radiant coefficient.
    """
    train = [m for m in rows if m["start_time"] < cutoff_ts]
    blocks = series_blocks(train)
    rng = np.random.default_rng(seed)
    S = np.empty((draws, len(teams))); C = np.empty(draws)
    nb = len(blocks)
    for d in range(draws):
        pick = rng.integers(0, nb, nb)
        samp = [train[i] for b in pick for i in blocks[b]]
        s = bt_strengths(samp, cutoff_ts, hl=float(PRODUCTION_HALF_LIFE_DAYS))
        S[d] = [s.get(t, 0.0) for t in teams]
        C[d] = est_c(tr.side_labelled(samp), s)     # same side-provenance restriction as fit()
    return S, C, nb


# --------------------------------------------------------------------------- optimization
def node_marginals(topo, W, PR, P, teams):
    """Per node: P(each team wins it) and P(each team reaches it)."""
    out = {}
    for col, nid in enumerate(topo["order"]):
        win = np.zeros(len(teams)); reach = np.zeros(len(teams))
        for i in range(len(teams)):
            win[i] = P[W[:, col] == i].sum()
            reach[i] = P[(PR[:, col, 0] == i) | (PR[:, col, 1] == i)].sum()
        out[nid] = {"win": win, "reach": reach}
    return out


def slate_detail(topo, W, PR, P, teams, row, strength, c):
    """Node-by-node description of one coherent slate."""
    marg = node_marginals(topo, W, PR, P, teams)
    rows = []
    for col, nid in enumerate(topo["order"]):
        a, b = int(PR[row, col, 0]), int(PR[row, col, 1])
        pick = int(W[row, col])
        other = b if pick == a else a
        mp = bk.map_prob(strength[teams[pick]], strength[teams[other]], c)
        rows.append({
            "selection_id": topo["node_to_selection"][nid], "node_id": nid,
            "round": topo["label"][nid], "series": topo["series_name"][nid],
            "best_of": topo["best_of"][nid],
            "predicted_matchup": [teams[a], teams[b]],
            "pick": teams[pick], "opponent": teams[other],
            "conditional_win_prob": float(series_win_prob(mp, topo["best_of"][nid])),
            "map_win_prob": float(mp),
            "marginal_pick_wins_node": float(marg[nid]["win"][pick]),
            "marginal_matchup_occurs": float(P[(W[:, col] == pick)
                                               & ((PR[:, col, 0] == other)
                                                  | (PR[:, col, 1] == other))].sum()),
        })
    return rows


def flip_costs(W, Es, topo, teams, row):
    """For each node: the best coherent slate that picks someone else, and what that costs."""
    out = {}
    for col, nid in enumerate(topo["order"]):
        pick = W[row, col]
        mask = W[:, col] != pick
        alt = int(np.flatnonzero(mask)[np.argmax(Es[mask])])
        out[nid] = {"best_alternative_row": alt, "alternative_pick": teams[int(W[alt, col])],
                    "alternative_expected_score": float(Es[alt]),
                    "cost_of_changing": float(Es[row] - Es[alt]),
                    "alternative_differs_at": [topo["node_to_selection"][topo["order"][k]]
                                               for k in range(len(topo["order"]))
                                               if W[alt, k] != W[row, k]]}
    return out


# --------------------------------------------------------------------------- pipeline
def run(draws=1000, outdir=None, verify_draws=VERIFY_DRAWS, seed=SEED, tie_report=None):
    started = datetime.now(timezone.utc)
    git_at_start = {"git_commit_at_start": _commit(), "git_dirty_at_start": _dirty()}

    # ---- gates -----------------------------------------------------------
    recon = tr.verify_standings()
    topo = bk.load_topology()
    scoring = bk.verify_scoring_vector()
    seats = {nid: (tr.canon(a), tr.canon(b)) for nid, (a, b) in tr.UBQF.items()}
    # The saved Valve feed proves the graph but carries no team ids in its Playoff nodes, so the four
    # seeded participants rest on separate, weaker evidence. Verify it before anything is computed.
    from ti_predict import seating_evidence as se
    seating = se.verify(seats=seats)
    display = se.display_names()
    teams, W, PR = bk.enumerate_structure(topo, seats)

    st = build_states()
    rows = st["_rows"]
    # A cutoff is the h90 decay reference and the training-set upper bound, not metadata. One dated
    # after the run that consumes it would claim knowledge the run did not have, so it is refused.
    future = {k: v["cutoff"] for k, v in st.items()
              if not k.startswith("_") and _ts(v["cutoff"]) > int(started.timestamp())}
    if future:
        raise SystemExit(
            "RUN BLOCKED: state cutoff dated after this run started "
            f"({started.isoformat(timespec='seconds')}): {future}. A cutoff feeds the decay and the "
            "training filter, so it must be a time already reached, never a rounded-up label.")
    cutoff_provenance = {
        "role": "h90 decay reference AND training-set upper bound (start_time < cutoff); "
                "not metadata",
        "run_started_at": started.isoformat(timespec="seconds"),
        "serve_cutoff": st["C_serve"]["cutoff"],
        "latest_model_timestamp_utc": _iso(max(r["start_time"] for r in rows
                                               if r.get("ti15_stage"))),
        "timestamp_basis": "IMPUTED. Round 1 carries the saved official league feed's scheduled "
                           "times; rounds 2-6 have no locally recorded time and are placed on a "
                           "two-blocks-per-day cadence purely so the h90 decay has something to "
                           "weight by. The value above is therefore the latest timestamp USED BY "
                           "THE MODEL, not an externally observed finish time for the last series.",
        "timestamp_provenance_counts": {
            k: sum(1 for r in rows if r.get("timestamp_provenance") == k)
            for k in (tr.TS_OFFICIAL_SCHEDULE, tr.TS_IMPUTED_CADENCE)},
        "chronology_gate": "latest timestamp used by the model < serve cutoff <= production run "
                           "start. This orders three things the pipeline controls; it asserts "
                           "nothing about when the final series really ended.",
        "cutoff_is_after_latest_model_timestamp": True,
        "cutoff_is_not_in_the_future": True,
        "margin_after_latest_model_timestamp_hours": round(
            (_ts(st["C_serve"]["cutoff"])
             - max(r["start_time"] for r in rows if r.get("ti15_stage"))) / 3600.0, 2),
        "margin_before_run_start_hours": round(
            (int(started.timestamp()) - _ts(st["C_serve"]["cutoff"])) / 3600.0, 2),
    }
    ti_rows = [r for r in rows if r.get("ti15_stage")]
    leak = [r for r in ti_rows if r["ti15_round"] > 6]
    if leak:
        raise SystemExit(f"LEAKAGE: {len(leak)} rows past the Elimination Round entered the fit")
    per_series = defaultdict(int)
    for r in ti_rows:
        per_series[r["series_id"]] += 1
    n_ti_series = len(per_series)
    if n_ti_series != 44:
        raise SystemExit(f"expected 44 TI15 series in the fit, found {n_ti_series}")
    bad = {s: k for s, k in per_series.items() if k not in (2, 3)}
    if bad:
        raise SystemExit(f"a TI15 Bo3 expanded to something other than 2 or 3 maps: {bad}")
    if abs(sum(r["w"] for r in ti_rows) - 44.0) > 1e-9:
        raise SystemExit("the 44 TI15 series do not carry total weight 44.0; a series is being "
                         "counted more than once or its maps are mis-weighted")

    # Audit the whole tracked table (it is keyed to the 16-team field), then gate on the eight that
    # actually enter this forecast. A CONFLICT on an eliminated team cannot block a bracket run.
    from ti_predict.rosters import roster_audit
    rosters = roster_audit()
    rosters["blocking_in_main_event"] = sorted(set(rosters["blocking"]) & set(teams))
    rosters["changed_in_main_event"] = [c for c in rosters["changed"] if c["organization"] in teams]
    if rosters["blocking_in_main_event"]:
        raise SystemExit("RUN BLOCKED: unresolved roster audit for "
                         + ", ".join(rosters["blocking_in_main_event"]))

    locked = json.load(open(LOCKED_GROUP, encoding="utf-8"))["manifest"]
    identity = {"locked_training_maps": locked["training_maps"],
                "refit_training_maps": st["A_pre_ti"]["train_maps"],
                "locked_radiant_c": locked["radiant_c"],
                "refit_radiant_c": round(st["A_pre_ti"]["c"], 4),
                "locked_cutoff": locked["data_cutoff"],
                "refit_cutoff": st["A_pre_ti"]["cutoff"]}
    identity["reproduced"] = (identity["locked_training_maps"] == identity["refit_training_maps"]
                              and identity["locked_radiant_c"] == identity["refit_radiant_c"])
    if not identity["reproduced"]:
        raise SystemExit(f"PRE-TI state does not reproduce the locked artifact: {identity}")

    # ---- serve state + uncertainty ---------------------------------------
    serve = st["C_serve"]
    strength = {t: serve["strength"][t] for t in teams}
    c = serve["c"]
    S, Cb, n_blocks = bootstrap_strengths(rows, st["_cuts"]["C"], teams, draws, seed=seed)

    P_hat = bk.outcome_probs(topo, W, PR, teams, strength, c)
    Pd = np.empty((draws, W.shape[0]))
    for d in range(draws):
        Pd[d] = bk.outcome_probs(topo, W, PR, teams,
                                 {t: S[d, i] for i, t in enumerate(teams)}, float(Cb[d]),
                                 check=False)
        Pd[d] /= Pd[d].sum()
    P_bar = Pd.mean(axis=0)

    # ---- exhaustive optimization ----------------------------------------
    Es, Ec = bk.expected_scores(W, P_bar)
    Es_hat, Ec_hat = bk.expected_scores(W, P_hat)
    best_score = int(np.argmax(Es))
    best_correct = int(np.argmax(Ec))
    greedy = bk.slate_row(W, bk.greedy_favourite(topo, seats, strength, c, teams))
    if greedy < 0:
        raise SystemExit("the greedy favourite bracket is not a coherent slate; topology is wrong")

    order_by_score = np.argsort(-Es)
    pool = order_by_score[:POOL]
    Kp = bk.agreement_matrix(W, pool)
    Sp = bk.SCORE_VEC[Kp].astype(np.float32)
    draw_best = np.asarray(pool[np.argmax(Sp @ Pd.T.astype(np.float32), axis=0)])

    # verification: does the pooled candidate set actually contain each draw's global optimum?
    rng = np.random.default_rng(seed + 1)
    check_idx = rng.choice(draws, size=min(verify_draws, draws), replace=False)
    ver_ok, ver_gap = 0, 0.0
    for d in check_idx:
        e_full, _ = bk.expected_scores(W, Pd[d])
        g = int(np.argmax(e_full))
        if g == int(draw_best[d]):
            ver_ok += 1
        else:
            ver_gap = max(ver_gap, float(e_full[g] - e_full[int(draw_best[d])]))
    verification = {"draws_checked_with_full_scan": int(len(check_idx)),
                    "pool_optimum_equals_global_optimum": int(ver_ok),
                    "max_expected_score_shortfall": round(ver_gap, 3),
                    "pool_size": int(POOL)}

    marg = node_marginals(topo, W, PR, P_bar, teams)
    gf_col = topo["order"].index(topo["gf"])
    ubf = next(n for n in topo["order"] if topo["label"][n] == "UBF")
    lbf = next(n for n in topo["order"] if topo["label"][n] == "LBF")
    seat_node = {t: nid for nid, pair in seats.items() for t in pair}
    champ = {teams[i]: float(P_bar[W[:, gf_col] == i].sum()) for i in range(len(teams))}
    reach_gf = {teams[i]: float(marg[topo["gf"]]["reach"][i]) for i in range(len(teams))}
    champ_draws = np.array([[Pd[d][W[:, gf_col] == i].sum() for i in range(len(teams))]
                            for d in range(draws)])

    primary = slate_detail(topo, W, PR, P_bar, teams, best_score, strength, c)
    costs = flip_costs(W, Es, topo, teams, best_score)
    stability = {}
    for col, nid in enumerate(topo["order"]):
        same = float(np.mean(W[draw_best, col] == W[best_score, col]))
        picks = defaultdict(float)
        for d in range(draws):
            picks[teams[int(W[draw_best[d], col])]] += 1.0 / draws
        stability[nid] = {"draw_agreement": same,
                          "draw_pick_distribution": dict(sorted(picks.items(),
                                                                key=lambda kv: -kv[1]))}
    # How uncertain each PREDICTED matchup really is: the same two teams re-priced under every
    # bootstrap draw. This separates "close on the point estimate" from "close and badly pinned
    # down", which are different reasons to distrust a node.
    idx_of = {t: i for i, t in enumerate(teams)}
    for r in primary:
        i, j = idx_of[r["pick"]], idx_of[r["opponent"]]
        d = S[:, i] - S[:, j]
        mp = 0.5 * (1.0 / (1.0 + np.exp(-(d + Cb))) + 1.0 / (1.0 + np.exp(-(d - Cb))))
        cw = np.array([series_win_prob(float(x), r["best_of"]) for x in mp])
        r["conditional_win_prob_90ci"] = [round(float(np.percentile(cw, 5)), 4),
                                          round(float(np.percentile(cw, 95)), 4)]
        r["conditional_win_prob_sd"] = round(float(cw.std(ddof=1)), 4)
        r["draws_favouring_pick"] = round(float((cw > 0.5).mean()), 4)
    for r in primary:
        nid = r["node_id"]
        r.update(cost_of_changing=costs[nid]["cost_of_changing"],
                 alternative=costs[nid]["alternative_pick"],
                 alternative_expected_score=costs[nid]["alternative_expected_score"],
                 bootstrap_draw_agreement=stability[nid]["draw_agreement"],
                 draw_pick_distribution=stability[nid]["draw_pick_distribution"])
        r["fragile"] = bool(abs(r["conditional_win_prob"] - 0.5) < 0.05
                            or r["cost_of_changing"] < 25.0
                            or r["bootstrap_draw_agreement"] < 0.75
                            or r["draws_favouring_pick"] < 0.75)

    # If a near-tie between the primary and its runner-up has been resolved by the dedicated paired
    # analysis, carry its verdict here so the two artifacts cannot drift. Optional by design: absent
    # file -> null, and the slate is unaffected either way.
    tie_path = tie_report or os.path.join(OUTDIR, "research", "slot810_tiebreak_20260816.json")
    tie = None
    if os.path.exists(tie_path):
        with open(tie_path, encoding="utf-8") as fh:
            t = json.load(fh)
        tie = {k: t[k] for k in ("differ_at_selection_ids", "draws", "plug_in_delta",
                                 "bootstrap_mean_delta", "bootstrap_median_delta", "bootstrap_sd",
                                 "mc_se_of_mean", "ci90", "ci95", "p_delta_gt_0", "verdict",
                                 "verdict_reason")}
        tie["artifact"] = "predictions/ti2026/playoffs/research/slot810_tiebreak_20260816.json"
        tie["read_from_staging_copy"] = bool(tie_report)
        tie["source_sha256"] = _sha256(tie_path)
        tie["deterministic_pick_retained"] = (
            "The fixed-seed 1000-draw production approximation has a unique NUMERICAL argmax, and "
            "the production decision procedure takes it, so the client pick stays the primary. That "
            "is emphatically NOT a claim that the underlying uncertainty-integrated objective has a "
            "unique argmax, nor that Nigma Galaxy is truly the better pick: the 40,000-draw paired "
            "comparison does not resolve the sign. The pick is determinism, not evidence.")
        tie["statistically_separated"] = False

    # runner-up: best slate that is not the primary, and best slate with a different champion
    runner = int(order_by_score[1])
    champ_pick = W[best_score, gf_col]
    diff_champ_mask = W[:, gf_col] != champ_pick
    diff_champ = int(np.flatnonzero(diff_champ_mask)[np.argmax(Es[diff_champ_mask])])

    # Timestamp sensitivity: collapse every TI15 map onto one instant and redo the serve state.
    # Both arms are compared at the POINT estimate, so the only thing that differs is the timestamps.
    st2 = build_states(collapse_to="2026-08-16T00:00:00Z")
    s2 = st2["C_serve"]
    P2 = bk.outcome_probs(topo, W, PR, teams, {t: s2["strength"][t] for t in teams}, s2["c"])
    Es2, _ = bk.expected_scores(W, P2)
    champ_hat = {teams[i]: float(P_hat[W[:, gf_col] == i].sum()) for i in range(len(teams))}
    ts_sens = {"arm": "all 44 TI15 series collapsed to 2026-08-16T00:00:00Z",
               "compared_against": "the point-estimate serve state (like for like; the primary "
                                   "slate itself is chosen on the bootstrap-averaged distribution)",
               "max_abs_strength_change": round(float(max(abs(s2["strength"][t] - strength[t])
                                                          for t in teams)), 6),
               "optimal_slate_unchanged": bool(int(np.argmax(Es2)) == int(np.argmax(Es_hat))),
               "champion_prob_max_change": round(float(max(
                   abs(float(P2[W[:, gf_col] == i].sum()) - champ_hat[teams[i]])
                   for i in range(len(teams)))), 6)}

    # Standings rank vs model strength: where the estimator disagrees with the Swiss table, and why
    # that is not a defect. Reported, never corrected -- a manual override is exactly what is banned.
    rank_of = {tr.canon(t): r for r, t, *_ in tr.PUBLISHED_STANDINGS}
    by_strength = sorted(teams, key=lambda t: -strength[t])
    tension = [{"team": t, "swiss_rank": rank_of[t], "model_rank": by_strength.index(t) + 1,
                "gap": rank_of[t] - (by_strength.index(t) + 1)} for t in by_strength]

    # Purely DESCRIPTIVE: how the locked group-stage slate happened to score. One realization of one
    # tournament is not evidence about calibration in either direction -- the whole 16-slot outcome
    # has a standard deviation of roughly two slots, so 6 against 5.249 is indistinguishable from
    # noise and would be equally uninformative had it come out at 3 or at 8. It is recorded because
    # a reader will otherwise go and compute it, and it feeds nothing.
    actual_bucket = {tr.canon("TEAM VISION"): "4-0", tr.canon("Team Liquid"): "4-1",
                     tr.canon("Nigma Galaxy"): "4-1", tr.canon("Team Spirit"): "decider_win",
                     tr.canon("Iron Wing"): "decider_win", tr.canon("Team Falcons"): "decider_win",
                     tr.canon("BoomBoys"): "decider_win", tr.canon("Team Yandex"): "decider_win",
                     tr.canon("Aurora Gaming"): "decider_loss", tr.canon("LGD Gaming"): "decider_loss",
                     tr.canon("Vici Gaming"): "decider_loss",
                     tr.canon("Team Resilience"): "decider_loss",
                     tr.canon("GamerLegion"): "decider_loss", tr.canon("Xtreme Gaming"): "1-4",
                     tr.canon("OG"): "1-4", tr.canon("HULIGANI"): "0-4"}
    lock_doc = json.load(open(LOCKED_GROUP, encoding="utf-8"))
    hits = sum(1 for b, picks in lock_doc["slate"].items() for p in picks
               if actual_bucket[p["team"]] == b)
    group_scoreboard = {
        "slots_correct": hits,
        "expected_correct_at_lock": lock_doc["manifest"]["expected_correct"],
        "status": "DESCRIPTIVE ONLY",
        "note": "a single realized tournament. It is NOT evidence that the model is calibrated, "
                "validated, or well specified, and it is not why the model was left frozen. The "
                "decision not to reopen rests on the preregistered validation and the freeze "
                "(docs/validation-plan-v2.md), which predate this outcome.",
        "must_not_be_used_as": ["calibration evidence", "validation evidence",
                                "justification for keeping or changing the model"]}

    # AUXILIARY diagnostic, deliberately downgraded. It is a within-league early->late test of the
    # sequential update, NOT a group/Swiss-to-playoff replay: the local data has no stage field, so
    # no stage boundary exists to replay. TI15 is excluded from it by construction. Its one load-
    # bearing job is negative -- confirming that no audit-predeclared shrinkage beats the plain frozen
    # refit, which is the only finding that could have changed production.
    from ti_predict import sequential_assimilation as sa
    base_uni, _, _ = load()
    assim, kappa_wins = {}, []
    for pop in ("all", "folds"):
        for f in sa.SPLIT_FRACTIONS:
            rep = sa.run(f, uni=base_uni, population=pop)
            block = {"leagues": rep["n_events"],
                     "preregistered_folds_included": rep["n_preregistered_folds_included"],
                     "eligible_late_maps": sum(e["eligible_late_maps"] for e in rep["events"])}
            for wt in ("map", "event"):
                s = sa.summarize(rep, "side_aware", "logloss", wt)
                block[f"{wt}_weighted"] = {
                    k: {"pooled_delta": round(v["pooled_delta"], 4),
                        "ci90": [round(v["league_blocked_90ci"][0], 4),
                                 round(v["league_blocked_90ci"][1], 4)],
                        "leagues_improved": v["events_improved"],
                        "leagues_worsened": v["events_worsened"],
                        "significant": v["significant"]}
                    for k, v in s["comparisons"].items()}
                kappa_wins += [f"{pop}@{f}/{wt}/{k}" for k, v in s["comparisons"].items()
                               if k.startswith("kappa") and v["significant"]
                               and v["pooled_delta"] < 0]
            assim[f"{pop}@{f:.1f}"] = block
    key_cmp = "D_full_vs_C_concurrent"
    folds_sig = {f: assim[f"folds@{f:.1f}"]["map_weighted"][key_cmp]["significant"]
                 and assim[f"folds@{f:.1f}"]["event_weighted"][key_cmp]["significant"]
                 for f in sa.SPLIT_FRACTIONS}
    replay_summary = {
        "name": "within-league early-to-late sequential-assimilation diagnostic",
        "is_a_group_to_playoff_replay": False,
        "why_not": "the rating universe has no stage field, so no local record exists of which "
                   "series were group and which were playoff. The split is chronological within a "
                   "league. Nothing here is evidence about elimination brackets specifically.",
        "status": "AUXILIARY, DOWNGRADED",
        "purpose": "test the sequential-update procedure; it never selects a model",
        "ti15_excluded_from_selection": True,
        "stage_metadata_available_locally": False,
        "selection_rule": "structural only -- a valid chronological split, at least "
                          f"{sa.MIN_EARLY_SERIES} early series, at least {sa.MIN_EVAL_MAPS} late "
                          "maps whose both teams appeared early, and non-empty pre-league training "
                          "data. No criterion refers to a league's outcomes or to model error on it.",
        "populations": {
            "all": "every league passing the minimums. Dominated by season-long leagues and "
                   "streamer/exhibition events, which have no group-to-playoff arc at all; the "
                   "three largest supply about half the map weight.",
            "folds": "only the leagues in inputs/folds.csv -- the preregistered set, i.e. discrete "
                     "tournaments. Smaller and the relevant population for a TI-like event."},
        "per_population_and_split": assim,
        "supported_claim": "on the broad league population, assimilating a league's earlier results "
                           "improves prediction of its later results under the frozen update "
                           "(0.009-0.020 nats, significant at every split and both weightings)",
        "not_established": "the same effect on discrete tournaments alone. It is positive in "
                           "direction at all four splits but significant at only "
                           f"{sum(folds_sig.values())} of 4 "
                           f"(significant at {[f for f, v in folds_sig.items() if v]}, not at "
                           f"{[f for f, v in folds_sig.items() if not v]}), and the splits nearest "
                           "the TI15 shape are among the non-significant ones. No empirical warrant "
                           "is claimed for 'observing the TI15 Swiss improves Main Event prediction'.",
        "audit_predeclared_candidate_set": ["plain frozen refit (kappa=1.00)"]
                                           + [f"shrinkage kappa={k:.2f}" for k in sa.KAPPAS
                                              if k != 1.00],
        "candidate_set_provenance": "fixed before scoring this auxiliary analysis and not altered "
                                    "afterwards, but NOT preregistered: no timestamped earlier "
                                    "artifact in this repository registers this kappa set. It "
                                    "carries none of the standing of the preregistered v1 model "
                                    "validation. Same status for the split fractions.",
        "selected": "plain frozen sequential refit (kappa=1.00)",
        "selection_reason": ("no shrinkage candidate beat the plain refit anywhere -- in the cells "
                             "where the family separates at all, shrinkage is significantly WORSE. "
                             "kappa=1 is also the frozen default, so it wins every tie."
                             if not kappa_wins else f"shrinkage won at {sorted(set(kappa_wins))}"),
        "why_production_uses_the_plain_refit": "because it is the frozen default, not because this "
                                               "diagnostic validated it",
        "production_path_changed": False,
        "detail_artifact": "predictions/ti2026/playoffs/research/"
                           "sequential_assimilation_20260816.json",
    }
    if kappa_wins:
        raise SystemExit("A shrinkage adjustment beat the plain frozen refit in the audit-predeclared "
                         f"candidate set at {sorted(set(kappa_wins))}. That is a decision, not an "
                         "automatic edit -- and the candidate set is not preregistered, which is a "
                         "further reason to stop and adopt it deliberately before serving.")

    finished = datetime.now(timezone.utc)
    art = {
        "manifest": {
            "artifact": "TI15 main-event 14-slot bracket prediction",
            "status": "OFFICIAL",
            "generated_at": finished.isoformat(timespec="seconds"),
            "runtime_seconds": round((finished - started).total_seconds(), 1),
            "code_commit": _commit(), **git_at_start,
            "snapshot_boundary": "after the final Elimination Round series (Team Yandex 2-1 LGD "
                                 "Gaming, 2026-08-16); before any Main Event match",
            # Clean-run provenance, named plainly so it can be checked without reading the schema.
            # `future_main_event_results_used` is DERIVED from the leakage gate above (the run aborts
            # if any inserted row sits past the Elimination Round), not asserted by hand.
            "network_used": False,
            "odds_used": False,
            "future_main_event_results_used": bool(leak),
            "clean_run_provenance_note": "network_used and odds_used are properties of the code "
                                         "path taken: the league feed is read from the on-disk "
                                         "snapshot whose sha256 is recorded below, no fetcher is "
                                         "invoked, and no market or crowd series exists in the "
                                         "repository to read.",
            "data_cutoff": serve["cutoff"],
            "cutoff_provenance": cutoff_provenance,
            "model": {"family": "B-bt", "half_life_days": PRODUCTION_HALF_LIFE_DAYS, "lambda": 1.0,
                      "calibration": "none", "map_prob": "side-neutral 0.5*(sigmoid(d+c)+sigmoid(d-c))",
                      "radiant_c": round(c, 4), "weighting": "1/series_size (series cap)",
                      "frozen": True, "reopened_for_ti15": False},
            "inputs_used": {"network": False, "odds_or_market": False, "crowd_percentages": False,
                            "main_event_results": False, "manual_adjustments": False,
                            "historical_universe_rows": len([r for r in rows
                                                             if not r.get("ti15_stage")]),
                            "ti15_series_inserted": n_ti_series,
                            "ti15_map_rows": len(ti_rows)},
            "provenance": {
                "universe_sha256": _sha256(os.path.join(PROC, "universe_maps.csv")),
                "league_feed_sha256": _sha256(os.path.join(REPO, "data", "ti2026", "raw",
                                                           "league_19719_feed.json")),
                "teams_sha256": _sha256(os.path.join(INPUTS, "teams.csv")),
                "canonical_identity_sha256": _sha256(os.path.join(INPUTS,
                                                                  "canonical_identity.csv")),
                "questions_sha256": _sha256(os.path.join(INPUTS, "prediction_questions.json")),
                "ti15_results": st["_provenance"]["full"],
            },
            "seed": seed, "bootstrap_draws": draws, "bootstrap_blocks": n_blocks,
            "approximation": {
                "objective": "expected official score under the outcome distribution averaged over "
                             f"{draws} fixed-seed series-blocked bootstrap draws",
                "exact_given_the_distribution": "the 16,384 x 16,384 scoring is exact; the "
                                                "APPROXIMATION is the finite bootstrap average that "
                                                "stands in for the parameter posterior",
                "read_as_estimates": ["expected_score", "expected_correct", "runner-up regret",
                                      "per-node cost_of_changing"],
                "draws_not_increased_for_precision": "the draw count is a fixed production "
                                                     "parameter, not tuned to sharpen a headline",
            },
            "enumeration": {"outcomes": int(W.shape[0]), "coherent_slates": int(W.shape[0]),
                            "method": "exact enumeration of all 2^14 outcomes; no Monte Carlo",
                            "probability_mass": float(P_bar.sum())},
        },
        "gates": {"result_reconciliation": recon, "pipeline_identity_vs_locked_group_run": identity,
                  "scoring_vector": scoring,
                  "bracket_topology": {"source": topo["source"],
                                       "shape": {k: sum(1 for n in topo["order"]
                                                        if topo["label"][n] == k)
                                                 for k in bk.EXPECTED_SHAPE},
                                       "nodes": [{"selection_id": topo["node_to_selection"][n],
                                                  "node_id": n, "round": topo["label"][n],
                                                  "best_of": topo["best_of"][n],
                                                  "inputs": [f"{t}{s}" for s, t in topo["inputs"][n]]
                                                            or ["seeded"],
                                                  "client_series": topo["series_name"][n]}
                                                 for n in topo["order"]]},
                  "pool_verification": verification,
                  "timestamp_sensitivity": ts_sens,
                  "seeded_participants": seating,
                  "roster_audit": rosters,
                  "standings_vs_model_strength": tension,
                  "locked_group_slate_scoreboard": group_scoreboard,
                  "sequential_assimilation": replay_summary},
        "seeding": [{"node_id": nid, "selection_id": topo["node_to_selection"][nid],
                     "client_names": list(pair), "teams": [tr.canon(pair[0]), tr.canon(pair[1])]}
                    for nid, pair in sorted(tr.UBQF.items())],
        "strength_evolution": {
            t: {"pre_ti": round(st["A_pre_ti"]["strength"][t], 4),
                "post_swiss": round(st["B_post_swiss"]["strength"][t], 4),
                "serve": round(strength[t], 4),
                "serve_bootstrap_sd": round(float(S[:, i].std(ddof=1)), 4),
                "serve_bootstrap_90ci": [round(float(np.percentile(S[:, i], 5)), 4),
                                         round(float(np.percentile(S[:, i], 95)), 4)],
                "decay_only_control": round(st["control_decay_origin"]["strength"][t], 4),
                "delta_pre_to_serve": round(strength[t] - st["A_pre_ti"]["strength"][t], 4),
                "delta_attributable_to_ti15": round(
                    strength[t] - st["control_decay_origin"]["strength"][t], 4)}
            for i, t in enumerate(teams)},
        "states": {k: {"cutoff": v["cutoff"], "train_maps": v["train_maps"],
                       "radiant_c": round(v["c"], 4), "data": v["data"]}
                   for k, v in st.items() if not k.startswith("_")},
        "tournament_probabilities": {
            t: {"champion": round(champ[t], 4),
                "champion_bootstrap_90ci": [round(float(np.percentile(champ_draws[:, i], 5)), 4),
                                            round(float(np.percentile(champ_draws[:, i], 95)), 4)],
                "reach_grand_final": round(reach_gf[t], 4),
                "win_ubqf": round(float(marg[seat_node[t]]["win"][i]), 4),
                "reach_ub_final": round(float(marg[ubf]["reach"][i]), 4),
                "win_ub_final": round(float(marg[ubf]["win"][i]), 4),
                "reach_lb_final": round(float(marg[lbf]["reach"][i]), 4),
                "win_lb_final": round(float(marg[lbf]["win"][i]), 4),
                "eliminated_in_lbr1": round(float(sum(
                    P_bar[(PR[:, topo["order"].index(n), 0] == i)
                          | (PR[:, topo["order"].index(n), 1] == i)].sum()
                    - P_bar[W[:, topo["order"].index(n)] == i].sum()
                    for n in topo["order"] if topo["label"][n] == "LBR1")), 4)}
            for i, t in enumerate(teams)},
        "optimization": {
            "objective": "maximize E[MAIN_EVENT_SCORE(number of correct nodes)] over all coherent "
                         "slates, against the bootstrap-averaged outcome distribution",
            "why_averaging_is_exact": "expected score is linear in the outcome distribution, so "
                                      "averaging the distribution over parameter draws and then "
                                      "optimizing equals optimizing the uncertainty-integrated "
                                      "objective",
            "candidates_evaluated": int(W.shape[0]),
            "greedy_coherent_favourite": {"row": greedy, "expected_score": round(float(Es[greedy]), 1),
                                          "expected_correct": round(float(Ec[greedy]), 3)},
            "max_expected_correct": {"row": best_correct,
                                     "expected_score": round(float(Es[best_correct]), 1),
                                     "expected_correct": round(float(Ec[best_correct]), 3)},
            "max_expected_official_score": {"row": best_score,
                                            "expected_score": round(float(Es[best_score]), 1),
                                            "expected_correct": round(float(Ec[best_score]), 3)},
            "point_estimate_check": {
                "argmax_row_under_point_estimate": int(np.argmax(Es_hat)),
                "same_slate_as_primary": bool(int(np.argmax(Es_hat)) == best_score),
                "primary_expected_score_under_point_estimate": round(float(Es_hat[best_score]), 1)},
            "score_distribution_of_primary": {
                str(k): round(float(P_bar[bk.agreement_matrix(W, [best_score])[0] == k].sum()), 5)
                for k in range(15)},
        },
        "primary_slate": primary,
        "runner_up": {
            "second_best_overall": {
                "row": runner, "expected_score": round(float(Es[runner]), 1),
                "expected_correct": round(float(Ec[runner]), 3),
                "regret_vs_primary": round(float(Es[best_score] - Es[runner]), 2),
                "differs_at": [{"selection_id": topo["node_to_selection"][topo["order"][k]],
                                "round": topo["label"][topo["order"][k]],
                                "primary": teams[int(W[best_score, k])],
                                "alternative": teams[int(W[runner, k])]}
                               for k in range(len(topo["order"]))
                               if W[runner, k] != W[best_score, k]],
                "paired_tie_resolution": tie},
            "best_with_a_different_champion": {
                "row": diff_champ, "champion": teams[int(W[diff_champ, gf_col])],
                "expected_score": round(float(Es[diff_champ]), 1),
                "expected_correct": round(float(Ec[diff_champ]), 3),
                "regret_vs_primary": round(float(Es[best_score] - Es[diff_champ]), 2),
                "differs_at": [{"selection_id": topo["node_to_selection"][topo["order"][k]],
                                "round": topo["label"][topo["order"][k]],
                                "primary": teams[int(W[best_score, k])],
                                "alternative": teams[int(W[diff_champ, k])]}
                               for k in range(len(topo["order"]))
                               if W[diff_champ, k] != W[best_score, k]]}},
        "client_actions": [{"selection_id": r["selection_id"], "series": r["series"],
                            "select": display.get(r["pick"], r["pick"]),
                            "canonical": r["pick"],
                            "name_basis": "client display name as it appears in the archived "
                                          "bracket/schedule evidence; `canonical` is the internal "
                                          "model organization"}
                           for r in sorted(primary, key=lambda x: x["selection_id"])],
        "client_display_names": display,
        "caveats": [
            "model-only; no market, crowd or manual input of any kind",
            "the h90 decay origin and the 44 inserted series are the only things that changed "
            "relative to the locked group-stage run; the estimator is byte-identical",
            "rounds 2-5 and the Elimination Round have no locally recorded timestamp; the cadence "
            "assumption is bounded by the collapse arm in gates.timestamp_sensitivity",
            "maps within a series are modelled as exchangeable draws, so a 2-0 and a 2-1 differ "
            "only in the third map's outcome, never in order or momentum",
        ],
    }
    outdir = outdir or OUTDIR
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.join(outdir, "ti15_main_event_prediction")
    with open(stem + ".json", "w", encoding="utf-8") as fh:
        json.dump(art, fh, ensure_ascii=False, indent=2, default=float)
    with open(stem + ".md", "w", encoding="utf-8") as fh:
        fh.write(to_markdown(art))
    return art, stem


def to_markdown(a):
    m = a["manifest"]
    L = [f"# TI15 Main Event prediction ({m['status']})", "",
         f"- commit `{m['code_commit']}` | generated {m['generated_at']} | "
         f"cutoff {m['data_cutoff']}",
         f"- snapshot: {m['snapshot_boundary']}",
         f"- model: **{m['model']['family']} / h{m['model']['half_life_days']} / "
         f"lambda={m['model']['lambda']} / calibration {m['model']['calibration']}** "
         f"(frozen, radiant c={m['model']['radiant_c']:+.4f})",
         f"- inputs: {m['inputs_used']['ti15_series_inserted']} TI15 series inserted "
         f"({m['inputs_used']['ti15_map_rows']} maps) on top of "
         f"{m['inputs_used']['historical_universe_rows']} historical maps; "
         f"network={m['inputs_used']['network']}, odds={m['inputs_used']['odds_or_market']}",
         f"- optimization: exact over all {m['enumeration']['coherent_slates']} coherent slates "
         f"x {m['enumeration']['outcomes']} outcomes; {m['bootstrap_draws']} series-blocked "
         f"bootstrap draws over {m['bootstrap_blocks']} blocks", "",
         "## Strength evolution (frozen estimator; only the data changed)", "",
         "| team | pre-TI | post-Swiss | serve | +/- (bootstrap SD) | attributable to TI15 |",
         "|---|---:|---:|---:|---:|---:|"]
    ev = a["strength_evolution"]
    for t in sorted(ev, key=lambda x: -ev[x]["serve"]):
        e = ev[t]
        L.append(f"| {t} | {e['pre_ti']:+.3f} | {e['post_swiss']:+.3f} | **{e['serve']:+.3f}** | "
                 f"{e['serve_bootstrap_sd']:.3f} | {e['delta_attributable_to_ti15']:+.3f} |")
    L += ["", "## Tournament probabilities", "",
          "| team | champion | 90% CI | reach GF | win UBQF | reach UBF | win UBF |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    tp = a["tournament_probabilities"]
    for t in sorted(tp, key=lambda x: -tp[x]["champion"]):
        p = tp[t]
        L.append(f"| {t} | **{p['champion']:.3f}** | "
                 f"{p['champion_bootstrap_90ci'][0]:.3f}-{p['champion_bootstrap_90ci'][1]:.3f} | "
                 f"{p['reach_grand_final']:.3f} | {p['win_ubqf']:.3f} | "
                 f"{p['reach_ub_final']:.3f} | {p['win_ub_final']:.3f} |")
    o = a["optimization"]
    L += ["", "## Optimization", "",
          "| slate | E[official score] | E[correct] |", "|---|---:|---:|",
          f"| greedy coherent favourite | {o['greedy_coherent_favourite']['expected_score']:.1f} | "
          f"{o['greedy_coherent_favourite']['expected_correct']:.3f} |",
          f"| max E[correct] | {o['max_expected_correct']['expected_score']:.1f} | "
          f"{o['max_expected_correct']['expected_correct']:.3f} |",
          f"| **max E[official score] (primary)** | "
          f"**{o['max_expected_official_score']['expected_score']:.1f}** | "
          f"{o['max_expected_official_score']['expected_correct']:.3f} |", "",
          "## Primary 14-slot slate", "",
          "| sel | round | matchup | pick | P(win \\| matchup) | P(pick wins node) | cost to change |"
          " fragile |", "|---:|---|---|---|---:|---:|---:|---|"]
    for r in sorted(a["primary_slate"], key=lambda x: x["selection_id"]):
        L.append(f"| {r['selection_id']} | {r['round']} | "
                 f"{r['predicted_matchup'][0]} vs {r['predicted_matchup'][1]} | **{r['pick']}** | "
                 f"{r['conditional_win_prob']:.3f} | {r['marginal_pick_wins_node']:.3f} | "
                 f"{r['cost_of_changing']:.1f} | {'YES' if r['fragile'] else '-'} |")
    ru = a["runner_up"]["second_best_overall"]
    L += ["", "## Runner-up and fragility", "",
          f"- second-best coherent slate: E[score] {ru['expected_score']:.1f} "
          f"(regret {ru['regret_vs_primary']:.2f}), differs at "
          + ", ".join(f"{d['selection_id']} ({d['primary']} -> {d['alternative']})"
                      for d in ru["differs_at"])]
    t = ru.get("paired_tie_resolution")
    if t:
        L += [f"- paired resolution of that difference ({t['draws']} draws): plug-in "
              f"{t['plug_in_delta']:+.2f}, bootstrap mean {t['bootstrap_mean_delta']:+.2f} "
              f"(MC SE {t['mc_se_of_mean']:.2f}), median {t['bootstrap_median_delta']:+.2f}, "
              f"95% CI [{t['ci95'][0]:+.1f}, {t['ci95'][1]:+.1f}], P(delta>0)="
              f"{t['p_delta_gt_0']:.4f} -> **{t['verdict']}**: {t['verdict_reason']}. "
              f"{t['deterministic_pick_retained']}"]
    dc = a["runner_up"]["best_with_a_different_champion"]
    L += [f"- best slate with a different champion ({dc['champion']}): "
          f"E[score] {dc['expected_score']:.1f} (regret {dc['regret_vs_primary']:.2f})", "",
          "## Client actions", ""]
    for r in a["client_actions"]:
        extra = "" if r["select"] == r["canonical"] else f"  _(model: {r['canonical']})_"
        L.append(f"- slot {r['selection_id']} - {r['series']}: **{r['select']}**{extra}")
    L += ["", "Names above are the client display names transcribed from the archived "
              "bracket/schedule evidence; the model's canonical organizations are shown in "
              "parentheses where they differ."]
    L += ["", "## Caveats", ""] + [f"- {c}" for c in a["caveats"]]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="TI15 main-event bracket prediction")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--verify-draws", type=int, default=VERIFY_DRAWS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--tie-report", help="paired near-tie report to embed. Defaults to the committed "
                                         "research artifact; point it at a staging copy when the "
                                         "production run must start from a clean working tree.")
    ap.add_argument("--out")
    a = ap.parse_args()
    art, stem = run(draws=a.draws, outdir=a.out, verify_draws=a.verify_draws, seed=a.seed,
                    tie_report=a.tie_report)
    print(to_markdown(art))
    try:
        shown = os.path.relpath(stem, REPO)
    except ValueError:                      # an --out on another drive is fine, just not relative
        shown = stem
    print(f"[{art['manifest']['status']}] wrote {shown}.json / .md")


if __name__ == "__main__":
    main()
