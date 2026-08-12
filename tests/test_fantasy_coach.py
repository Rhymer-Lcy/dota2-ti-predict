"""Discipline of the published coach artifact: what it claims, and what it admits it cannot.

This file deliberately does NOT check that particular gains appear in the JSON -- that would only
prove the file was written. Recomputation lives in test_fantasy_coach_optimize. What is checked
here is the part a generator cannot enforce on its own: that every title is classified, that a
retracted claim stays retracted, that the recommendation is not dressed up as final, and that the
evidence is attributed to the sources it actually came from.
"""
import json
import os

import pytest

from ti_predict.fantasy import coach_optimize as co

ART = os.path.join("predictions", "ti2026", "fantasy", "coach_pricing_20260812.json")
pytestmark = pytest.mark.skipif(not os.path.exists(ART), reason="coach pricing not generated")


@pytest.fixture(scope="module")
def art():
    with open(ART, encoding="utf-8") as fh:
        return json.load(fh)


def test_the_recommendation_is_never_labelled_final(art):
    assert art["label"].startswith("BEST-KNOWN PROVISIONAL")
    # scan everything except the label, whose whole job is to deny those two words
    body = json.dumps({k: v for k, v in art.items() if k != "label"})
    assert "ROBUST OPTIMUM" not in body
    assert '"FINAL"' not in body


def test_the_two_readings_claim_is_recorded_as_withdrawn(art):
    """The retraction has to survive in the file, or the next round will re-derive the error."""
    w = art["withdrawn_claim"]
    assert w["status"] == "WITHDRAWN"
    assert "two equally admissible readings" in w["claim"]
    assert "the categories overlap" in w["why"]
    assert "sum of the eight categories" in w["why"]


def test_the_two_community_sources_are_both_named_and_the_client_is_not_one_of_them(art):
    """A x2 provenance claim has to list two sources; the client panel is a separate observation."""
    p = art["provenance"]
    ids = [s["id"] for s in p["tier_2_independent_community"]]
    assert any("Kadadji1" in i for i in ids)
    assert any("MyKa322" in i for i in ids)
    obs = [s["id"] for s in p["user_runtime_observation"]]
    assert any("client" in i for i in obs)
    assert not any("client" in i for i in ids)
    assert p["tier_1_valve"] == []


def test_every_prefix_is_placed_in_exactly_one_evidence_class(art):
    cov = art["exact_pricing"]["prefix_coverage"]
    classes = [cov["exact"], cov["lower_bound"], cov["no_category_table"]]
    flat = [p for c in classes for p in c]
    assert len(flat) == len(set(flat)) == len(co.PREFIX_BONUS)
    assert set(flat) == set(co.PREFIX_BONUS)


def test_every_suffix_is_either_priced_or_carries_a_breakpoint(art):
    ex = art["exact_pricing"]
    priced = set(ex["priced_suffixes"])
    unpriced = ex["unpriced_suffixes"]
    assert priced | set(unpriced) == set(co.SUFFIX_BONUS)
    for name, u in unpriced.items():
        assert u["classification"] in ("PARTIAL-BOUNDED", "UNAVAILABLE"), name
        assert u["breakpoint_rate_if_uncorrelated"] > 0, name
        assert u["breakpoint_rate_if_tied_to_losing"] >= u["breakpoint_rate_if_uncorrelated"], name


def test_an_unavailable_suffix_says_what_would_be_needed_rather_than_just_unavailable(art):
    cruel = art["exact_pricing"]["unpriced_suffixes"].get("the Cruel")
    if cruel is None:
        pytest.skip("the Cruel was priced")
    assert cruel["classification"] == "UNAVAILABLE"
    assert "replay" in cruel["why"]


def test_the_frequency_reading_is_backed_by_replication_not_by_assertion(art):
    """Every prefix we can tag must be reproduced against the community numbers, and agree."""
    rep = art["exact_pricing"]["frequency_replication"]
    assert set(rep) == set(co.PREFIX_FLAG)
    for name, r in rep.items():
        assert r["players"] >= 20, name
        assert r["correlation"] > 0.6, name
        assert abs(r["mean_offset"]) < 10.0, name


