"""The published main-event artifact must stay internally consistent and honestly labelled.

These are artifact-discipline tests: they read the committed prediction rather than recomputing it,
so a hand-edit, a stale rerun or a quietly relaxed gate is caught. Pure helpers from the pipeline are
exercised separately on synthetic input.
"""
import json
import os

import numpy as np
import pytest

from ti_predict import bracket as bk
from ti_predict import predict_main_event as pme
from ti_predict import ti15_results as tr
from ti_predict.contest_rules import MAIN_EVENT_SCORE, PRODUCTION_HALF_LIFE_DAYS

ART = os.path.join(pme.OUTDIR, "ti15_main_event_prediction.json")


@pytest.fixture(scope="module")
def art():
    if not os.path.exists(ART):
        pytest.skip("main-event artifact not generated yet")
    with open(ART, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- pure helpers
def test_series_blocks_keep_a_bo3_together():
    rows = [{"series_id": 7, "match_id": "1"}, {"series_id": 7, "match_id": "2"},
            {"series_id": 7, "match_id": "3"}, {"series_id": 8, "match_id": "4"},
            {"series_id": 0, "match_id": "5"}, {"series_id": 0, "match_id": "6"}]
    blocks = pme.series_blocks(rows)
    assert sorted(len(b) for b in blocks) == [1, 1, 1, 3]
    assert sum(len(b) for b in blocks) == len(rows)


def test_series_blocks_partition_every_row_exactly_once():
    rows = [{"series_id": i % 5, "match_id": str(i)} for i in range(40)]
    idx = sorted(i for b in pme.series_blocks(rows) for i in b)
    assert idx == list(range(40))


def test_flip_cost_is_never_negative_and_names_a_real_alternative():
    topo = bk.load_topology()
    teams = [f"T{i}" for i in range(8)]
    seats = {nid: (teams[2 * k], teams[2 * k + 1]) for k, nid in enumerate(topo["seeded"])}
    names, W, PR = bk.enumerate_structure(topo, seats)
    P = bk.outcome_probs(topo, W, PR, names, {t: 0.22 * i for i, t in enumerate(teams)}, 0.09)
    Es, _ = bk.expected_scores(W, P)
    best = int(np.argmax(Es))
    costs = pme.flip_costs(W, Es, topo, names, best)
    assert len(costs) == 14
    for col, nid in enumerate(topo["order"]):
        assert costs[nid]["cost_of_changing"] >= -1e-9
        alt = costs[nid]["best_alternative_row"]
        assert W[alt, col] != W[best, col]
        assert costs[nid]["alternative_pick"] in names


def test_node_marginals_are_probability_distributions():
    topo = bk.load_topology()
    teams = [f"T{i}" for i in range(8)]
    seats = {nid: (teams[2 * k], teams[2 * k + 1]) for k, nid in enumerate(topo["seeded"])}
    names, W, PR = bk.enumerate_structure(topo, seats)
    P = bk.outcome_probs(topo, W, PR, names, {t: 0.22 * i for i, t in enumerate(teams)}, 0.09)
    marg = pme.node_marginals(topo, W, PR, P, names)
    for nid, m in marg.items():
        assert m["win"].sum() == pytest.approx(1.0)
        assert m["reach"].sum() == pytest.approx(2.0), "two teams reach every node"
        assert (m["win"] <= m["reach"] + 1e-12).all()


# ---------------------------------------------------------------- the artifact
def test_every_hard_gate_passed(art):
    g = art["gates"]
    assert g["result_reconciliation"]["total_series"] == 44
    assert g["result_reconciliation"]["standings_reproduced"]
    assert g["result_reconciliation"]["unique_surviving_orgs"] == 8
    assert g["pipeline_identity_vs_locked_group_run"]["reproduced"]
    assert g["scoring_vector"]["anchors_ok"]
    assert g["bracket_topology"]["shape"] == bk.EXPECTED_SHAPE
    assert not g["roster_audit"]["blocking_in_main_event"]
    assert g["timestamp_sensitivity"]["optimal_slate_unchanged"]


def test_the_frozen_specification_is_unchanged(art):
    m = art["manifest"]["model"]
    assert m["family"] == "B-bt"
    assert m["half_life_days"] == PRODUCTION_HALF_LIFE_DAYS == 90
    assert m["lambda"] == 1.0
    assert m["calibration"] == "none"
    assert m["frozen"] and not m["reopened_for_ti15"]
    sa = art["gates"]["sequential_assimilation"]
    assert sa["production_path_changed"] is False
    assert sa["selected"].startswith("plain frozen")
    assert sa["is_a_group_to_playoff_replay"] is False


def test_no_forbidden_input_entered_the_run(art):
    u = art["manifest"]["inputs_used"]
    assert u["network"] is False
    assert u["odds_or_market"] is False
    assert u["crowd_percentages"] is False
    assert u["main_event_results"] is False
    assert u["manual_adjustments"] is False
    assert u["ti15_series_inserted"] == 44


def test_clean_run_provenance_fields_are_present_and_false(art):
    m = art["manifest"]
    assert m["network_used"] is False
    assert m["odds_used"] is False
    assert m["future_main_event_results_used"] is False
    assert m["git_dirty_at_start"] is False,         "the published artifact must be generated from a clean working tree"


def test_the_kappa_candidate_set_is_not_called_preregistered(art):
    """Provenance wording: the shrinkage set was fixed before scoring, but never preregistered."""
    sa = art["gates"]["sequential_assimilation"]
    assert "audit_predeclared_candidate_set" in sa
    assert "preregistered_candidate_set" not in sa
    assert "NOT preregistered" in sa["candidate_set_provenance"]
    blob = json.dumps({k: v for k, v in sa.items() if k != "per_population_and_split"})
    assert "preregistered" not in blob.replace("NOT preregistered", "").replace(
        "preregistered v1 model validation", "").replace("preregistered set", "")


def test_the_slate_has_fourteen_slots_with_the_client_selection_ids(art):
    ids = sorted(r["selection_id"] for r in art["primary_slate"])
    assert ids == list(range(801, 815))
    assert len({r["node_id"] for r in art["primary_slate"]}) == 14


def test_the_slate_is_coherent_against_the_verified_topology(art):
    """A pick must be one of the two teams the slate itself sends to that node."""
    topo = bk.load_topology()
    by_node = {r["node_id"]: r for r in art["primary_slate"]}
    win, lose = {}, {}
    for nid in topo["order"]:
        r = by_node[nid]
        if topo["inputs"][nid]:
            (s1, t1), (s2, t2) = topo["inputs"][nid]
            a = win[s1] if t1 == "W" else lose[s1]
            b = win[s2] if t2 == "W" else lose[s2]
        else:
            a, b = tr.canon(tr.UBQF[nid][0]), tr.canon(tr.UBQF[nid][1])
        assert sorted(r["predicted_matchup"]) == sorted([a, b]), nid
        assert r["pick"] in (a, b), nid
        win[nid] = r["pick"]
        lose[nid] = b if r["pick"] == a else a


def test_client_actions_agree_with_the_slate(art):
    slate = {r["selection_id"]: r["pick"] for r in art["primary_slate"]}
    actions = {r["selection_id"]: r["select"] for r in art["client_actions"]}
    assert slate == actions
    assert [r["selection_id"] for r in art["client_actions"]] == sorted(actions)


def test_only_the_grand_final_is_bo5_in_the_slate(art):
    bo5 = [r for r in art["primary_slate"] if r["best_of"] == 5]
    assert len(bo5) == 1 and bo5[0]["round"] == "GF"


def test_probabilities_are_well_formed(art):
    tp = art["tournament_probabilities"]
    assert len(tp) == 8
    assert sum(p["champion"] for p in tp.values()) == pytest.approx(1.0, abs=1e-3)
    assert sum(p["reach_grand_final"] for p in tp.values()) == pytest.approx(2.0, abs=1e-3)
    for t, p in tp.items():
        assert 0.0 <= p["champion"] <= p["reach_grand_final"] <= 1.0, t
        lo, hi = p["champion_bootstrap_90ci"]
        assert 0.0 <= lo <= hi <= 1.0, t
    for r in art["primary_slate"]:
        assert 0.0 < r["conditional_win_prob"] < 1.0
        assert 0.0 < r["marginal_pick_wins_node"] <= r["conditional_win_prob"] + 1e-9


def test_a_seeded_pick_has_no_gap_between_conditional_and_marginal(art):
    """In round 1 the matchup is certain, so the two probabilities must coincide."""
    for r in art["primary_slate"]:
        if r["round"] == "UBQF":
            assert r["marginal_pick_wins_node"] == pytest.approx(r["conditional_win_prob"], abs=0.02)


def test_the_primary_slate_is_the_expected_score_optimum(art):
    o = art["optimization"]
    best = o["max_expected_official_score"]["expected_score"]
    assert best >= o["greedy_coherent_favourite"]["expected_score"]
    assert best >= o["max_expected_correct"]["expected_score"]
    assert o["max_expected_correct"]["expected_correct"] >= \
           o["max_expected_official_score"]["expected_correct"]
    assert o["candidates_evaluated"] == 1 << 14


def test_the_score_distribution_is_a_distribution_and_matches_the_expectation(art):
    dist = art["optimization"]["score_distribution_of_primary"]
    assert sorted(int(k) for k in dist) == list(range(15))
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-4)
    exp = sum(MAIN_EVENT_SCORE[int(k)] * v for k, v in dist.items())
    assert exp == pytest.approx(
        art["optimization"]["max_expected_official_score"]["expected_score"], rel=1e-3)
    ecorrect = sum(int(k) * v for k, v in dist.items())
    assert ecorrect == pytest.approx(
        art["optimization"]["max_expected_official_score"]["expected_correct"], rel=1e-3)


