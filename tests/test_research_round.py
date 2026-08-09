"""Coverage for the pre-lock research round: pre-draw sampling, simulation archive, ensemble
mixing, and the verified expected-points refinement rule."""
import random

import numpy as np
import pytest

from backtest2.ensemble_study import mix
from backtest2.pre_draw import sample_pods
from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.predict_ti15 import _BIDX, points_refinement
from ti_predict.swiss import monte_carlo

TEAMS = [f"T{i:02d}" for i in range(16)]
STRENGTH = {t: 0.22 * i for i, t in enumerate(TEAMS)}
REGION = {t: ("EU", "CN", "SEA", "NA")[i % 4] for i, t in enumerate(TEAMS)}


@pytest.mark.parametrize("scenario", ["uniform", "banded", "region"])
def test_sample_pods_is_a_valid_partition(scenario):
    rng = random.Random(7)
    podA, podB = sample_pods(TEAMS, scenario, rng, STRENGTH, REGION)
    assert len(podA) == 8 and len(podB) == 8
    assert set(podA) | set(podB) == set(TEAMS)
    assert not set(podA) & set(podB)


def test_sample_pods_banded_takes_two_per_band_per_pod():
    rng = random.Random(11)
    podA, podB = sample_pods(TEAMS, "banded", rng, STRENGTH, REGION)
    ranked = sorted(TEAMS, key=lambda t: -STRENGTH[t])
    for i in range(0, 16, 4):
        band = set(ranked[i:i + 4])
        assert len(band & set(podA)) == 2 and len(band & set(podB)) == 2


def test_sample_pods_deterministic_under_seed():
    a = sample_pods(TEAMS, "uniform", random.Random(3), STRENGTH, REGION)
    b = sample_pods(TEAMS, "uniform", random.Random(3), STRENGTH, REGION)
    assert a == b


def test_monte_carlo_archive_matches_P():
    pods = (TEAMS[0::2], TEAMS[1::2])
    P, arch = monte_carlo(pods, STRENGTH, n=300, seed=5, c=0.0, return_archive=True)
    for t in TEAMS:
        assert len(arch[t]) == 300
        assert all(0 <= b < len(BUCKETS) for b in arch[t])
        for b in BUCKETS:
            freq = sum(1 for x in arch[t] if x == _BIDX[b]) / 300
            assert freq == pytest.approx(P[t][b])


def test_mix_endpoints_and_midpoint():
    assert mix(0.7, 0.2, 0.0) == pytest.approx(0.7)
    assert mix(0.7, 0.2, 1.0) == pytest.approx(0.2)
    assert 0.2 < mix(0.7, 0.2, 0.5) < 0.7


# In the baseline toy assignment (TEAMS zipped to the slot list) T03 holds a decider_win slot and
# T08 a decider_loss slot; the pair (T03, T08) is the contested boundary in these tests.
def _tiny_archives(win_team):
    """Toy archive: every team always lands its baseline slot, except the (T03, T08) pair, where
    `win_team` always lands decider_win and the other always lands decider_loss."""
    n = 200
    slots = [b for b in BUCKETS for _ in range(CAPACITY[b])]
    asg = dict(zip(TEAMS, slots))
    assert asg["T03"] == "decider_win" and asg["T08"] == "decider_loss"
    arch = {t: np.full(n, _BIDX[asg[t]], dtype=np.int8) for t in TEAMS}
    loser = "T08" if win_team == "T03" else "T03"
    arch[win_team][:] = _BIDX["decider_win"]
    arch[loser][:] = _BIDX["decider_loss"]
    return asg, arch


def test_points_refinement_adopts_a_clear_improvement():
    # baseline slate has T03 in decider_win, but in the archive T08 always wins and T03 always
    # loses -> the swap is a strict points improvement and must be proposed and adopted
    asg, arch = _tiny_archives(win_team="T08")
    final, info = points_refinement(asg, arch, arch, seed=1)
    assert info["proposed_moves"] == ["T03", "T08"]
    assert info["adopted"] is True
    assert final["T08"] == "decider_win" and final["T03"] == "decider_loss"
    from collections import Counter
    assert Counter(final.values()) == CAPACITY


def test_points_refinement_rejects_when_verification_disagrees():
    asg, arch_opt = _tiny_archives(win_team="T08")         # optimize archive: T08 always wins
    _, arch_ver = _tiny_archives(win_team="T03")           # verification archive: the OPPOSITE
    final, info = points_refinement(asg, arch_opt, arch_ver, seed=1)
    assert info["proposed_moves"] == ["T03", "T08"]
    assert info["adopted"] is False                        # gain negative on verification archive
    assert final == asg                                    # Hungarian slate stands


def test_points_refinement_no_move_on_consistent_slate():
    asg, arch = _tiny_archives(win_team="T03")             # T03 already in decider_win and wins
    final, info = points_refinement(asg, arch, arch, seed=1)
    assert info["proposed_moves"] == [] and info["adopted"] is False
    assert final == asg
