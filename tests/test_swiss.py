"""Simulator: structural invariant, side-neutral symmetry, reproducibility, CRN sensitivity."""
from collections import Counter

import pytest

from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.swiss import (d4_sensitivity_crn, is_two_pod, map_p, map_pn, monte_carlo,
                              simulate_one, teams_of)

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


# ---- open (no-pod) structure: added when the posted draw published round 1 but no pod split ----
def test_open_structure_holds_the_same_record_distribution():
    """A single 16-team Swiss forces the same 1/2/5/5/2/1 outcome as the two-pod structure."""
    teams = [f"T{i:02d}" for i in range(16)]
    s = {t: 0.2 * i for i, t in enumerate(teams)}
    P = monte_carlo((teams,), s, n=2000, seed=11)
    for b in BUCKETS:
        assert abs(sum(P[t][b] for t in teams) - CAPACITY[b]) < 1e-9


def test_open_structure_accepts_a_round_one_that_would_cross_pods():
    """With no pod split there is no cross-pod constraint, so any perfect pairing is legal."""
    teams = [f"T{i:02d}" for i in range(16)]
    s = {t: 0.2 * i for i, t in enumerate(teams)}
    r1 = [(teams[i], teams[i + 8]) for i in range(8)]        # illegal under any 8/8 pod split
    P = monte_carlo((teams,), s, n=800, seed=12, r1_pairings=r1)
    assert abs(sum(P[t]["4-0"] for t in teams) - 1.0) < 1e-9


def test_structure_helpers():
    teams = [f"T{i:02d}" for i in range(16)]
    assert is_two_pod((teams[:8], teams[8:])) and not is_two_pod((teams,))
    assert teams_of((teams[:8], teams[8:])) == teams and teams_of((teams,)) == teams


def test_open_structure_is_reproducible_under_a_fixed_seed():
    teams = [f"T{i:02d}" for i in range(16)]
    s = {t: 0.2 * i for i, t in enumerate(teams)}
    r1 = [(teams[2 * i], teams[2 * i + 1]) for i in range(8)]
    a = monte_carlo((teams,), s, n=500, seed=99, r1_pairings=r1)
    b = monte_carlo((teams,), s, n=500, seed=99, r1_pairings=r1)
    assert a == b
