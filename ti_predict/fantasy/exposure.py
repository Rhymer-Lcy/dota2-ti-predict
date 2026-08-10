"""Schedule exposure: how many series a team gets, and what an extra draw is worth.

A fantasy period keeps the BEST series, so a team's period score is the maximum of however many
series it plays. That makes schedule length worth something on its own: a team that plays six series
draws six times from its distribution and keeps the best, which beats a team of identical strength
that draws four times. This module puts a number on that.

Exposure is read from the frozen group-stage track and never recomputed here. The Swiss format fixes
the mapping exactly -- a team plays until four wins or four losses, and the ten teams that reach the
elimination round play one more series -- so the frozen track's per-team bucket probabilities ARE
the exposure distribution. Nothing in the frozen model is re-run, re-tuned or re-read beyond its
published output.
"""
import argparse
import glob
import json
import os
import random

from ti_predict.fantasy import baseline as bl

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CANDIDATES = os.path.join(REPO, "predictions", "ti2026", "group-stage", "candidates", "*.json")

# Series played, by final group-stage record. A team stops at four wins or four losses, so the
# record determines the count with no freedom left: 4-0 and 0-4 finish in four series; 4-1 and 1-4
# take five; the ten teams that finish 3-2 or 2-3 play five Swiss series plus the elimination round.
SERIES_BY_BUCKET = {"4-0": 4, "4-1": 5, "decider_win": 6, "decider_loss": 6, "1-4": 5, "0-4": 4}
SEED = 20260813
DRAWS = 4000


def frozen_bucket_probabilities(path=None):
    """Per-team bucket probabilities, read from the frozen track's published candidate artifact."""
    if path is None:
        found = sorted(glob.glob(CANDIDATES))
        if not found:
            raise SystemExit("no frozen group-stage candidate artifact found; this module reads "
                             "the frozen track's output and never recomputes it")
        path = found[-1]
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    probs = doc.get("probabilities")
    if not probs:
        raise SystemExit(f"{path} carries no per-team bucket probabilities")
    for team, row in probs.items():
        missing = [b for b in SERIES_BY_BUCKET if b not in row]
        if missing:
            raise SystemExit(f"{path}: {team} is missing bucket(s) {missing}")
        total = sum(row[b] for b in SERIES_BY_BUCKET)
        if abs(total - 1.0) > 0.02:
            raise SystemExit(f"{path}: {team} bucket probabilities sum to {total:.4f}")
    return probs, os.path.basename(path)


def exposure_distribution(probs):
    """team -> {series count: probability}, plus the expected count."""
    out = {}
    for team, row in probs.items():
        dist = {}
        for bucket, n in SERIES_BY_BUCKET.items():
            dist[n] = dist.get(n, 0.0) + row[bucket]
        out[team] = {"dist": {k: round(v, 4) for k, v in sorted(dist.items())},
                     "expected_series": round(sum(k * v for k, v in dist.items()), 3)}
    return out


def expected_max(sample, n, rng):
    """E[max of n draws] from an empirical sample, by resampling with replacement."""
    if not sample:
        return None
    tot = 0.0
    for _ in range(DRAWS):
        tot += max(sample[rng.randrange(len(sample))] for _ in range(n))
    return tot / DRAWS


def option_value(sample, seed=SEED):
    """E[max] at each reachable series count, and what one extra draw buys."""
    rng = random.Random(seed)
    counts = sorted(set(SERIES_BY_BUCKET.values()))
    em = {n: expected_max(sample, n, rng) for n in counts}
    lo, hi = counts[0], counts[-1]
    gain = None
    if em[lo] and em[hi]:
        gain = {"absolute": round(em[hi] - em[lo], 1),
                "relative": round((em[hi] - em[lo]) / em[lo], 4),
                "from_series": lo, "to_series": hi}
    return {"expected_max_by_series": {n: (round(v, 1) if v is not None else None)
                                       for n, v in em.items()},
            "gain_over_full_range": gain}


def adjust(ranking, probs, seed=SEED):
    """Exposure-adjusted period score: E over the team's series count of E[max of that many]."""
    rng = random.Random(seed)
    dist = exposure_distribution(probs)
    out = []
    for e in ranking:
        sample = e.get("series_scores") or []
        team = e["organization"]
        d = dist.get(team)
        if not sample or not d:
            continue
        em = {n: expected_max(sample, n, rng) for n in sorted(set(SERIES_BY_BUCKET.values()))}
        adjusted = sum(p * em[n] for n, p in d["dist"].items() if em[n] is not None)
        out.append({**e, "expected_series": d["expected_series"],
                    "series_distribution": d["dist"],
                    "unadjusted_total": e["envelope_total"],
                    "exposure_adjusted_total": round(adjusted, 1),
                    "option_value": option_value(sample, seed)})
    return out


