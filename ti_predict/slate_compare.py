"""Paired comparison of two coherent slates under the frozen serve state.

Answers one question and nothing else: given two candidate slates, is the expected OFFICIAL score
difference between them real, or is it inside the noise of the parameter estimate? Nothing here
selects a model, tunes a parameter, or touches the bracket, the data snapshot, or the completed
optimization -- it re-reads the same frozen serve state and re-prices two already-chosen slates.

The comparison is PAIRED by construction: both slates are scored against the same bootstrap draw, so
the per-draw difference removes the shared uncertainty about how strong the eight teams are and
isolates the disagreement at the nodes where the slates differ.

Two identities worth stating, because they make the output easy to read:
  - expected score is linear in the outcome distribution, so the bootstrap MEAN of the paired
    difference is exactly the difference evaluated under the bootstrap-averaged distribution. The
    "mean delta" and the "uncertainty-integrated delta" are the same number, not two estimates.
  - the plug-in delta (point-estimate strengths) carries no Monte-Carlo error at all; only the
    bootstrap quantities do.

Run: python -m ti_predict.slate_compare --node 810 --draws 20000
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict import bracket as bk
from ti_predict import predict_main_event as pme
from ti_predict import ti15_results as tr

CHECKPOINTS = (1000, 2500, 5000, 10000, 20000, 40000)


def compare(row_a, row_b, draws=20000, seed=pme.SEED, label_a="A", label_b="B"):
    """Paired bootstrap comparison of two coherent slates. Returns a report dict."""
    topo = bk.load_topology()
    seats = {nid: (tr.canon(x), tr.canon(y)) for nid, (x, y) in tr.UBQF.items()}
    teams, W, PR = bk.enumerate_structure(topo, seats)
    st = pme.build_states()
    serve = st["C_serve"]
    strength = {t: serve["strength"][t] for t in teams}
    c = serve["c"]

    diff_nodes = [topo["node_to_selection"][topo["order"][k]]
                  for k in range(len(topo["order"])) if W[row_a, k] != W[row_b, k]]

    # SCORE(K(slate, outcome)) for each slate against every outcome; the paired score difference
    # per outcome is then a fixed vector and each draw costs one dot product.
    K = bk.agreement_matrix(W, [row_a, row_b])
    dvec = bk.SCORE_VEC[K[0]] - bk.SCORE_VEC[K[1]]

    P_hat = bk.outcome_probs(topo, W, PR, teams, strength, c)
    plug_in = float(dvec @ P_hat)

    S, Cb, n_blocks = pme.bootstrap_strengths(rows := st["_rows"], st["_cuts"]["C"], teams,
                                              draws, seed=seed)
    d = np.empty(draws)
    for i in range(draws):
        P = bk.outcome_probs(topo, W, PR, teams, {t: S[i, j] for j, t in enumerate(teams)},
                             float(Cb[i]), check=False)
        P /= P.sum()
        d[i] = dvec @ P
    del rows

    conv = []
    for n in CHECKPOINTS:
        if n > draws:
            continue
        conv.append({"draws": n, "mean_delta": round(float(d[:n].mean()), 4),
                     "mc_se": round(float(d[:n].std(ddof=1) / np.sqrt(n)), 4),
                     "p_delta_gt_0": round(float((d[:n] > 0).mean()), 4)})
    se = float(d.std(ddof=1) / np.sqrt(draws))
    return {
        "comparison": f"{label_a} vs {label_b}",
        "slates": {"a_row": int(row_a), "b_row": int(row_b)},
        "differ_at_selection_ids": diff_nodes,
        "picks_at_differing_nodes": {
            str(topo["node_to_selection"][topo["order"][k]]):
                {label_a: teams[int(W[row_a, k])], label_b: teams[int(W[row_b, k])]}
            for k in range(len(topo["order"])) if W[row_a, k] != W[row_b, k]},
        "paired": True,
        "draws": int(draws), "seed": int(seed), "bootstrap_blocks": int(n_blocks),
        "plug_in_delta": round(plug_in, 4),
        "plug_in_note": "point-estimate strengths; exact, carries no Monte-Carlo error",
        "bootstrap_mean_delta": round(float(d.mean()), 4),
        "bootstrap_mean_note": "identical by linearity to the delta under the bootstrap-averaged "
                               "outcome distribution, which is the objective the slate was chosen on",
        "bootstrap_median_delta": round(float(np.median(d)), 4),
        "bootstrap_sd": round(float(d.std(ddof=1)), 4),
        "mc_se_of_mean": round(se, 4),
        "ci90": [round(float(np.percentile(d, 5)), 4), round(float(np.percentile(d, 95)), 4)],
        "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)],
        "p_delta_gt_0": round(float((d > 0).mean()), 4),
        "statistically_separated": False if ((np.percentile(d, 2.5) < 0 < np.percentile(d, 97.5)))
                                   else True,
        "convergence": conv,
        "reference_scale": {
            "expected_score_of_a": None, "score_step_1_correct": 120,
            "note": "read the delta against the ~2287-point expected score of either slate and "
                    "against the 120-point value of one extra correct node"},
    }


def verdict(rep, tie_band=0.05):
    """Decision-theoretic reading. `tie_band` is a fraction of one correct node (120 points)."""
    band = tie_band * 120.0
    ci_spans_zero = rep["ci95"][0] < 0 < rep["ci95"][1]
    tiny = abs(rep["bootstrap_mean_delta"]) < band
    if ci_spans_zero and tiny:
        return ("TIE", f"the paired 95% interval spans zero and the mean difference is under "
                       f"{band:.0f} points, {tie_band:.0%} of one correct node. The sign is NOT "
                       "resolved: this says the two slates are evidentially indistinguishable, not "
                       "that their true difference is zero")
    if ci_spans_zero:
        return ("INDISTINGUISHABLE", "the paired 95% interval spans zero")
    return ("SEPARATED", "the paired 95% interval excludes zero")


def main():
    ap = argparse.ArgumentParser(description="paired comparison of two coherent slates")
    ap.add_argument("--node", type=int, default=810,
                    help="client selection id at which the primary and its best alternative differ")
    ap.add_argument("--draws", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=pme.SEED)
    ap.add_argument("--json", help="write the report here")
    a = ap.parse_args()

    art = json.load(open(os.path.join(pme.OUTDIR, "ti15_main_event_prediction.json"),
                         encoding="utf-8"))
    row_a = art["optimization"]["max_expected_official_score"]["row"]
    ru = art["runner_up"]["second_best_overall"]
    if [d["selection_id"] for d in ru["differs_at"]] != [a.node]:
        raise SystemExit(f"the recorded runner-up does not differ from the primary at exactly "
                         f"slot {a.node}; it differs at "
                         f"{[d['selection_id'] for d in ru['differs_at']]}")
    row_b = ru["row"]
    pick = next(r for r in art["primary_slate"] if r["selection_id"] == a.node)
    rep = compare(row_a, row_b, draws=a.draws, seed=a.seed,
                  label_a="primary", label_b="alternative")
    rep["reference_scale"]["expected_score_of_a"] = \
        art["optimization"]["max_expected_official_score"]["expected_score"]
    rep["node_under_test"] = {
        "selection_id": a.node, "round": pick["round"], "series": pick["series"],
        "matchup": pick["predicted_matchup"],
        "conditional_win_prob_of_primary_pick": pick["conditional_win_prob"]}
    rep["verdict"], rep["verdict_reason"] = verdict(rep)

    print(f"slot {a.node}: {rep['picks_at_differing_nodes'][str(a.node)]}")
    print(f"  plug-in delta          {rep['plug_in_delta']:+.3f}")
    print(f"  bootstrap mean delta   {rep['bootstrap_mean_delta']:+.3f}  "
          f"(MC SE {rep['mc_se_of_mean']:.3f}, {rep['draws']} draws)")
    print(f"  bootstrap median delta {rep['bootstrap_median_delta']:+.3f}")
    print(f"  bootstrap SD           {rep['bootstrap_sd']:.3f}")
    print(f"  90% CI                 [{rep['ci90'][0]:+.2f}, {rep['ci90'][1]:+.2f}]")
    print(f"  95% CI                 [{rep['ci95'][0]:+.2f}, {rep['ci95'][1]:+.2f}]")
    print(f"  P(delta > 0)           {rep['p_delta_gt_0']:.4f}")
    print(f"  verdict                {rep['verdict']} - {rep['verdict_reason']}")
    print("  convergence:")
    for cpt in rep["convergence"]:
        print(f"    n={cpt['draws']:>6}  mean {cpt['mean_delta']:+.3f}  "
              f"MC SE {cpt['mc_se']:.3f}  P(>0) {cpt['p_delta_gt_0']:.4f}")
    if a.json:
        os.makedirs(os.path.dirname(a.json), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1, default=float)
        print(f"  wrote {a.json}")


if __name__ == "__main__":
    main()
