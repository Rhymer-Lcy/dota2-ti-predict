"""16-slot assignment: maximize the expected number of correct group-stage predictions.

Given P[team][bucket] from `swiss.monte_carlo` and the fixed client slot capacities
(4-0 x1, 4-1 x2, decider_win x5, decider_loss x5, 1-4 x2, 0-4 x1), assign each of the 16 teams to
exactly one bucket-slot so the EXPECTED number correct (sum of P over the chosen cells) is maximal.

Why expected-correct-max is the base slate: group scoring has no underdog weighting and no
wrong-answer penalty (docs/contest-official-ti15.md sec 3), so each slot's value is set purely by hit
probability. Higher-variance / contrarian deviation is a separate strategic layer (justified only by
the convex point curve + percentile reward), NOT applied here.

Exact via Hungarian assignment over the 16 expanded slots; the LP is integral so this is optimal.
No TI2026 numbers are emitted here; __main__ demonstrates on synthetic strengths.
"""
import os
import sys

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.swiss import BUCKETS, CAPACITY


def assign(P):
    """Return (slate, expected_correct, rows).

    slate: {bucket: [(team, p), ...]} sorted by p desc.
    expected_correct: sum of P over the chosen cells (an upper bound on realized score in expectation).
    rows: [(team, bucket, p), ...] one per team.
    """
    teams = list(P)
    slots = [b for b in BUCKETS for _ in range(CAPACITY[b])]
    n = len(teams)
    assert n == len(slots) == 16, (n, len(slots))
    cost = np.array([[-P[t][b] for b in slots] for t in teams])
    ri, cj = linear_sum_assignment(cost)
    slate = {b: [] for b in BUCKETS}
    rows, exp_correct = [], 0.0
    for i, j in zip(ri, cj):
        t, b, p = teams[i], slots[j], P[teams[i]][slots[j]]
        slate[b].append((t, p))
        rows.append((t, b, p))
        exp_correct += p
    for b in slate:
        slate[b].sort(key=lambda x: -x[1])
    return slate, exp_correct, rows


def format_slate(slate, exp_correct):
    lines = [f"expected correct = {exp_correct:.2f} / 16", ""]
    for b in BUCKETS:
        picks = ", ".join(f"{t} ({p:.2f})" for t, p in slate[b])
        lines.append(f"{b:>13} [{CAPACITY[b]}] : {picks}")
    return "\n".join(lines)


if __name__ == "__main__":
    from ti_predict.swiss import monte_carlo

    teams = [f"T{i:02d}" for i in range(16)]
    strength = {t: 0.22 * i for i, t in enumerate(teams)}    # synthetic, T15 strongest
    pods = (teams[0::2], teams[1::2])
    P = monte_carlo(pods, strength, n=6000)
    slate, exp_correct, rows = assign(P)

    # each team used exactly once; capacities respected
    assert len({t for t, _, _ in rows}) == 16
    assert all(len(slate[b]) == CAPACITY[b] for b in BUCKETS)
    print("synthetic assignment (NOT TI2026):")
    print(format_slate(slate, exp_correct))
    print("\nassignment self-test passed; no TI2026 output emitted")