def test_a_role_that_drops_a_slot_says_which_slot_it_dropped(art):
    for role, v in art["exact_pricing"]["roles"].items():
        if v.get("priced") and v["dropped_slots"]:
            assert all(s in co.bl.UNAVAILABLE or s not in co.bl.STAT_COLUMNS
                       for s in v["dropped_slots"]), role


def test_a_partial_fetch_is_never_reported_as_a_population_bound(art):
    """New matches raise the numerator too, and the unfetched remainder is the latest slice."""
    ex = art["exact_pricing"]
    m = ex["missingness"]
    fp_ = ex["coverage"]["fingerprint"]
    complete = fp_["coverage_complete"]
    assert m["is_missingness_ignorable"] is complete
    # completeness is a claim about the target set, not about a row count
    assert complete == (fp_["missing_matches"] == 0
                        and fp_["fetched_matches"] == fp_["expected_matches"])
    assert len(fp_["sha256"]) == 64
    for name, b in ex["population_bounds"].items():
        if not isinstance(b, dict) or "scope_of_validity" not in b:
            continue
        assert b["scope_of_validity"] == ("population" if complete
                                          else "observed chronological prefix only"), name
    if not complete:
        assert "either direction" in m["consequence"]


def test_the_untabled_prefix_figures_are_named_as_extrapolations_not_ceilings(art):
    """Nothing bounds an unmeasured prefix by the largest attenuation among measured ones."""
    ex = art["exact_pricing"]
    assert "untabled_prefix_total_extrapolation" in ex
    assert "untabled_prefix_total_ceiling" not in ex
    for role, v in ex["roles"].items():
        if not v.get("priced"):
            continue
        assert "untabled_prefix_ceiling" not in v, role
        for p, e in v["untabled_prefix_extrapolation"].items():
            if e:
                assert "not_a_ceiling" in e, f"{role}/{p}"


def test_both_overclaims_are_recorded_as_withdrawn(art):
    claims = {w["claim"]: w for w in art["withdrawn_claims"]}
    assert any("cannot change the conclusion" in c for c in claims)
    assert any("their ceiling" in c for c in claims)
    assert all(w["status"].startswith("WITHDRAWN") for w in claims.values())


def test_an_exclusion_that_rests_on_an_assumption_says_so(art):
    """The same discipline as the prefix ceiling: largest observed is not largest possible."""
    for name, u in art["exact_pricing"]["unpriced_suffixes"].items():
        assert "not_a_proven_exclusion" in u, name
    t = art["exact_pricing"]["unpriced_suffixes"].get("the Tormented")
    if t and t.get("required_attenuation_to_compete"):
        assert t["required_attenuation_to_compete"] > t["largest_attenuation_measured"]
        assert "under a stated assumption" in t["verdict"] or "LIVE" in t["verdict"]


def test_the_freeze_is_derived_from_rival_status_and_not_asserted(art):
    """No suffix may be frozen while a rival sits in an unresolved evidence class."""
    g = art["exact_pricing"]["suffix_grade"]
    cls = art["exact_pricing"]["suffix_classification"]
    unresolved = [s for s, c in cls.items() if c not in ("COMPLETE", "UNAVAILABLE")]
    assert g["unresolved_rivals"] == unresolved
    gap = g.get("gap_bootstrap")
    separated = bool(gap and gap["separated_at_95"])
    # a freeze needs BOTH: no unresolved rival, and the leader separated from the runner-up
    if unresolved or not separated:
        assert not g["grade"].startswith("FROZEN"), (unresolved, gap)
        assert g["grade"].startswith("DECISION-PREFERRED")
    else:
        assert g["grade"].startswith("FROZEN")
    assert art["label_by_component"]["suffix_choice"]["grade"] == g["grade"]


