"""Coach pricing from public evidence, and the joint team+coach structure.

Two failure modes this guards against. First, importing a third party's scoring model along with
its data: the community optimizer composes traits multiplicatively, which the client has already
falsified, so only its definitions are usable. Second, ranking a coach title by frequency times
bonus, which is wrong whenever the trigger correlates with how good the game was.
"""
import json
import os

import pytest

ART = os.path.join("predictions", "ti2026", "fantasy", "coach_pricing_20260812.json")
pytestmark = pytest.mark.skipif(not os.path.exists(ART), reason="coach pricing not generated")


@pytest.fixture(scope="module")
def art():
    with open(ART, encoding="utf-8") as fh:
        return json.load(fh)


def test_the_third_party_scoring_model_is_rejected_but_its_definitions_are_kept(art):
    a = art["public_evidence_audit"]
    assert "MULTIPLICATIVELY" in a["third_party_score_model_rejected"]["finding"]
    assert "1 + quality_bonus + net_trait_bonus" in a["third_party_score_model_rejected"]["our_rule"]
    assert a["prefix_and_suffix_definitions"]["not_tier_1"]


def test_the_denominator_question_is_carried_not_assumed_away(art):
    d = art["denominator_reconstruction"]
    assert d["status"] == "UNRESOLVED as a fact, IRRELEVANT to the decision"
    assert "BOTH readings were carried" in d["resolution"]


def test_both_readings_of_the_community_data_agree_on_the_prefix(art):
    p = art["prefix_pricing"]
    a = max(p["reading_A_percentages"], key=p["reading_A_percentages"].get)
    b = max(p["reading_B_normalised_counts"], key=p["reading_B_normalised_counts"].get)
    assert a == b == "Elemental"
    assert p["decision_status"] == "ROBUST across the two admissible readings"


def test_the_recommended_prefix_is_flagged_as_the_one_we_cannot_verify(art):
    """Elemental is exactly the prefix the public hero table can only lower-bound."""
    cov = art["public_evidence_audit"]["hero_category_table"][
        "coverage_against_the_2026_prefixes"]
    assert any("Elemental" in s for s in cov["strict_subset_only"])
    assert "LOWER-BOUND" in art["public_evidence_audit"]["hero_category_table"]["consequence"]


def test_a_suffix_is_not_ranked_by_frequency_times_bonus(art):
    """the Underdog fires four times as often as the Lucky and is worth less than half."""
    s = art["suffix_pricing"]
    rate = s["empirical_trigger_rates_over_4709_player_maps"]
    gain = s["simulated_gain_over_no_suffix"]
    assert rate["the Underdog"] > 4 * rate["the Lucky"]
    assert gain["the Lucky"] > 2 * gain["the Underdog"]
    assert "correlation between a trigger and the game's score" in \
        s["why_frequency_times_bonus_is_the_wrong_ranking"]


def test_the_unpriced_suffixes_are_reported_with_breakpoints(art):
    u = art["suffix_pricing"]["unpriced_rivals"]
    assert "13.7" in u["the Tormented"]
    assert "live candidate that cannot be priced" in u["honest_caveat"]


def test_the_coach_does_not_move_any_team_choice(art):
    j = art["joint_team_and_coach"]
    assert "ALL EIGHT prefixes" in j["result"]
    assert j["joint_optimum"]["picks"]["core"] == "Xtreme Gaming"
    assert j["joint_optimum"]["picks"]["mid"] == "Team Yandex"


def test_the_remaining_gap_is_entirely_the_unscoreable_support_slot(art):
    j = art["joint_team_and_coach"]
    # the recorded gap is rounded to whole points, so allow one unit of rounding
    assert abs(j["joint_optimum"]["total"] - j["current_triple_under_the_same_coach"]
               - j["gap"]) <= 1
    assert "Watchers" in j["gap_source"]


def test_the_recommendation_is_coach_only_and_free(art):
    r = art["recommendation"]
    assert r["prefix"] == "Elemental" and r["suffix"] == "the Lucky"
    assert r["gain_total"] == r["gain_prefix"] + r["gain_suffix"]
    assert r["cost"].startswith("free")
    assert r["keep"]["support"] == "Xtreme Gaming"     # not switched, the slot is unscoreable
