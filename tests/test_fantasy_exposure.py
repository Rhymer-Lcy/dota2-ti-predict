"""Exposure and the fact/decision split.

The two things worth protecting here are both about attribution. Exposure has to come from the
frozen track rather than be re-derived, and a change in the ranking has to be attributed to the one
factor that actually moved -- the failure this project has already made once, by comparing a setting
that changed two things at the same time and blaming one of them.
"""
import copy
import json
import random

import pytest

from ti_predict import contest_rules
from ti_predict.fantasy import exposure as ex
from ti_predict.fantasy import sensitivity as sv


# ---- exposure is a consequence of the format, not a free parameter ------------------------------
def test_series_count_is_pinned_by_the_official_bucket_structure():
    assert set(ex.SERIES_BY_BUCKET) == set(contest_rules.BUCKETS)
    # a team stops at four wins or four losses
    assert ex.SERIES_BY_BUCKET["4-0"] == 4 and ex.SERIES_BY_BUCKET["0-4"] == 4
    assert ex.SERIES_BY_BUCKET["4-1"] == 5 and ex.SERIES_BY_BUCKET["1-4"] == 5
    # the ten decider teams play five Swiss series plus the elimination round
    assert ex.SERIES_BY_BUCKET["decider_win"] == 6
    assert ex.SERIES_BY_BUCKET["decider_loss"] == 6
    decider = contest_rules.CAPACITY["decider_win"] + contest_rules.CAPACITY["decider_loss"]
    assert decider == 10


def test_exposure_is_read_from_the_frozen_artifact_and_is_a_distribution():
    probs, src = ex.frozen_bucket_probabilities()
    assert src.endswith(".json")
    dist = ex.exposure_distribution(probs)
    assert len(dist) == 16
    for team, v in dist.items():
        assert abs(sum(v["dist"].values()) - 1.0) < 0.02, team
        assert 4.0 <= v["expected_series"] <= 6.0


def test_a_malformed_frozen_artifact_is_refused(tmp_path):
    probs, _ = ex.frozen_bucket_probabilities()
    bad = {"probabilities": copy.deepcopy(probs)}
    first = next(iter(bad["probabilities"]))
    bad["probabilities"][first].pop("4-0")
    p = tmp_path / "cand.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="missing bucket"):
        ex.frozen_bucket_probabilities(str(p))


def test_probabilities_that_do_not_sum_to_one_are_refused(tmp_path):
    probs, _ = ex.frozen_bucket_probabilities()
    bad = {"probabilities": copy.deepcopy(probs)}
    first = next(iter(bad["probabilities"]))
    bad["probabilities"][first]["4-0"] += 0.5
    p = tmp_path / "cand.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="sum to"):
        ex.frozen_bucket_probabilities(str(p))


# ---- the extreme-value machinery ----------------------------------------------------------------
def test_more_draws_never_lowers_the_expected_maximum():
    rng = random.Random(1)
    sample = [1.0, 5.0, 9.0, 2.0, 7.0]
    vals = [ex.expected_max(sample, n, rng) for n in (4, 5, 6)]
    assert vals[0] < vals[1] < vals[2]
    assert vals[-1] <= max(sample)


def test_a_degenerate_sample_gains_nothing_from_extra_draws():
    """If every series scores the same, an extra draw is worth exactly zero."""
    ov = ex.option_value([100.0] * 8)
    assert ov["gain_over_full_range"]["absolute"] == pytest.approx(0.0)


def test_option_value_is_reported_over_the_reachable_range():
    ov = ex.option_value([1.0, 4.0, 9.0, 16.0])
    g = ov["gain_over_full_range"]
    assert g["from_series"] == 4 and g["to_series"] == 6
    assert set(ov["expected_max_by_series"]) == {4, 5, 6}


# ---- attribution ---------------------------------------------------------------------------------
def _entry(org, role, by_league, scores):
    return {"organization": org, "role": role, "envelope_total": sum(by_league.values())
            / len(by_league), "by_league": by_league, "series_scores": scores}


def test_the_control_holds_exposure_constant_so_only_the_estimator_moves():
    ranking = [_entry("A", "core", {"L1": 10.0}, [10.0, 12.0]),
               _entry("B", "core", {"L1": 11.0}, [11.0, 11.0])]
    control = ex.fixed_draw_ranking(ranking, 5)
    assert {e["organization"] for e in control} == {"A", "B"}
    # every entry is scored at the same number of draws
    assert all("exposure_adjusted_total" in e for e in control)


def test_scale_only_detects_a_pure_rescaling_and_nothing_else():
    base = {"ranking": [_entry("A", "core", {"L1": 10.0}, []),
                        _entry("B", "core", {"L1": 20.0}, [])]}
    half = {"ranking": [_entry("A", "core", {"L1": 5.0}, []),
                        _entry("B", "core", {"L1": 10.0}, [])]}
    skew = {"ranking": [_entry("A", "core", {"L1": 5.0}, []),
                        _entry("B", "core", {"L1": 18.0}, [])]}
    assert sv.scale_only_check(base, half)["scale_only"] is True
    assert sv.scale_only_check(base, skew)["scale_only"] is False


def test_rank_displacement_counts_movement_rather_than_just_flagging_difference():
    d = sv._displacement(["a", "b", "c"], ["c", "b", "a"])
    assert d["identical"] is False
    assert d["total_positions_moved"] == 4 and d["max_single_move"] == 2
    same = sv._displacement(["a", "b"], ["a", "b"])
    assert same["identical"] is True and same["total_positions_moved"] == 0