def test_a_leader_inside_the_bootstrap_interval_is_not_called_settled(art):
    """Half a point between two suffixes resting on a handful of games is not a difference."""
    gap = art["exact_pricing"]["suffix_grade"].get("gap_bootstrap")
    if not gap:
        pytest.skip("only one scoreable suffix")
    assert gap["p05"] <= gap["mean_gap"] <= gap["p95"]
    straddles = gap["p05"] < 0 < gap["p95"]
    assert gap["separated_at_95"] is not straddles
    if straddles:
        assert 0.05 < gap["p_a_ahead"] < 0.95


def test_the_tormentor_residual_inference_is_recorded_as_withdrawn(art):
    claims = [w["claim"] for w in art["withdrawn_claims"]]
    assert any("upper bound on the Tormented" in c for c in claims)
    w = next(w for w in art["withdrawn_claims"] if "upper bound on the Tormented" in w["claim"])
    assert w["status"] == "WITHDRAWN"
    assert "killed_by is not hero-only" in w["why"]


def test_the_coach_change_cost_has_exactly_one_consistent_statement(art):
    """The ruleset held this all along; the artifact must cite it, not restate it differently."""
    from ti_predict.fantasy import questions as fq
    c = art["coach_change_cost"]
    assert c["cost"] == "0 roll tokens" and c["reversible"] is True
    assert c["grade"] == "CONFIRMED"
    confirmed = fq.load_rules()["coach_titles"]["confirmed"]
    assert "changed freely without spending roll tokens" in confirmed
    # scan everything except the withdrawal records, whose job is to quote the retracted wording
    body = json.dumps({k: v for k, v in art.items() if k != "withdrawn_claims"})
    assert "never been verified" not in body
    assert "cost advantage" not in body.replace("no cost advantage", "")


def test_estimator_uncertainty_and_the_predictive_distribution_are_never_conflated(art):
    """Two different questions, so two different fields with two different names."""
    ex = art["exact_pricing"]
    gap = ex["suffix_grade"]["gap_bootstrap"]
    assert "ESTIMATOR uncertainty" in gap["what_this_is"]
    assert "decision_rule" not in gap          # the old field mixed both
    pred = ex["joint_closing"]["by_stacking"]["additive"]["predictive_distribution"]
    assert "NOT estimator uncertainty" in pred["what_this_is"]
    # the predictive side reports period scores; the estimator side reports a gap in gain
    assert set(pred["paired_difference"]) & {"p05", "p95"} == set()
    assert set(gap) & {"median", "p10", "p90"} == set()


def test_bootstrap_interval_endpoints_are_not_called_minimax_regret(art):
    ex = art["exact_pricing"]
    e = ex["suffix_grade"]["gap_bootstrap"]["interval_endpoints"]
    assert "worst_endpoint_over_the_90_percent_bootstrap_interval" in e
    # no KEY may name these regrets; the disclaimer text is allowed to say what they are not
    assert not any("regret" in k for k in e
                   if k != "not_minimax_regret")
    # a real one exists, over a named scenario family
    sm = ex["scenario_minimax_regret"]
    assert sm["is_full_cartesian_product"] is False
    full = ex["cartesian_scenario_regret"]
    assert "event state" in full["scenario_family"]
    assert "recency half-life" in full["scenario_family"]
    assert len(sm["scenarios"]) >= 4
    assert sm["minimax_choice"] in sm["max_regret"]
    assert sm["max_regret"][sm["minimax_choice"]] == min(sm["max_regret"].values())


def test_the_joint_comparison_is_the_one_the_account_actually_faces(art):
    """Prefix held fixed, suffix varied -- not two standalone gains against no coach."""
    jc = art["exact_pricing"]["joint_closing"]
    assert jc["prefix_held_fixed"] == "Elemental"
    for stacking in ("additive", "multiplicative"):
        b = jc["by_stacking"][stacking]
        assert set(b["joint_gain"]) == set(jc["contenders"])
        resid = b["standalone_sum_approximation"]["interaction_residual"]
        # the whole point: the exact joint is not the sum of standalone gains
        assert any(abs(v) > 1e-6 for v in resid.values())


