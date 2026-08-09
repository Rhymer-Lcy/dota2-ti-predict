"""Pre-draw research: marginalize the group-stage forecast over the unknown official draw.

RESEARCH / DRY-RUN ONLY. The official two-pod split and round-1 pairings are not yet published; this
study quantifies how much the unknown draw matters by (a) computing draw-MARGINAL bucket
probabilities under sampled legal draws, (b) measuring slate stability across individual draws, and
(c) comparing against the single fixed synthetic draw used by earlier rehearsals. It never emits an
official prediction; once the real draw posts, the post-draw official path
(ti_predict.predict_ti15 --official) is the only valid route.

Draw scenarios (the official pod/seeding mechanism is unpublished; only 'uniform' is implied by the
known constraints, the others are labeled sensitivity mechanisms, not official rules):
  uniform  - pods: uniform random 8/8 split; round 1 random within pods (the neutral legal draw).
  banded   - pods: teams ranked by model strength into four bands of 4; each pod receives 2 per band
             (a plausible strength-balancing mechanism).
  region   - pods: same-region teams spread as evenly as possible across pods (a plausible
             region-separation mechanism); round 1 random within pods.

Outputs backtest2/reports/pre_draw.json and prints a decision-level summary.
Run: python -m backtest2.pre_draw --strengths bt --cutoff 2026-08-02T00:00:00Z
(the default cutoff matches the end of the locally available universe; strengths are therefore
"as of 2026-08-01 data" until the lock-day refresh).
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.predict_ti15 import bt_strengths_for, load_teams, parse_cutoff, synthetic_strengths
from ti_predict.swiss import simulate_one, monte_carlo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = ("uniform", "banded", "region")
DEFAULT_CUTOFF = "2026-08-02T00:00:00Z"      # end of locally available universe data


def sample_pods(names, scenario, rng, strength=None, region=None):
    """Sample one legal two-pod split under the scenario's mechanism."""
    if scenario == "uniform":
        order = list(names)
        rng.shuffle(order)
        return order[:8], order[8:]
    if scenario == "banded":
        ranked = sorted(names, key=lambda t: -strength[t])
        podA, podB = [], []
        for i in range(0, 16, 4):
            band = ranked[i:i + 4]
            rng.shuffle(band)
            podA += band[:2]
            podB += band[2:]
        return podA, podB
    if scenario == "region":
        podA, podB = [], []
        groups = defaultdict(list)
        for t in names:
            groups[region[t]].append(t)
        for _, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            members = list(members)
            rng.shuffle(members)
            for t in members:
                (podA if len(podA) <= len(podB) else podB).append(t)
        assert len(podA) == 8 and len(podB) == 8, (len(podA), len(podB))
        return podA, podB
    raise ValueError(scenario)


def marginal_P(names, scenario, strength, region, n, seed, c):
    """Draw-marginal bucket probabilities: a fresh sampled draw for every simulation."""
    tally = {t: {b: 0 for b in BUCKETS} for t in names}
    for k in range(n):
        base = seed * 1_000_003 + k
        pods = sample_pods(names, scenario, random.Random(base * 5 + 1), strength, region)
        bucket = simulate_one(pods, strength, random.Random(base * 5 + 2), None, "strategic", c=c)
        for t, b in bucket.items():
            tally[t][b] += 1
    return {t: {b: tally[t][b] / n for b in BUCKETS} for t in names}


def per_draw_stability(names, scenario, strength, region, k_draws, m_sims, seed, c):
    """Assignment stability across individual draws: slot frequency per team + E[correct] range."""
    freq = {t: defaultdict(int) for t in names}
    exp_corrects = []
    for d in range(k_draws):
        pods = sample_pods(names, scenario, random.Random(seed * 7919 + d), strength, region)
        P = monte_carlo(pods, strength, n=m_sims, seed=seed + 31 * d, c=c)
        slate, exp_c, rows = assign(P)
        exp_corrects.append(exp_c)
        for t, b, _ in rows:
            freq[t][b] += 1
    stable = {t: max(freq[t].items(), key=lambda kv: kv[1]) for t in names}
    return ({t: {b: n_ / k_draws for b, n_ in freq[t].items()} for t in names},
            {t: (b, n_ / k_draws) for t, (b, n_) in stable.items()},
            (min(exp_corrects), sum(exp_corrects) / len(exp_corrects), max(exp_corrects)))


