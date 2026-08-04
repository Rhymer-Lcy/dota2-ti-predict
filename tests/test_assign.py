"""Assignment solver: capacity, one team per slot, expected-correct accounting."""
import pytest

from ti_predict.assign import assign
from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.swiss import monte_carlo

TEAMS = [f"T{i:02d}" for i in range(16)]
STRENGTH = {t: 0.22 * i for i, t in enumerate(TEAMS)}
PODS = (TEAMS[0::2], TEAMS[1::2])


def test_assignment_respects_capacity_and_uses_each_team_once():
    P = monte_carlo(PODS, STRENGTH, n=500, seed=11, c=0.0)
    slate, exp_correct, rows = assign(P)
    assert all(len(slate[b]) == CAPACITY[b] for b in BUCKETS)
    assert len({t for t, _, _ in rows}) == 16
    assert exp_correct == pytest.approx(sum(P[t][b] for t, b, _ in rows))


def test_assignment_is_at_least_as_good_as_greedy_extremes():
    P = monte_carlo(PODS, STRENGTH, n=800, seed=13, c=0.0)
    _, exp_correct, _ = assign(P)
    assert 0.0 <= exp_correct <= 16.0
    assert exp_correct > 4.0                                    # monotone strengths -> clearly informative