def test_the_event_aggregation_choice_is_not_recorded_as_a_confirmed_fact():
    """Equal weight per event is an estimator, not a Valve rule or an observable."""
    from ti_predict.fantasy import questions as fq
    u = next(x for x in fq.load_rules()["unknowns"]
             if x["id"] == "historical_event_aggregation")
    assert u["fact_status"] != "CONFIRMED"
    assert u.get("is_estimator_choice_not_a_rule") is True
    assert u.get("model_status") == "SELECTED"


def test_event_sensitivity_is_reported_rather_than_smoothed_over(art):
    loo = art["exact_pricing"]["leave_one_event_out"]
    winners = {f["winner"] for f in loo["folds"]}
    assert loo["winner_flips_when_an_event_is_dropped"] == (len(winners) > 1)
    assert loo["event_sensitive"] == loo["winner_flips_when_an_event_is_dropped"]
    for f in loo["folds"]:
        assert set(f["by_role"]) <= {"core", "mid", "support"}


def test_the_hierarchical_bootstrap_says_how_coarse_it_is(art):
    h = art["exact_pricing"]["hierarchical_bootstrap"]
    assert "three distinct values" in h["what_this_is"]
    assert "coarse" in h["what_this_is"]


def test_the_cross_event_pooling_defect_is_recorded_as_withdrawn(art):
    claims = [w["claim"] for w in art["withdrawn_claims"]]
    assert any("never pooled across events" in c for c in claims)
    assert any("token cost of changing a coach title" in c for c in claims)


def test_no_superseded_prose_survives_outside_the_withdrawal_records(art):
    """Every number in the live body must come from this run, not from a previous conclusion."""
    withdrawn = json.dumps(art["withdrawn_claims"], ensure_ascii=False)
    body = json.dumps(art, ensure_ascii=False).replace(withdrawn, "")
    for stale in ("factor of 2.3", "5.78", "bounded at 5", "Two residuals",
                  "residual_the_Tormented", "beats the next scoreable suffix",
                  "bounded from above", "upside_tail_pick"):
        assert stale not in body, stale


def test_the_incomplete_elemental_predicate_is_declared_and_stress_tested(art):
    m = art["exact_pricing"]["prefix_membership_sensitivity"]
    assert m["predicate_status"].startswith("INCOMPLETE")
    names = {r["assignment"] for r in m["rows"]}
    assert "adversarial_to_leader" in names and "random" in names
    assert m["winner_flips_under_any_assignment"] == (len({r["winner"] for r in m["rows"]}) > 1)


def test_the_recency_family_is_pre_registered_and_enters_the_scenario_regret(art):
    w = art["exact_pricing"]["weighting_sensitivity"]
    lives = {f["half_life_days"] for f in w["folds"]}
    assert lives == {None, 180, 90, 60, 30}
    names = {sc["scenario"] for sc in art["exact_pricing"]["scenario_minimax_regret"]["scenarios"]}
    assert any("recency half-life" in n for n in names)
    assert any("Elemental" in n for n in names)


def test_the_predictive_tail_is_only_used_when_it_is_stable(art):
    d = art["exact_pricing"]["suffix_grade"]["joint_decision"]["D_predictive_utility"]
    stable = (d["p90_winner_stable_across_dependence"]
              and d["p95_winner_stable_across_dependence"]
              and d["median_winner_stable_across_dependence"])
    assert d["usable_as_evidence"] == stable
    if not stable:
        assert "NOT a usable discriminator" in \
            art["exact_pricing"]["dependence_sensitivity"]["verdict"]


def test_the_cruel_breakpoint_is_against_the_joint_leader_not_a_bare_suffix(art):
    c = art["exact_pricing"]["cruel_joint_breakpoint"]
    assert c["leader"].startswith("Elemental + ")
    assert "not_a_mathematical_exclusion" in c
    assert {r["placement"] for r in c["rows"]} == {"random", "best_games"}


def test_the_four_evidence_classes_are_reported_separately_and_never_tallied(art):
    j = art["exact_pricing"]["suffix_grade"]["joint_decision"]
    for key in ("A_point_estimate", "B_estimator_uncertainty",
                "C_modelling_scenario_robustness", "D_predictive_utility"):
        assert key in j
    assert "never tallied" in j["not_a_vote_count"]
    assert "wins 11" not in json.dumps(art, ensure_ascii=False)