def main():
    ap = argparse.ArgumentParser(description="Pre-draw marginalization study (research dry-run)")
    ap.add_argument("--strengths", choices=("synthetic", "bt"), default="bt")
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                    help="data cutoff for B-bt strengths (default: end of available universe)")
    ap.add_argument("--sims", type=int, default=12000, help="sims per scenario for the marginal P")
    ap.add_argument("--draws", type=int, default=40, help="fixed draws for the stability study")
    ap.add_argument("--sims-per-draw", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260809)
    a = ap.parse_args()

    teams = load_teams()
    names = [t["team"] for t in teams]
    region = {t["team"]: t["region"] for t in teams}
    if a.strengths == "bt":
        cut_ts, cut_iso = parse_cutoff(a.cutoff)
        strength, c, n_train, _, _ = bt_strengths_for(teams, cut_ts)
        ssrc = f"B-bt @ {cut_iso} ({n_train} training maps, radiant c={c:+.3f})"
    else:
        strength, c, ssrc = synthetic_strengths(teams), 0.0, "synthetic (non-predictive)"

    out = {"status": "PRE-DRAW RESEARCH DRY-RUN - NOT an official prediction",
           "strengths": ssrc, "seed": a.seed,
           "marginal_sims": a.sims, "stability_draws": a.draws, "sims_per_draw": a.sims_per_draw,
           "scenarios": {}}

    marg_slates = {}
    for sc in SCENARIOS:
        P = marginal_P(names, sc, strength, region, a.sims, a.seed, c)
        slate, exp_c, rows = assign(P)
        freq, stable, ec_range = per_draw_stability(names, sc, strength, region, a.draws,
                                                    a.sims_per_draw, a.seed, c)
        marg_slates[sc] = {t: b for t, b, _ in rows}
        out["scenarios"][sc] = {
            "marginal_P": {t: {b: round(P[t][b], 4) for b in BUCKETS} for t in names},
            "marginal_slate": {b: sorted([t for t, bb, _ in rows if bb == b]) for b in BUCKETS},
            "marginal_expected_correct": round(exp_c, 3),
            "per_draw_modal_slot": {t: {"bucket": stable[t][0], "share": round(stable[t][1], 3)}
                                    for t in names},
            "expected_correct_over_draws": {"min": round(ec_range[0], 3),
                                            "mean": round(ec_range[1], 3),
                                            "max": round(ec_range[2], 3)},
        }

    # fixed synthetic split used by earlier rehearsals, for comparison
    fixed_pods = (names[0::2], names[1::2])
    P_fixed = monte_carlo(fixed_pods, strength, n=a.sims, seed=a.seed, c=c)
    slate_f, exp_f, rows_f = assign(P_fixed)
    fixed_assign = {t: b for t, b, _ in rows_f}
    out["fixed_synthetic_draw"] = {
        "slate": {b: sorted([t for t, bb, _ in rows_f if bb == b]) for b in BUCKETS},
        "expected_correct": round(exp_f, 3),
        "slots_differing_vs_uniform_marginal":
            sorted(t for t in names if fixed_assign[t] != marg_slates["uniform"][t]),
    }
    agree_bu = sorted(t for t in names if marg_slates["banded"][t] == marg_slates["uniform"][t])
    agree_ru = sorted(t for t in names if marg_slates["region"][t] == marg_slates["uniform"][t])
    stable_all = sorted(t for t in names
                        if len({marg_slates[sc][t] for sc in SCENARIOS}) == 1)
    out["cross_scenario"] = {
        "teams_with_same_slot_in_all_scenarios": stable_all,
        "n_stable_of_16": len(stable_all),
        "banded_vs_uniform_agreement": len(agree_bu),
        "region_vs_uniform_agreement": len(agree_ru),
    }

    outdir = os.path.join(REPO, "backtest2", "reports")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "pre_draw.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[{out['status']}]")
    print(f"strengths = {ssrc}\n")
    for sc in SCENARIOS:
        s = out["scenarios"][sc]
        print(f"--- scenario: {sc} ---")
        print(f"  marginal E[correct] = {s['marginal_expected_correct']}   "
              f"per-draw E[correct] min/mean/max = "
              f"{s['expected_correct_over_draws']['min']}/"
              f"{s['expected_correct_over_draws']['mean']}/"
              f"{s['expected_correct_over_draws']['max']}")
        for b in BUCKETS:
            print(f"  {b:>13}: {', '.join(s['marginal_slate'][b])}")
    cs = out["cross_scenario"]
    print(f"\nslot identical across all 3 scenarios: {cs['n_stable_of_16']}/16 -> "
          f"{', '.join(cs['teams_with_same_slot_in_all_scenarios'])}")
    print(f"fixed synthetic draw differs from uniform marginal on: "
          f"{', '.join(out['fixed_synthetic_draw']['slots_differing_vs_uniform_marginal']) or 'none'}")
    print("\nwrote backtest2/reports/pre_draw.json")


if __name__ == "__main__":
    main()
