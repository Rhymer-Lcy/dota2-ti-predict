"""How much would LGD's strength have to move before the slate changes? (RESEARCH)

Four days before TI15, LGD replaced its position-2 player: TaiLung was banned for tournament
integrity and Topson -- retired since 2024-09, with no official match since -- joined
(data/ti2026/inputs/roster_events.csv). The production model is ORGANIZATION-level: LGD's strength is
estimated from LGD's own match history, which was played by the previous lineup. Nothing in that
history describes the new lineup, and Topson's history describes a different organization, so neither
may be transplanted. No strength is edited here and no prior about the replacement is asserted.

Instead the question is inverted into one the model can answer honestly:

    Given that LGD's strength is now MORE uncertain than the estimate's own standard error,
    how large a shift would it take to change the final 16-slot slate?

Method:
  sigma   -- event-blocked bootstrap: resample the training leagues with replacement, refit the
             frozen B-bt (half-life 90) on each resample, and take the standard deviation of LGD's
             strength. This is the model's own estimation error, not a guess about Topson.
  grid    -- baseline and baseline +/- {0.5, 1.0, 1.5} sigma, plus quantiles of the bootstrap
             distribution itself, plus a fine scan to locate the slate-change threshold.
  common random numbers -- every scenario reuses one seed, so a slate difference is the perturbation,
             not Monte-Carlo noise.

Structure: the open 16-team Swiss with the posted round 1 (backtest2/post_r1.py establishes that the
open and two-pod families produce the same slate, so the pod hypothesis is not re-marginalized inside
every scenario). Everything else is the frozen production configuration.

Run: python -m backtest2.roster_sensitivity [--team "LGD Gaming"] [--sims N] [--boot N]
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS, GROUP_LOCK_UTC, GROUP_SCORE, PRODUCTION_HALF_LIFE_DAYS
from ti_predict.predict_ti15 import bt_strengths_for, load_teams, parse_cutoff, resolve_draw
from ti_predict.swiss import map_pn, monte_carlo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAW = os.path.join(REPO, "data", "ti2026", "inputs", "draw.json")
BIDX = {b: i for i, b in enumerate(BUCKETS)}
FVEC = np.array([GROUP_SCORE[k] for k in range(17)])


def bootstrap_strengths(cut_ts, teams, n_boot=300, seed=20260810, block="event"):
    """Bootstrap the frozen B-bt fit; returns {team: [log-strength draws]}.

    block="event"  -- resample whole leagues with replacement. Conservative: it also prices in WHICH
                      events a team happened to play, so for a team whose maps sit in two or three
                      leagues some resamples drop most of its record.
    block="series" -- resample series within the training set, keeping the event mix fixed. This
                      isolates match-level sampling error.
    Neither is a statement about the roster; both measure how well the DATA pins the organization.
    """
    from ti_predict.backtest import load
    from ti_predict.calibrate import bt_strengths
    uni, _, _ = load()
    train = [m for m in uni if m["start_time"] < cut_ts]
    key = (lambda m: m["leagueid"]) if block == "event" else (
        lambda m: m["series_id"] or f"m{m['match_id']}")
    blocks = defaultdict(list)
    for m in train:
        blocks[key(m)].append(m)
    keys = list(blocks)
    rng = random.Random(seed)
    draws = {t: [] for t in teams}
    for _ in range(n_boot):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        sample = [m for k in pick for m in blocks[k]]
        sample.sort(key=lambda m: m["start_time"])
        sm = bt_strengths(sample, cut_ts, hl=PRODUCTION_HALF_LIFE_DAYS)
        for t in teams:
            if t in sm:
                draws[t].append(float(sm[t]))
    return draws


def run_scenario(strength, teams, r1, c, n, seed):
    """One Monte-Carlo run under the open structure; returns (P, assignment, archive)."""
    P, arch = monte_carlo((list(teams),), strength, n=n, seed=seed, r1_pairings=r1,
                          elim_choice="strategic", c=c, return_archive=True)
    arch = {t: np.asarray(v, dtype=np.int8) for t, v in arch.items()}
    _, _, rows = assign(P)
    return P, {t: b for t, b, _ in rows}, arch


def expected_points(asg, arch):
    n = len(next(iter(arch.values())))
    K = np.zeros(n, dtype=np.int16)
    for t, b in asg.items():
        K += arch[t] == BIDX[b]
    return float(FVEC[K].mean())


def main():
    ap = argparse.ArgumentParser(description="roster-change sensitivity of the 16-slot slate")
    ap.add_argument("--team", default="LGD Gaming")
    ap.add_argument("--cutoff", default=GROUP_LOCK_UTC)
    ap.add_argument("--sims", type=int, default=40000)
    ap.add_argument("--boot", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--out", default=os.path.join(REPO, "predictions", "ti2026", "group-stage",
                                                  "research"))
    a = ap.parse_args()

    rows = load_teams()
    teams = [t["team"] for t in rows]
    cut_ts, cut_iso = parse_cutoff(a.cutoff)
    base_strength, c, n_train, uni_rows, _ = bt_strengths_for(rows, cut_ts)
    _, r1, _ = resolve_draw(rows, DRAW)
    tgt = a.team
    if tgt not in base_strength:
        raise SystemExit(f"unknown team {tgt!r}")

    draws = {b: bootstrap_strengths(cut_ts, teams, n_boot=a.boot, seed=a.seed, block=b)
             for b in ("event", "series")}
    sigma = {b: {t: float(np.std(v, ddof=1)) for t, v in d.items() if len(v) > 1}
             for b, d in draws.items()}
    s_t = sigma["event"][tgt]                    # headline: the conservative block
    q = {f"q{int(p*100):02d}": round(float(np.quantile(draws["event"][tgt], p)), 4)
         for p in (0.05, 0.25, 0.5, 0.75, 0.95)}

    r1_opp = next((x for pair in r1 for x in pair if x != tgt and tgt in pair), None)

    base_P, base_asg, base_arch = run_scenario(base_strength, teams, r1, c, a.sims, a.seed)
    base_pts = expected_points(base_asg, base_arch)

    def scenario(delta):
        """Re-run the whole decision layer with the target's strength shifted by `delta`.

        Reported both ways, because they answer different questions:
          target_slot / slot_changed -- does the perturbation move the TEAM's own slot?
          regret                     -- expected correct lost by submitting the BASELINE slate in a
                                        world where the perturbed strength is true. Near-tied
                                        mid-table pairs re-order at tiny deltas, which shows up as
                                        `teams_moved` while costing essentially nothing; regret is
                                        what says whether a re-order matters.
        """
        s = dict(base_strength); s[tgt] = base_strength[tgt] + delta
        P, asg, arch = run_scenario(s, teams, r1, c, a.sims, a.seed)   # same seed for every scenario
        p_map = map_pn(s[r1_opp], s[tgt], c) if r1_opp else None       # opponent's win prob
        moved = sorted(t for t in teams if asg[t] != base_asg[t])
        exp_scen = sum(P[t][asg[t]] for t in teams)
        exp_base = sum(P[t][base_asg[t]] for t in teams)
        return {"delta": round(delta, 4), "delta_sigma": round(delta / s_t, 2),
                "strength": round(s[tgt], 4),
                "r1_opponent_map_p": round(p_map, 4) if p_map is not None else None,
                "r1_opponent_series_p": round(p_map * p_map * (3 - 2 * p_map), 4)
                if p_map is not None else None,
                "target_buckets": {b: round(P[tgt][b], 4) for b in BUCKETS},
                "target_slot": asg[tgt], "slot_changed": asg[tgt] != base_asg[tgt],
                "teams_moved": moved,
                "expected_correct": round(exp_scen, 3),
                "regret_of_baseline_slate": round(exp_scen - exp_base, 4),
                "expected_points": round(expected_points(asg, arch), 1)}

    grid = [scenario(k * s_t) for k in (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)]
    boot_q = [scenario(float(np.quantile(draws["event"][tgt], p)) - base_strength[tgt])
              for p in (0.05, 0.5, 0.95)]

    # Threshold on the target's OWN slot: monotone in delta, so bisect. This is the number that
    # answers "how far would LGD have to move before our pick for LGD changes".
    thresholds = {}
    for name, sign in (("down", -1), ("up", 1)):
        lo, hi = 0.0, sign * 3.0
        if not scenario(hi)["slot_changed"]:
            thresholds[name] = {"delta": None, "delta_sigma": None,
                                "note": "target slot unchanged out to +/-3.0 log-strength"}
            continue
        for _ in range(9):                       # bisect to ~0.006 log-strength
            mid = 0.5 * (lo + hi)
            if scenario(mid)["slot_changed"]:
                hi = mid
            else:
                lo = mid
        sc = scenario(hi)
        thresholds[name] = {"delta": round(hi, 3), "delta_sigma": round(hi / s_t, 2),
                            "new_slot": sc["target_slot"], "teams_moved": sc["teams_moved"],
                            "regret_of_baseline_slate": sc["regret_of_baseline_slate"]}

    out = {"status": "RESEARCH - roster-change sensitivity; production strengths unchanged",
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "team": tgt, "cutoff": cut_iso, "structure": "open-16 with the posted round 1",
           "sims_per_scenario": a.sims, "seed": a.seed, "bootstrap_resamples": a.boot,
           "training_maps": n_train, "universe_rows": uni_rows,
           "baseline_strength": round(base_strength[tgt], 4),
           "baseline_rank": 1 + sorted(base_strength.values(), reverse=True).index(
               base_strength[tgt]),
           "baseline_slot": base_asg[tgt],
           "baseline_buckets": {b: round(base_P[tgt][b], 4) for b in BUCKETS},
           "baseline_expected_correct": round(sum(base_P[t][base_asg[t]] for t in teams), 3),
           "baseline_expected_points": round(base_pts, 1),
           "sigma_event_blocked_bootstrap": round(s_t, 4),
           "sigma_series_blocked_bootstrap": round(sigma["series"][tgt], 4),
           "sigma_all_teams_event_blocked": {t: round(v, 4) for t, v in
                                             sorted(sigma["event"].items(), key=lambda x: -x[1])},
           "sigma_all_teams_series_blocked": {t: round(v, 4) for t, v in
                                              sorted(sigma["series"].items(), key=lambda x: -x[1])},
           "bootstrap_quantiles_event_blocked": q,
           "r1_opponent": r1_opp,
           "scenarios_sigma_grid": grid, "scenarios_bootstrap_quantiles": boot_q,
           "target_slot_change_threshold": thresholds,
           "interpretation": "the pick for this team is unchanged for every perturbation strictly "
                             "inside the threshold. Mid-table teams whose bucket probabilities are "
                             "near-tied re-order at much smaller deltas; read regret_of_baseline_"
                             "slate, not teams_moved, to judge whether such a re-order matters."}
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"roster_sensitivity_{tgt.replace(' ', '_').lower()}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"{tgt}: strength {out['baseline_strength']:+.4f} (rank {out['baseline_rank']}/16), "
          f"slot {out['baseline_slot']}")
    print(f"bootstrap sigma: event-blocked {s_t:.4f} | series-blocked "
          f"{sigma['series'][tgt]:.4f}  (event-blocked 5-95%: {q['q05']:+.3f} .. {q['q95']:+.3f})")
    print(f"round-1 opponent: {r1_opp}")
    print(f"{'delta':>8}{'sigma':>7}{'slot':>16}{'expC':>8}{'regret':>8}{'expPts':>9}  moved")
    for g in grid:
        print(f"{g['delta']:+8.3f}{g['delta_sigma']:+7.1f}{g['target_slot']:>16}"
              f"{g['expected_correct']:>8.2f}{g['regret_of_baseline_slate']:>8.3f}"
              f"{g['expected_points']:>9.0f}  {', '.join(g['teams_moved']) or '-'}")
    print("target-slot change threshold: " + json.dumps(thresholds))
    print("wrote " + os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
