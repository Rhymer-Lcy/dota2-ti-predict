"""The observed account state, and the worked example that corrected the composition rule.

The client prints, for every emblem, a total percentage and its two components. That makes nine free
exact worked examples of Valve's composition, and they falsified the rule this project had been
using. These tests keep the corrected rule pinned to those nine observations.
"""
import copy
import json

import pytest

from ti_predict.fantasy import account_state as acc
from ti_predict.fantasy import banner_model as bm

STATE = acc.load_state()


def test_the_composition_is_additive_on_a_hundred_percent_base():
    """multiplier = 1 + quality_bonus + net_trait_bonus, not quality * (1 + trait).

    The withdrawn rule made a Tier I emblem score 0.10 of its stat. The client shows 1.10.
    """
    assert bm.slot_weights((0, 0, 0), ("Base", "Base", "Base")) == pytest.approx([1.1, 1.1, 1.1])
    assert bm.slot_weights((4, 4, 4), ("Base", "Base", "Base")) == pytest.approx([2.5, 2.5, 2.5])


def test_all_nine_observed_emblems_reproduce_the_client_exactly():
    for role in acc.ROLES:
        w = acc.banner_weights(STATE, role)
        for i, s in enumerate(STATE["banners"][role]["slots"]):
            assert w[i] == pytest.approx(s["displayed_multiplier"]), f"{role} slot {i + 1}"


def test_each_emblem_equals_one_plus_its_two_printed_components():
    """The client prints the quality line and the trait line separately; they must sum."""
    for role in acc.ROLES:
        for s in STATE["banners"][role]["slots"]:
            assert s["displayed_multiplier"] == pytest.approx(
                1.0 + s["displayed_quality_bonus"] + s["displayed_trait_bonus"])


def test_the_observed_core_banner_pins_the_adjacency_rules():
    """Two Benevolent and one Vampiric in a line reproduce +20 / +10 / +70 and nothing else does."""
    q = (2, 0, 0)
    t = ("Benevolent", "Benevolent", "Vampiric")
    assert bm.trait_bonus(q, t) == pytest.approx([0.20, 0.10, 0.70])
    # slot 2 nets +20 from slot 1's Benevolent and -10 from slot 3's Vampiric
    # slot 3 nets its own +50 plus +20 from slot 2's Benevolent
    # slot 1 gets nothing from its own Benevolent, only +20 from slot 2's


def test_the_observed_mid_banner_pins_the_duplicate_unique_rule():
    """Two Unique emblems cancel each other, and Fractal is dead while two tiers match."""
    assert bm.trait_bonus((0, 2, 0), ("Unique", "Fractal", "Unique")) == pytest.approx([0, 0, 0])
    # remove one Unique and the other immediately pays
    assert bm.trait_bonus((0, 2, 0), ("Base", "Fractal", "Unique"))[2] == pytest.approx(0.30)


def test_the_observed_support_banner_pins_unique_minus_vampiric_adjacency():
    assert bm.trait_bonus((1, 0, 1), ("Vampiric", "Unique", "Friendly")) \
        == pytest.approx([0.50, 0.20, 0.0])


def test_a_state_that_disagrees_with_the_client_is_refused(tmp_path):
    bad = copy.deepcopy(STATE)
    bad["banners"]["mid"]["slots"][0]["displayed_multiplier"] = 1.75
    p = tmp_path / "state.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="Fix the model before optimising"):
        acc.load_state(str(p))


# ---- the roll board -------------------------------------------------------------------------------
MID_VALUES = {"deaths": 2588.2, "wards_placed": 368.7, "stuns": 1129.4}


def test_rerolling_the_mid_red_trait_cannot_lose():
    """A trait reroll is guaranteed to change the trait, which frees the other Unique."""
    r = acc.operation_outcomes(STATE, "mid", "trait", "red", MID_VALUES)
    assert r["target_slot"] == 1 and r["target_stat"] == "deaths"
    assert r["floor"] > 0 and r["downside_probability"] == 0.0
    assert r["expected_delta"] > r["floor"]


def test_rerolling_the_mid_blue_trait_can_lose():
    r = acc.operation_outcomes(STATE, "mid", "trait", "blue", MID_VALUES)
    assert r["floor"] < 0 and r["downside_probability"] > 0


def test_rerolling_the_mid_red_quality_cannot_lose_from_the_bottom_tier():
    r = acc.operation_outcomes(STATE, "mid", "quality", "red", MID_VALUES)
    assert r["floor"] == pytest.approx(0.0)      # already Tier I, so nothing to lose
    assert r["expected_delta"] > 0