def rank_movement(before, after, role):
    a = [e["organization"] for e in sorted((x for x in before if x["role"] == role),
                                           key=lambda e: -e["envelope_total"])]
    b = [e["organization"] for e in sorted((x for x in after if x["role"] == role),
                                           key=lambda e: -e["exposure_adjusted_total"])]
    pos = {o: i for i, o in enumerate(b)}
    moves = [abs(i - pos[o]) for i, o in enumerate(a) if o in pos]
    return {"identical": all(m == 0 for m in moves), "total_positions_moved": sum(moves),
            "max_single_move": max(moves, default=0), "before": a, "after": b}


def fixed_draw_ranking(ranking, n, seed=SEED):
    """E[max of exactly n draws] for every team: the same estimator, with exposure held constant.

    This is the control. Going from the raw envelope to the exposure-adjusted number changes two
    things at once -- the estimator (a mean of per-event maxima becomes an expected maximum over a
    fixed number of draws) and the exposure (that number differs by team). Attributing all of the
    resulting movement to exposure would be exactly the confound this project keeps tripping over,
    so the two steps are measured separately.
    """
    rng = random.Random(seed)
    out = []
    for e in ranking:
        sample = e.get("series_scores") or []
        if not sample:
            continue
        out.append({**e, "exposure_adjusted_total": round(expected_max(sample, n, rng), 1),
                    "unadjusted_total": e["envelope_total"]})
    return out


def run(min_series_maps=2, tfp_curve="linear"):
    base = bl.build("sum", False, min_series_maps, tfp_curve)
    probs, src = frozen_bucket_probabilities()
    adjusted = adjust(base["ranking"], probs)
    control = fixed_draw_ranking(base["ranking"], 5)
    roles = ("core", "mid", "support")
    return {"coverage": base["input_coverage"], "frozen_source": src,
            "series_by_bucket": SERIES_BY_BUCKET,
            "exposure": exposure_distribution(probs),
            "ranking": adjusted,
            "attribution": {
                "note": "Two steps, measured one at a time. Step 1 changes the estimator with "
                        "exposure held at a constant five draws for every team. Step 2 then lets "
                        "the per-team series count vary. Only step 2 is the exposure effect.",
                "step_1_estimator_only": {r: rank_movement(base["ranking"], control, r)
                                          for r in roles},
                "step_2_exposure_only": {r: _movement_between(control, adjusted, r) for r in roles}},
            "movement_total": {r: rank_movement(base["ranking"], adjusted, r) for r in roles},
            "status": "PRELIMINARY"}


def _movement_between(before, after, role):
    """Rank movement between two rankings that both use the exposure-adjusted key."""
    a = [e["organization"] for e in sorted((x for x in before if x["role"] == role),
                                           key=lambda e: -e["exposure_adjusted_total"])]
    b = [e["organization"] for e in sorted((x for x in after if x["role"] == role),
                                           key=lambda e: -e["exposure_adjusted_total"])]
    pos = {o: i for i, o in enumerate(b)}
    moves = [abs(i - pos[o]) for i, o in enumerate(a) if o in pos]
    return {"identical": all(m == 0 for m in moves), "total_positions_moved": sum(moves),
            "max_single_move": max(moves, default=0), "before": a, "after": b}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--out", default="")
    a.add_argument("--role", default="")
    a = a.parse_args(argv)
    r = run()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    cov = r["coverage"]
    print(f"exposure from {r['frozen_source']} on {cov['matches_covered']}/"
          f"{cov['matches_targeted']} matches ({cov['coverage']:.1%})")
    ex = sorted(r["exposure"].items(), key=lambda kv: -kv[1]["expected_series"])
    print("\nexpected series (frozen track, exogenous):")
    for team, v in ex[:5]:
        print(f"  {team:<18} {v['expected_series']:.3f}  {v['dist']}")
    print(f"  ... lowest: {ex[-1][0]} {ex[-1][1]['expected_series']:.3f}")
    for role in ("core", "mid", "support"):
        s1 = r["attribution"]["step_1_estimator_only"][role]
        s2 = r["attribution"]["step_2_exposure_only"][role]
        print(f"\n{role}: estimator change moves {s1['total_positions_moved']} positions; "
              f"exposure differential moves {s2['total_positions_moved']} "
              f"(max {s2['max_single_move']})")
        rows = sorted((e for e in r["ranking"] if e["role"] == role),
                      key=lambda e: -e["exposure_adjusted_total"])
        for e in rows[:5]:
            ov = e["option_value"]["gain_over_full_range"]
            g = f"{ov['relative']:+.1%}" if ov else "n/a"
            print(f"   {e['exposure_adjusted_total']:>9.1f} (raw {e['unadjusted_total']:>9.1f})  "
                  f"E[series] {e['expected_series']:.2f}  4->6 draw gain {g}  {e['organization']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
