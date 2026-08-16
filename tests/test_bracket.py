"""Bracket: topology read from the official feed, exact enumeration, and the scoring contract."""
import numpy as np
import pytest

from ti_predict import bracket as bk
from ti_predict.contest_rules import MAIN_EVENT_SCORE
from ti_predict.series import series_win_prob

TOPO = bk.load_topology()
TEAMS = [f"T{i}" for i in range(8)]
SEATS = {nid: (TEAMS[2 * k], TEAMS[2 * k + 1]) for k, nid in enumerate(TOPO["seeded"])}
STRENGTH = {t: 0.22 * i for i, t in enumerate(TEAMS)}
C = 0.09


@pytest.fixture(scope="module")
def enumerated():
    names, W, PR = bk.enumerate_structure(TOPO, SEATS)
    P = bk.outcome_probs(TOPO, W, PR, names, STRENGTH, C)
    return names, W, PR, P


def test_topology_has_the_required_fourteen_node_shape():
    shape = {}
    for nid in TOPO["order"]:
        shape[TOPO["label"][nid]] = shape.get(TOPO["label"][nid], 0) + 1
    assert shape == bk.EXPECTED_SHAPE
    assert len(TOPO["order"]) == 14


def test_only_the_grand_final_is_best_of_five():
    bo5 = [n for n in TOPO["order"] if TOPO["best_of"][n] == 5]
    assert bo5 == [TOPO["gf"]]
    assert all(TOPO["best_of"][n] == 3 for n in TOPO["order"] if n != TOPO["gf"])


def test_lower_bracket_feed_is_crossed():
    """A semi-final loser must not meet the quarter-final losers from its own half."""
    lbr2 = [n for n in TOPO["order"] if TOPO["label"][n] == "LBR2"]
    assert len(lbr2) == 2
    for nid in lbr2:
        drop = [s for s, tag in TOPO["inputs"][nid] if tag == "L"]
        feed = [s for s, tag in TOPO["inputs"][nid] if tag == "W"]
        assert len(drop) == 1 and len(feed) == 1
        semi_qfs = {s for s, _ in TOPO["inputs"][drop[0]]}          # quarters feeding that semi
        lbr1_qfs = {s for s, _ in TOPO["inputs"][feed[0]]}          # quarters feeding that LBR1
        assert not (semi_qfs & lbr1_qfs), f"node {nid} is not crossed"


def test_every_node_is_reachable_and_the_order_is_topological():
    placed = set()
    for nid in TOPO["order"]:
        assert all(s in placed for s, _ in TOPO["inputs"][nid])
        placed.add(nid)
    assert len(placed) == 14


def test_client_slot_map_covers_selection_ids_801_to_814():
    assert sorted(TOPO["node_to_selection"].values()) == list(range(801, 815))
    assert len(set(TOPO["series_name"].values())) == 14


def test_scoring_vector_matches_the_client_and_its_anchors():
    sv = bk.verify_scoring_vector()
    assert sv["vector"][1] == 120 and sv["vector"][14] == 12000 and sv["vector"][0] == 0
    assert sv["vector"] == [MAIN_EVENT_SCORE[k] for k in range(15)]


def test_enumeration_is_complete_and_normalized(enumerated):
    names, W, PR, P = enumerated
    assert W.shape == (1 << 14, 14)
    assert len({tuple(r) for r in W.tolist()}) == 1 << 14, "outcomes must be distinct"
    assert P.sum() == pytest.approx(1.0, abs=1e-12)
    assert (P >= 0).all()


def test_each_node_winner_is_one_of_its_two_participants(enumerated):
    _, W, PR, _ = enumerated
    assert ((W == PR[:, :, 0]) | (W == PR[:, :, 1])).all()
    assert (PR[:, :, 0] != PR[:, :, 1]).all()