def test_a_colour_with_two_emblems_is_reported_as_an_ambiguous_target():
    """Core holds two red emblems and the client never says which one an operation hits."""
    core_values = {"gpm": 2910.6, "roshan_kills": 1449.6, "creep_score": 2838.4}
    r = acc.operation_outcomes(STATE, "core", "trait", "red", core_values)
    assert r["ambiguous_target"] is True
    assert r["candidate_slots"] == [1, 3]


def test_the_unobtainable_support_stat_is_flagged_not_silently_zeroed():
    slot = STATE["banners"]["support"]["slots"][2]
    assert slot["stat"] == "watchers_taken"
    assert "NO PUBLIC PLAYER-LEVEL SOURCE" in slot["data_status"]
    total, missing = acc.banner_score(STATE, "support",
                                      {"runes_grabbed": 900.0, "first_blood": 677.0})
    assert missing == ["watchers_taken"]         # reported, not treated as zero
    assert total > 0


def test_the_state_records_which_account_it_is():
    assert "TARGET ACCOUNT" in STATE["account"]
    assert "Never the operator's test account" in STATE["account"]
    assert STATE["roll_tokens"] == 40


# ---- state 2: after the first reroll ---------------------------------------------------------
import os as _os
STATE2_PATH = _os.path.join("predictions", "ti2026", "fantasy",
                            "account_state_target_20260811b.json")


@pytest.mark.skipif(not _os.path.exists(STATE2_PATH), reason="state 2 not recorded")
def test_state_two_also_reproduces_the_client_exactly():
    s2 = acc.load_state(STATE2_PATH)
    for role in acc.ROLES:
        w = acc.banner_weights(s2, role)
        for i, slot in enumerate(s2["banners"][role]["slots"]):
            assert w[i] == pytest.approx(slot["displayed_multiplier"]), f"{role} slot {i + 1}"


def test_the_vampiric_branch_was_predicted_before_it_happened():
    """The strongest check available: a state that did not exist when the prediction was made.

    Before the reroll the model enumerated the Vampiric outcome as [1.60, 1.50, 1.40]. The client
    then produced exactly that, including the negative trait line on the neighbour.
    """
    q, t = (0, 2, 0), ("Vampiric", "Fractal", "Unique")
    assert bm.slot_weights(q, t) == pytest.approx([1.60, 1.50, 1.40])
    assert bm.trait_bonus(q, t) == pytest.approx([0.50, -0.10, 0.30])


@pytest.mark.skipif(not _os.path.exists(STATE2_PATH), reason="state 2 not recorded")
def test_operations_now_name_their_target_position():
    """The client's own labels answer last round's ambiguity: first / last / random."""
    s2 = acc.load_state(STATE2_PATH)
    which = {o["id"]: o["which"] for o in s2["roll_board"]}
    assert which == {"A2": "last", "B2": "random", "C2": "first"}
    assert s2["resolved_this_round"]["operation_targeting"]["status"] == "CONFIRMED"


@pytest.mark.skipif(not _os.path.exists(STATE2_PATH), reason="state 2 not recorded")
def test_the_duplicate_team_finding_is_not_overstated():
    """Seeing a team offered is not the same as having submitted it."""
    d = acc.load_state(STATE2_PATH)["resolved_this_round"]["duplicate_team_across_roles"]
    assert d["status"] == "PARTIAL" and d["tier"] == "user_runtime_observation"
    assert "not a confirmed successful duplicate submission" in d["caveat"]


@pytest.mark.skipif(not _os.path.exists(STATE2_PATH), reason="state 2 not recorded")
def test_change_team_stays_blocked_while_regeneration_is_unknown():
    """The downside is four times the upside, so the unknown is decision-blocking, not cosmetic."""
    m = acc.load_state(STATE2_PATH)["open_mechanics"]["team_change_regenerates_banner"]
    assert m["status"] == "UNRESOLVED"
    assert m["decision_status"].startswith("BLOCKING")
    assert 0.0 < m["breakeven_probability"] < 1.0
    assert "TEST account" in m["resolution"]


@pytest.mark.skipif(not _os.path.exists(STATE2_PATH), reason="state 2 not recorded")
def test_one_token_was_spent_and_the_trait_actually_changed():
    s1, s2 = acc.load_state(), acc.load_state(STATE2_PATH)
    assert s1["roll_tokens"] - s2["roll_tokens"] == 1
    before = s1["banners"]["mid"]["slots"][0]["trait"]
    after = s2["banners"]["mid"]["slots"][0]["trait"]
    assert before == "Unique" and after == "Vampiric" and before != after
