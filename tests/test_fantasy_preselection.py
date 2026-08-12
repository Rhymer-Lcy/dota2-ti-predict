"""The pre-banner decision: a two-stage problem with a switching cost, not a leaderboard lookup.

The failure this guards against is the one that makes the whole module pointless: treating the
initial pick as `argmax E[score]`. With a positive token price the right objective is the value of
the keep-or-pay POLICY, and the two answers differ.
"""
import json
import os

import numpy as np
import pytest

from ti_predict.fantasy import preselection as ps
from ti_predict.fantasy import questions as fq

ARTIFACT = os.path.join("predictions", "ti2026", "fantasy", "preselection_20260810.json")


def _analysis(scores):
    """A hand-built analysis: rows are draws, columns are teams."""
    s = np.array(scores, dtype=float)
    best = s.max(axis=1)
    return {"teams": [f"T{i}" for i in range(s.shape[1])], "_score": s, "_best": best,
            "mean_score": s.mean(axis=0).tolist(),
            "p_optimal": ((best[:, None] - s) <= 1e-9).mean(axis=0).tolist(),
            "usable_fraction": [1.0] * s.shape[1], "mean_best": float(best.mean())}


def test_the_policy_value_is_not_the_same_number_for_every_candidate():
    """The bug that motivated this test: moving the max outside the expectation collapses it.

    E[max(score, best - lam)] is NOT score + max(0, E[regret] - lam). The second form equals
    E[best] for every candidate whenever lam is small, which would make the ranking meaningless.

    Note what the correct form rewards: a candidate is only distinguished on the draws where it is
    within lam of the best, because everywhere else you simply pay and switch. T0 here is nearly
    optimal when it is not optimal; T1 is far off when it is not.
    """
    a = _analysis([[10.0, 9.0], [9.7, 10.0]])
    pv = ps.policy_table(a['teams'], a['_score'], 0.05)
    values = {e["organization"]: e["policy_value"] for e in pv}
    assert values["T0"] > values["T1"]


def test_a_free_token_makes_every_candidate_equivalent():
    """With lam = 0 you can always switch for nothing, so the initial pick genuinely cannot matter.

    This is the degenerate case the model has to reproduce, and it is why a positive token price is
    the whole point: it is what makes the first choice a real decision.
    """
    a = _analysis([[10.0, 8.0], [2.0, 9.0]])
    pv = ps.policy_table(a['teams'], a['_score'], 0.0)
    values = [e["policy_value"] for e in pv]
    assert max(values) == pytest.approx(min(values))


def test_a_candidate_that_is_always_optimal_never_switches():
    a = _analysis([[10.0, 1.0], [10.0, 2.0], [10.0, 3.0]])
    pv = {e["organization"]: e for e in ps.policy_table(a['teams'], a['_score'], 0.02)}
    assert pv["T0"]["p_optimal"] == pytest.approx(1.0)
    assert pv["T0"]["p_switch"] == pytest.approx(0.0)
    assert pv["T1"]["p_switch"] == pytest.approx(1.0)


def test_regret_is_relative_so_the_weight_scale_cannot_dominate():
    """Doubling every score on a draw must not change any candidate's relative standing."""
    a = _analysis([[10.0, 8.0], [4.0, 18.0]])
    b = _analysis([[20.0, 16.0], [8.0, 36.0]])
    pa = {e["organization"]: e["policy_value"] for e in ps.policy_table(a['teams'], a['_score'], 0.02)}
    pb = {e["organization"]: e["policy_value"]
          for e in ps.policy_table(b['teams'], b['_score'], 0.02)}
    assert pa == pytest.approx(pb)


