"""Simulator: structural invariant, side-neutral symmetry, reproducibility, CRN sensitivity."""
from collections import Counter

import pytest

from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.swiss import (d4_sensitivity_crn, map_p, map_pn, monte_carlo, simulate_one)

TEAMS = [f"T{i:02d}" for i in range(16)]
STRENGTH = {t: 0.22 * i for i, t in enumerate(TEAMS)}
PODS = (TEAMS[0::2], TEAMS[1::2])


def test_map_pn_side_neutral_symmetry():
    for sa, sb, c in [(1.0, 0.0, 0.09), (0.3, 0.9, 0.5), (-0.4, 0.4, 0.0)]:
        assert map_pn(sa, sb, c) + map_pn(sb, sa, c) == pytest.approx(1.0)


def test_map_pn_c_zero_equals_sigmoid():
    for sa, sb in [(1.0, 0.0), (-0.5, 0.5), (0.2, 0.2)]:
        assert map_pn(sa, sb, 0.0) == pytest.approx(map_p(sa, sb))


def test_simulate_one_returns_16_with_exact_capacity():
    import random
    bucket = simulate_one(PODS, STRENGTH, random.Random(1), c=0.09)
    assert len(bucket) == 16
    assert Counter(bucket.values()) == CAPACITY


def test_monte_carlo_row_and_column_sums():
    P = monte_carlo(PODS, STRENGTH, n=400, seed=7, c=0.09)
    for t in TEAMS:
        assert sum(P[t].values()) == pytest.approx(1.0)
    for b in BUCKETS:
        assert sum(P[t][b] for t in TEAMS) == pytest.approx(CAPACITY[b])


def test_monte_carlo_reproducible_with_seed():
    a = monte_carlo(PODS, STRENGTH, n=300, seed=42, c=0.0)
    b = monte_carlo(PODS, STRENGTH, n=300, seed=42, c=0.0)
    assert a == b


def test_monotonic_strength_ordering():
    P = monte_carlo(PODS, STRENGTH, n=1500, seed=3, c=0.0)
    assert P["T15"]["4-0"] == max(P[t]["4-0"] for t in TEAMS)
    assert P["T00"]["0-4"] == max(P[t]["0-4"] for t in TEAMS)


def test_crn_sensitivity_capacities_and_reproducible():
    P1 = d4_sensitivity_crn(PODS, STRENGTH, n=300, seed=5, c=0.09)
    P2 = d4_sensitivity_crn(PODS, STRENGTH, n=300, seed=5, c=0.09)
    assert P1 == P2                                             # deterministic under fixed seed
    for choice in ("strategic", "noisy", "random"):
        for b in BUCKETS:
            assert sum(P1[choice][t][b] for t in TEAMS) == pytest.approx(CAPACITY[b])