def test_the_scenario_family_is_a_real_cartesian_product(art):
    """Appending one-factor sweeps is not a product; the corners are the whole point."""
    ex = art["exact_pricing"]
    c = ex["cartesian_scenario_regret"]
    assert c["is_full_cartesian_product"] is True
    rows = c["scenarios"]
    levels = {f: {str(r[f]) for r in rows}
              for f in ("stacking", "event_state", "recency_half_life_days", "membership")}
    expected = 1
    for v in levels.values():
        expected *= len(v)
    assert c["n_scenarios"] == len(rows) == expected
    seen = {(r["stacking"], r["event_state"], str(r["recency_half_life_days"]), r["membership"])
            for r in rows}
    assert len(seen) == expected          # every combination present exactly once


def test_the_partial_sweep_no_longer_claims_to_be_the_full_family(art):
    scen = art["exact_pricing"]["scenario_minimax_regret"]
    assert scen["is_full_cartesian_product"] is False
    assert "PARTIAL" in scen["scenario_family"]


def test_the_corner_scenarios_are_actually_reached(art):
    """drop the newest event AND weight recency AND grant the worst membership, together."""
    rows = art["exact_pricing"]["cartesian_scenario_regret"]["scenarios"]
    corner = [r for r in rows
              if r["event_state"].startswith("drop")
              and r["recency_half_life_days"] == 30
              and r["membership"].endswith("50pct")]
    assert corner, "the compound corner was never evaluated"
    assert len({r["stacking"] for r in corner}) == 2


def test_the_missing_elemental_mass_is_labelled_an_estimate_not_a_bound(art):
    c = art["exact_pricing"]["cartesian_scenario_regret"]
    note = c["central_missing_mass_is_a_point_estimate_not_a_bound"]
    assert "central estimate" in note["why"]
    assert "drift" in note["why"]
    sets = c["membership_sets"]
    assert any(k.endswith("50pct") for k in sets)
    assert any(k.startswith("hero_consistent") for k in sets)
    assert any(k.startswith("game_level") for k in sets)
    body = json.dumps({k: v for k, v in art.items() if k != "withdrawn_claims"},
                      ensure_ascii=False)
    assert "only 3 unseen" not in body


def test_hero_consistent_and_game_level_stresses_are_both_present_and_distinguished(art):
    sets = art["exact_pricing"]["cartesian_scenario_regret"]["membership_sets"]
    hero = {k: v for k, v in sets.items() if k.startswith("hero_consistent")}
    game = {k: v for k, v in sets.items() if k.startswith("game_level")}
    assert len(hero) == len(game) >= 5
    for v in hero.values():
        assert "hero_consistent" in v["placement"]
    for v in game.values():
        assert "game_level" in v["placement"]


def test_the_runner_up_wins_are_attributed_to_a_factor_rather_than_left_unexplained(art):
    c = art["exact_pricing"]["cartesian_scenario_regret"]
    dec = c["runner_up_win_decomposition"]
    assert set(dec) == {"stacking", "event_state", "recency_half_life_days", "membership"}
    for f, levels in dec.items():
        assert sum(v["runner_up_wins"] for v in levels.values()) == \
            c["scenarios_won_by_runner_up"], f
        assert sum(v["scenarios"] for v in levels.values()) == c["n_scenarios"], f


def test_no_unlabelled_common_rng_predictive_result_survives(art):
    """The artifact may not assert a default dependence and then quietly report another."""
    assert art["exact_pricing"]["dependence_sensitivity"]["default"] == "by_organization"
    for stacking, block in art["exact_pricing"]["joint_closing"]["by_stacking"].items():
        dep = block["predictive_distribution"]["dependence"]
        assert dep == "by_organization" or "DIAGNOSTIC ONLY" in dep, stacking


def test_the_artifact_records_how_to_regenerate_itself(art):
    assert art["generated_by"] == "ti_predict.fantasy.coach_optimize"
    assert "--state" in art["regenerate"]