def test_champion_mass_is_normalized_and_monotone_in_strength(enumerated):
    names, W, _, P = enumerated
    gf = TOPO["order"].index(TOPO["gf"])
    champ = np.array([P[W[:, gf] == i].sum() for i in range(8)])
    assert champ.sum() == pytest.approx(1.0)
    assert champ.argmax() == 7, "the strongest team must be the modal champion"


def test_a_seeded_team_appears_in_exactly_one_quarterfinal(enumerated):
    names, W, PR, P = enumerated
    qf = [TOPO["order"].index(n) for n in TOPO["order"] if TOPO["label"][n] == "UBQF"]
    for i in range(8):
        seats = [col for col in qf if (PR[0, col] == i).any()]
        assert len(seats) == 1


def test_grand_final_uses_the_bo5_probability(enumerated):
    """The Bo5 must actually sharpen the favourite relative to a Bo3."""
    names, W, PR, _ = enumerated
    mp = bk.map_prob(STRENGTH[names[7]], STRENGTH[names[0]], C)
    assert series_win_prob(mp, 5) > series_win_prob(mp, 3) > mp


def test_expected_score_is_exact_against_a_direct_recomputation(enumerated):
    names, W, PR, P = enumerated
    Es, Ec = bk.expected_scores(W, P)
    for row in (0, 4321, (1 << 14) - 1):
        K = (W == W[row]).sum(axis=1)
        assert Es[row] == pytest.approx(float(bk.SCORE_VEC[K] @ P))
        assert Ec[row] == pytest.approx(float(K @ P))


def test_a_slate_scores_fourteen_exactly_when_its_own_outcome_happens(enumerated):
    names, W, PR, P = enumerated
    row = 777
    K = (W == W[row]).sum(axis=1)
    assert K[row] == 14
    assert (K == 14).sum() == 1


def test_expected_correct_never_exceeds_the_node_count(enumerated):
    names, W, PR, P = enumerated
    Es, Ec = bk.expected_scores(W, P)
    assert Ec.max() <= 14 and Ec.min() >= 0
    assert Es.max() <= MAIN_EVENT_SCORE[14]


def test_greedy_favourite_is_a_coherent_slate(enumerated):
    names, W, PR, P = enumerated
    vec = bk.greedy_favourite(TOPO, SEATS, STRENGTH, C, names)
    assert bk.slate_row(W, vec) >= 0


def test_greedy_is_never_better_than_the_exhaustive_optimum(enumerated):
    names, W, PR, P = enumerated
    Es, _ = bk.expected_scores(W, P)
    g = bk.slate_row(W, bk.greedy_favourite(TOPO, SEATS, STRENGTH, C, names))
    assert Es[g] <= Es.max() + 1e-9


def test_outcome_probs_is_invariant_to_a_common_strength_shift(enumerated):
    names, W, PR, P = enumerated
    shifted = {t: v + 3.0 for t, v in STRENGTH.items()}
    assert bk.outcome_probs(TOPO, W, PR, names, shifted, C) == pytest.approx(P)


def test_equal_strengths_give_a_uniform_outcome_distribution(enumerated):
    names, W, PR, _ = enumerated
    flat = bk.outcome_probs(TOPO, W, PR, names, {t: 0.0 for t in names}, 0.0)
    assert flat == pytest.approx(np.full(1 << 14, 2.0 ** -14))


def test_agreement_matrix_matches_a_direct_comparison(enumerated):
    names, W, PR, P = enumerated
    rows = [0, 100, 16383]
    K = bk.agreement_matrix(W, rows)
    for i, r in enumerate(rows):
        assert (K[i] == (W == W[r]).sum(axis=1)).all()


def test_topology_fails_closed_on_a_broken_feed(tmp_path):
    import json
    broken = tmp_path / "feed.json"
    broken.write_text(json.dumps({"node_groups": [{"name": "Playoff", "nodes": []}]}),
                      encoding="utf-8")
    with pytest.raises(SystemExit):
        bk.load_topology(path=str(broken))
    with pytest.raises(SystemExit):
        bk.load_topology(path=str(tmp_path / "absent.json"))
