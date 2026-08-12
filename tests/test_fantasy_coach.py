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


def test_the_artifact_records_how_to_regenerate_itself(art):
    assert art["generated_by"] == "ti_predict.fantasy.coach_optimize"
    assert "--state" in art["regenerate"]