def test_runner_up_regret_is_non_negative_and_the_diff_is_described(art):
    for key in ("second_best_overall", "best_with_a_different_champion"):
        r = art["runner_up"][key]
        assert r["regret_vs_primary"] >= 0.0
        assert r["differs_at"], "a runner-up must differ from the primary somewhere"
        for d in r["differs_at"]:
            assert d["primary"] != d["alternative"]


def test_a_different_champion_really_means_a_different_grand_final_pick(art):
    dc = art["runner_up"]["best_with_a_different_champion"]
    gf = next(r for r in art["primary_slate"] if r["round"] == "GF")
    assert dc["champion"] != gf["pick"]


def test_strength_evolution_covers_the_eight_and_decomposes_the_delta(art):
    ev = art["strength_evolution"]
    assert len(ev) == 8
    assert set(ev) == {tr.canon(t) for t in tr.FINAL_EIGHT}
    for t, e in ev.items():
        assert e["delta_pre_to_serve"] == pytest.approx(e["serve"] - e["pre_ti"], abs=1e-3)
        assert e["delta_attributable_to_ti15"] == pytest.approx(
            e["serve"] - e["decay_only_control"], abs=1e-3)
        assert e["serve_bootstrap_sd"] > 0
        lo, hi = e["serve_bootstrap_90ci"]
        assert lo < e["serve"] < hi, t


