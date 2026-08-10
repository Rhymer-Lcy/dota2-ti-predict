"""The pods-latent hypothesis space: complete, admissible, and counted once each."""
from backtest2.post_r1 import pod_hypotheses, r1_probabilities, structures
from ti_predict.swiss import is_two_pod, teams_of

TEAMS = [f"T{i:02d}" for i in range(16)]
R1 = [(TEAMS[2 * i], TEAMS[2 * i + 1]) for i in range(8)]


def test_every_admissible_two_pod_partition_appears_exactly_once():
    """A pod must be a union of four whole round-1 matches; C(8,4)/2 = 35 such partitions."""
    hyps = pod_hypotheses(R1)
    assert len(hyps) == 35
    seen = {frozenset(map(frozenset, (a, b))) for a, b in hyps}
    assert len(seen) == 35                                   # no partition counted twice


def test_each_hypothesis_is_a_legal_pod_split_for_the_posted_round_one():
    for podA, podB in pod_hypotheses(R1):
        assert len(podA) == 8 and len(podB) == 8
        assert set(podA).isdisjoint(podB)
        assert set(podA) | set(podB) == set(TEAMS)
        pod_of = {t: "A" for t in podA}
        pod_of.update({t: "B" for t in podB})
        for a, b in R1:
            assert pod_of[a] == pod_of[b]                    # round 1 never crosses pods


def test_structure_list_is_the_open_pool_plus_the_two_pod_family():
    st = structures(R1, TEAMS)
    assert len(st) == 36
    fams = [f for f, _, _ in st]
    assert fams.count("open") == 1 and fams.count("two-pod") == 35
    (_, _, open_pods) = st[0]
    assert not is_two_pod(open_pods) and sorted(teams_of(open_pods)) == sorted(TEAMS)


def test_round_one_probabilities_are_consistent_map_to_series():
    """Bo3 series probability is p^2(3-2p); it must sit on the same side of 0.5 as the map prob."""
    strength = {t: 0.2 * i for i, t in enumerate(TEAMS)}
    out = r1_probabilities(strength, R1, c=0.09)
    assert len(out) == 8
    for m in out:
        p, s = m["map_p_a"], m["series_p_a"]
        assert 0.0 < p < 1.0 and 0.0 < s < 1.0
        assert (p > 0.5) == (s > 0.5)
        assert abs(s - (p * p * (3 - 2 * p))) < 5e-4         # both reported rounded to 4 decimals
        assert abs(s - 0.5) >= abs(p - 0.5) - 1e-12          # a Bo3 amplifies the favourite
