"""R1-fixed / pods-latent provisional group-stage prediction (RESEARCH, never OFFICIAL).

State it models: Valve's league feed publishes the eight round-1 pairings (r1_status=official) but no
pod partition (pods_status=unresolved). The official pipeline fails closed on that, and rightly so.
This runner answers the question the frozen pipeline cannot yet answer -- what the slate looks like
with the REAL round 1 fixed and the pod structure marginalized out.

What is uncertain is the pod MEMBERSHIP, not the structure. The official TI15 rules state the
two-pod format: round 1 splits the 16 into two initial groups and pairs within them, rounds 2-3 pair
inside a team own initial group, round 4 pairs against the other group. Only the eight-team split
itself is unpublished. Round 1 is known and never crosses pods, so a pod is exactly a union of four
of the eight posted matches: C(8,4)/2 = 35 admissible memberships, none distinguishable by evidence.

  two-pod (HEADLINE)   -- uniform marginalization over those 35 memberships. This is the official
                          format and the only basis for a submission.
  open-16 (COMPARATOR) -- one undivided 16-team pool with no pod constraint at all. NOT the official
                          format; simulated only to bound how much the pod constraint moves
                          anything, i.e. the extreme case of "membership does not matter".

Everything downstream of the structure is the FROZEN production configuration: identity side-neutral
B-bt, half-life 90, no calibration, side-neutral map probability with the train-only radiant
coefficient, Hungarian assignment plus the verified points refinement. No parameter is tuned here.

Run: python -m backtest2.post_r1 [--cutoff ISO] [--sims-per-hypothesis N] [--out DIR]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS, CAPACITY, GROUP_LOCK_UTC, PRODUCTION_HALF_LIFE_DAYS
from ti_predict.predict_ti15 import (bt_strengths_for, draw_status, load_teams, parse_cutoff,
                                     points_refinement, resolve_draw, se)
from ti_predict.rosters import roster_audit
from ti_predict.swiss import (admissible_two_pod_partitions, d4_sensitivity_crn,
                              map_pn, monte_carlo)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAW = os.path.join(REPO, "data", "ti2026", "inputs", "draw.json")
BIDX = {b: i for i, b in enumerate(BUCKETS)}


def pod_hypotheses(r1):
    """Every two-pod membership compatible with the posted round 1 (a pod = 4 whole matches)."""
    return admissible_two_pod_partitions(r1)


def structures(r1, teams):
    """[(family, label, pods)] -- every admissible two-pod membership, plus the open-16 comparator."""
    out = [("open", "open-16", (list(teams),))]
    for i, pods in enumerate(pod_hypotheses(r1)):
        out.append(("two-pod", f"two-pod-{i:02d}", pods))
    return out


def family_archives(strength, r1, teams, c, sims_per_hyp, seed):
    """Simulate every structure; return {family: {label: archive}} with equal sims per hypothesis."""
    out = {"open": {}, "two-pod": {}}
    n_pod = sum(1 for f, _, _ in structures(r1, teams) if f == "two-pod")
    for k, (fam, label, pods) in enumerate(structures(r1, teams)):
        # the open family gets the same TOTAL number of simulations as the two-pod family, so a
        # 50/50 family mixture is a plain concatenation of the two archives
        n = sims_per_hyp * n_pod if fam == "open" else sims_per_hyp
        _, arch = monte_carlo(pods, strength, n=n, seed=seed + 1009 * k, r1_pairings=r1,
                              elim_choice="strategic", c=c, return_archive=True)
        out[fam][label] = {t: np.asarray(v, dtype=np.int8) for t, v in arch.items()}
    return out


def _P(arch):
    n = len(next(iter(arch.values())))
    return {t: {b: float((v == BIDX[b]).sum()) / n for b in BUCKETS} for t, v in arch.items()}


def _concat(archs):
    teams = list(next(iter(archs)).keys())
    return {t: np.concatenate([a[t] for a in archs]) for t in teams}


def provisional(strength, r1, teams, c, sims_per_hyp=3000, seed=20260813):
    """Run the full hypothesis space and return the mixture result plus per-family diagnostics."""
    fam = family_archives(strength, r1, teams, c, sims_per_hyp, seed)
    fam_arch = {f: _concat(list(d.values())) for f, d in fam.items()}
    mix = fam_arch["two-pod"]              # HEADLINE: official structure, membership-marginalized
    P = {f: _P(a) for f, a in fam_arch.items()}
    P["mixture"] = _P(mix)

    slates = {}
    for key in ("open", "two-pod", "mixture"):
        _, exp_correct, rows = assign(P[key])
        slates[key] = ({t: b for t, b, _ in rows}, exp_correct)

    # per-hypothesis slate: how much of the slate the unpublished structure could move at all
    per_hyp = {}
    for f, d in fam.items():
        for label, a in d.items():
            _, _, rows = assign(_P(a))
            per_hyp[label] = {t: b for t, b, _ in rows}
    return {"P": P, "slates": slates, "mixture_archive": mix, "per_hypothesis": per_hyp,
            "n_mixture": len(next(iter(mix.values()))), "family_archives": fam_arch}


def refined_slate(res, strength, r1, teams, c, sims_per_hyp, seed):
    """Hungarian slate + the verified points refinement on an INDEPENDENT mixture archive."""
    asgA = res["slates"]["mixture"][0]
    ver = provisional(strength, r1, teams, c, sims_per_hyp, seed + 424243)["mixture_archive"]
    return points_refinement(asgA, res["mixture_archive"], ver, seed + 7)


def r1_probabilities(strength, r1, c):
    """Side-neutral map and Bo3 series win probability for each posted round-1 match."""
    out = []
    for a, b in r1:
        p = map_pn(strength[a], strength[b], c)
        out.append({"a": a, "b": b, "map_p_a": round(p, 4),
                    "series_p_a": round(p * p * (3 - 2 * p), 4)})
    return out


def main():
    ap = argparse.ArgumentParser(description="R1-fixed / pods-latent provisional prediction")
    ap.add_argument("--cutoff", default=GROUP_LOCK_UTC)
    ap.add_argument("--sims-per-hypothesis", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--draw", default=DRAW)
    ap.add_argument("--out", default=os.path.join(REPO, "predictions", "ti2026", "group-stage",
                                                  "research"))
    a = ap.parse_args()

    teams_rows = load_teams()
    teams = [t["team"] for t in teams_rows]
    cut_ts, cut_iso = parse_cutoff(a.cutoff)
    strength, c, n_train, uni_rows, uni_max = bt_strengths_for(teams_rows, cut_ts)
    _, r1, src = resolve_draw(teams_rows, a.draw)
    if r1 is None:
        raise SystemExit("draw file carries no r1_pairings; nothing to fix")
    state = draw_status(a.draw)
    rosters = roster_audit(orgs=teams)

    res = provisional(strength, r1, teams, c, a.sims_per_hypothesis, a.seed)
    refine_asg, refine = refined_slate(res, strength, r1, teams, c, a.sims_per_hypothesis, a.seed)
    P = res["P"]["mixture"]
    n = res["n_mixture"]

    # structural (pod) uncertainty, measured two ways:
    #   family_delta -- max |P_open - P_two-pod| per team. Each family pools the same number of
    #     simulations, so this is the actual size of the structural effect (MC se ~0.0015 per cell).
    #   disagree     -- how many single hypotheses assign a different slot than the mixture slate.
    #     Each individual hypothesis carries only sims_per_hypothesis simulations, so this mixes the
    #     structural effect with Monte-Carlo noise: read it as an UPPER bound, not an estimate.
    base = res["slates"]["mixture"][0]
    hyp_labels = list(res["per_hypothesis"])
    disagree = {t: sum(1 for h in hyp_labels if res["per_hypothesis"][h][t] != base[t])
                for t in teams}
    family_delta = {t: round(max(abs(res["P"]["open"][t][b] - res["P"]["two-pod"][t][b])
                                 for b in BUCKETS), 4) for t in teams}

    # D4 opponent-choice sensitivity under the open structure with the real round 1
    d4 = d4_sensitivity_crn(pod_hypotheses(r1)[0], strength, n=max(4000, a.sims_per_hypothesis * 4),
                            seed=a.seed, r1_pairings=r1, c=c)
    d4_slates = {sc: {t: b for t, b, _ in assign(d4[sc])[2]} for sc in d4}
    d4_moves = sorted(t for t in teams if len({d4_slates[sc][t] for sc in d4_slates}) > 1)

    per_team = {}
    for t in teams:
        b = refine_asg[t]
        ranked = sorted(BUCKETS, key=lambda x: -P[t][x])
        second = ranked[1] if ranked[0] == b else ranked[0]
        per_team[t] = {"assigned": b, "p": round(P[t][b], 4), "mc_se": round(se(P[t][b], n), 4),
                       "second_best": second, "second_p": round(P[t][second], 4),
                       "gap": round(P[t][b] - P[t][second], 4),
                       "structural_family_delta": family_delta[t],
                       "pod_hypotheses_disagreeing": disagree[t], "n_pod_hypotheses": len(hyp_labels),
                       "d4_sensitive": t in d4_moves}

    out = {
        "status": "RESEARCH - R1-fixed / pods-latent provisional; NOT the official prediction",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "r1_status": state["r1_status"], "structure": state["structure"],
        "structure_status": state["structure_status"],
        "pod_membership_status": state["pod_membership_status"],
        "structure_evidence": state["structure_evidence"],
        "pod_membership_evidence": state["pod_membership_evidence"],
        "pod_uncertainty_assumptions": {
            "headline_structure": "two_pod (official rule; membership marginalized)",
            "admissible_memberships": len(hyp_labels) - 1,
            "membership_prior": "uniform over every membership compatible with the posted round 1",
            "comparator": "open-16, simulated only to bound the size of the pod constraint; it is "
                          "NOT the official format and never the basis of a submission",
            "note": "the two-pod structure is confirmed by the official rules; only WHICH eight "
                    "teams form each group is unpublished, so membership is marginalized"},
        "draw_source": src, "feed_sha256": state["feed_sha256"],
        "draw_retrieved_at": state["retrieved_at"],
        "cutoff": cut_iso, "half_life_days": PRODUCTION_HALF_LIFE_DAYS,
        "radiant_c": round(c, 4), "training_maps": n_train, "universe_rows": uni_rows,
        "universe_max_start_time": datetime.fromtimestamp(uni_max, timezone.utc).isoformat(),
        "sims_per_hypothesis": a.sims_per_hypothesis, "n_mixture_sims": n, "seed": a.seed,
        "roster_audit": rosters,
        "r1_probabilities": r1_probabilities(strength, r1, c),
        "strengths": {t: round(strength[t], 4) for t in sorted(teams, key=lambda x: -strength[x])},
        "slate": {b: sorted([t for t in teams if refine_asg[t] == b],
                            key=lambda t: -P[t][b]) for b in BUCKETS},
        "family_slates": {k: {b: sorted([t for t in teams if v[0][t] == b], key=lambda t: -P[t][b])
                              for b in BUCKETS} for k, v in res["slates"].items()},
        "comparator_agrees_with_official_structure":
            (res["slates"]["open"][0] == res["slates"]["two-pod"][0]),
        "families_agree": (res["slates"]["open"][0] == res["slates"]["two-pod"][0]),
        "max_structural_family_delta": round(max(family_delta.values()), 4),
        "family_probabilities": {k: {t: {b: round(res["P"][k][t][b], 4) for b in BUCKETS}
                                     for t in teams} for k in ("open", "two-pod")},
        "points_refinement": refine,
        "expected_correct": round(sum(P[t][refine_asg[t]] for t in teams), 3),
        "d4_sensitive_teams": d4_moves,
        "probabilities": {t: {b: round(P[t][b], 4) for b in BUCKETS} for t in teams},
        "per_team": per_team,
    }
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "ti15_post_r1_provisional.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[{out['status']}]")
    print(f"r1_status={out['r1_status']} structure={out['structure']} "
          f"({out['structure_status']}) membership={out['pod_membership_status']} "
          f"| admissible memberships={len(hyp_labels) - 1} | headline sims={n}")
    print(f"two-pod slate == open-16 comparator slate: {out['families_agree']} | largest per-cell "
          f"difference: {out['max_structural_family_delta']:.4f}")
    print(f"expected correct = {out['expected_correct']} / 16")
    for b in BUCKETS:
        print(f"  {b:>12} x{CAPACITY[b]}: " + ", ".join(
            f"{t} ({P[t][b]:.2f})" for t in out["slate"][b]))
    print("\nround 1 (side-neutral map / Bo3 series win prob for the first-named team):")
    for m in out["r1_probabilities"]:
        print(f"  {m['a']:<18} vs {m['b']:<18} map {m['map_p_a']:.3f}  series {m['series_p_a']:.3f}")
    print(f"\npoints refinement: {refine['rule']} | proposed {refine['proposed_moves']} | "
          f"adopted={refine['adopted']}")
    print("wrote " + os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