# ---- the coach suffix predicates ------------------------------------------------------------------
def _row(**kw):
    base = {"match_id": "m1", "_series": "s1", "duration": "1800", "win": "1"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_the_computable_suffix_conditions_match_the_client_wording():
    order = {"m1": 2, "m2": 0}
    length = {"s1": 3, "s2": 2}
    t = ps.suffix_triggers(_row(duration=1400, win=0), order, length)
    assert t["the Decisive"] is True          # under 25 minutes
    assert t["the Underdog"] is True          # the player lost
    assert t["the Clutch"] is True            # final map of a three-map series
    t = ps.suffix_triggers(_row(duration=1800, win=1, match_id="m2", _series="s2"), order, length)
    assert t["the Decisive"] is False and t["the Underdog"] is False
    assert t["the Clutch"] is False           # a two-map series has no last-possible game
    assert ps.suffix_triggers(_row(duration=1808), order, length)["the Lucky"] is True
    assert ps.suffix_triggers(_row(duration=1807), order, length)["the Lucky"] is False


def test_only_the_four_computable_suffixes_are_applied():
    """The other twelve titles need data this pipeline does not fetch, and are not faked."""
    assert set(ps.COMPUTABLE_SUFFIXES) == {"the Underdog", "the Decisive", "the Clutch",
                                           "the Lucky"}
    for name, bonus in ps.COMPUTABLE_SUFFIXES.items():
        assert 0 < bonus < 1


def test_the_bonus_values_match_the_recorded_client_pool():
    pool = fq.load_rules()["coach_titles"]["selectable_pool_2026"]
    by_name = {s["name"]: s["bonus_percent"] / 100.0 for s in pool["suffixes"]}
    for name, bonus in ps.COMPUTABLE_SUFFIXES.items():
        assert by_name[name] == pytest.approx(bonus)


# ---- the artifact ----------------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(ARTIFACT), reason="artifact not generated")
def test_the_recommendation_uses_three_distinct_organisations():
    """Legal under both readings of the unresolved distinct-team rule, at a measured 0.02% cost."""
    art = json.load(open(ARTIFACT, encoding="utf-8"))
    teams = [art["selection"][r]["team"] for r in ("core", "mid", "support")]
    assert len(set(teams)) == 3
    assert art["distinct_team_constraint"]["cost_of_being_safe"] < 0.001


@pytest.mark.skipif(not os.path.exists(ARTIFACT), reason="artifact not generated")
def test_the_artifact_is_labelled_as_a_pre_banner_pick_not_a_final_candidate():
    art = json.load(open(ARTIFACT, encoding="utf-8"))
    assert art["label"] == "PRE-BANNER INITIAL SELECTION"
    assert "NOT a final Fantasy candidate" in art["not"]
    assert "test account" in art["explicitly_not_derived_from"]


@pytest.mark.skipif(not os.path.exists(ARTIFACT), reason="artifact not generated")
def test_every_role_reports_a_switch_probability_and_a_second_choice():
    art = json.load(open(ARTIFACT, encoding="utf-8"))
    for role in ("core", "mid", "support"):
        s = art["selection"][role]
        assert 0.0 <= s["p_optimal_after_reveal"] <= 1.0
        assert s["second_choice"] and s["second_choice"] != s["team"]
        assert s["confidence"] in ("LOW", "LOW-MEDIUM", "MEDIUM", "MEDIUM-HIGH", "HIGH")


@pytest.mark.skipif(not os.path.exists(ARTIFACT), reason="artifact not generated")
def test_cold_start_roles_are_reported_rather_than_dropped():
    art = json.load(open(ARTIFACT, encoding="utf-8"))
    cs = art["robustness"]["cold_start"]
    assert "LGD Gaming (Topson)" in cs["mid"]["missing"]
    assert "Team Resilience" in cs["core"]["missing"]
    assert "reputation is not evidence" in cs["note"]


# ---- the mechanics this round corrected -------------------------------------------------------------
def test_switching_teams_is_recorded_as_costed_not_free():
    ts = fq.load_rules()["team_selection"]
    assert ts["change_cost_tokens"] == 1
    assert "positive cost" in ts["operational_model"]
    assert ts["user_runtime_observation"]["tier"] == "user_runtime_observation"
    assert "withdrawn" in ts["user_runtime_observation"]["why_it_matters"]


def test_banner_generation_is_confirmed_independent_of_the_team():
    bi = fq.load_rules()["banner_generation_independence"]
    assert bi["status"] == "CONFIRMED" and bi["tier"] == 1
    assert "carries no team field" in bi["evidence"]


# ---- the final decision -----------------------------------------------------------------------
GO = os.path.join("predictions", "ti2026", "fantasy", "preselection_20260811_go.json")


@pytest.mark.skipif(not os.path.exists(GO), reason="decision not generated")
def test_the_final_pick_is_three_distinct_client_visible_names():
    art = json.load(open(GO, encoding="utf-8"))
    from ti_predict.fantasy import build_roster_positions as brp
    assert art["status"] == "GO"
    names, canon = [], []
    for role in ("core", "mid", "support"):
        s = art["selection"][role]
        assert s["client_name"] == brp.client_name(s["canonical"])
        names.append(s["client_name"])
        canon.append(s["canonical"])
    assert len(set(canon)) == 3 and art["distinct_team_constraint"]["satisfied"]
    assert len(set(names)) == 3


@pytest.mark.skipif(not os.path.exists(GO), reason="decision not generated")
def test_the_decision_criterion_is_minimax_expected_regret_not_expected_value():
    """With candidates 0.1 percent apart, the argmax of expected value is not identifiable."""
    art = json.load(open(GO, encoding="utf-8"))
    c = art["decision_criterion"]
    assert c["name"] == "prior-family minimax expected regret"
    assert len(c["families"]) == 5
    assert "not identifiable" in c["why_not_expected_value"]


@pytest.mark.skipif(not os.path.exists(GO), reason="decision not generated")
def test_unobtainable_facts_are_not_treated_as_blockers():
    art = json.load(open(GO, encoding="utf-8"))
    s = art["structurally_unavailable_not_missing"]
    assert "does not exist yet" in s["consequence"]
    assert "after the decision" in s["consequence"]


def test_the_coach_perturbation_is_bounded_by_the_largest_offered_title():
    """The bound has to come from the real pool, not from a number chosen for convenience."""
    pool = fq.load_rules()["coach_titles"]["selectable_pool_2026"]
    biggest = max(t["bonus_percent"] for t in pool["prefixes"] + pool["suffixes"]) / 100.0
    assert ps.MAX_COACH_BONUS == pytest.approx(biggest)


def test_the_coach_perturbation_is_a_per_team_multiplier():
    rng = np.random.default_rng(0)
    f = ps.coach_perturbation(rng, 6, 0.5)
    assert f.shape == (6,)
    assert (f >= 1.0).all() and (f <= 1.0 + ps.MAX_COACH_BONUS * 0.5 + 1e-9).all()


def test_minimax_expected_regret_picks_the_never_badly_wrong_candidate():
    """Not the one with the best average: the one whose WORST family expectation is smallest."""
    import numpy as _np
    score = _np.array([[10.0, 9.5], [1.0, 9.4], [10.0, 9.6]])
    reg = ps.expected_regret(score)
    assert reg[1] < reg[0]          # B is never far off; A is sometimes catastrophic