def test_the_three_states_add_data_monotonically(art):
    s = art["states"]
    assert s["A_pre_ti"]["train_maps"] < s["B_post_swiss"]["train_maps"] \
        < s["C_serve"]["train_maps"]
    assert s["C_serve"]["train_maps"] - s["B_post_swiss"]["train_maps"] == 12   # 5 elim series
    assert s["B_post_swiss"]["train_maps"] - s["A_pre_ti"]["train_maps"] == 97  # 39 Swiss series
    assert s["control_decay_origin"]["train_maps"] == s["A_pre_ti"]["train_maps"]


def test_fragile_nodes_are_flagged_by_a_stated_rule(art):
    for r in art["primary_slate"]:
        expect = (abs(r["conditional_win_prob"] - 0.5) < 0.05 or r["cost_of_changing"] < 25.0
                  or r["bootstrap_draw_agreement"] < 0.75 or r["draws_favouring_pick"] < 0.75)
        assert r["fragile"] == expect, r["selection_id"]


def test_the_markdown_view_matches_the_json_source(art):
    md = open(ART.replace(".json", ".md"), encoding="utf-8").read()
    for r in art["client_actions"]:
        assert f"slot {r['selection_id']}" in md and r["select"] in md
    assert art["manifest"]["code_commit"] in md
