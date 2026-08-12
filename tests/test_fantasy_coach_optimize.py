"""Properties of the coach pricer, checked by recomputation rather than by reading the artifact.

An earlier version of this file asserted that particular numbers appeared in a generated JSON,
which tests nothing except that the file was written. What matters is whether the pricer has the
properties the scoring rules demand: that the bonus lands on the player-game and not on the role
average, that a trigger correlated with bad games is worth less than its frequency implies, and
that a trigger uncorrelated with anything is worth exactly its frequency implies.
"""
import inspect
import json
import math
import os

import numpy as np
import pytest

from ti_predict.fantasy import coach_optimize as co
from ti_predict.fantasy import questions as fq


def _per(series):
    """{event: {series: {match: {account: total}}}} from a compact literal."""
    return {"E": {sid: {mid: dict(accts) for mid, accts in maps.items()}
                  for sid, maps in series.items()}}


def _flat(bonus):
    return lambda _mid, _acct: bonus


# ------------------------------------------------------------------ layering properties

def test_a_uniform_bonus_scales_the_period_score_by_exactly_that_bonus():
    """The calibration case. If it fires on every game, the gain must equal the bonus exactly."""
    per = _per({"s1": {1: {10: 100.0}, 2: {10: 80.0}, 3: {10: 60.0}},
                "s2": {4: {10: 90.0}, 5: {10: 70.0}}})
    counts = np.array([1, 2, 3, 2])
    base = co.price(per, 1, counts, co._zero)
    got = co.price(per, 1, counts, _flat(0.20))
    assert got / base - 1.0 == pytest.approx(0.20, abs=1e-12)


def test_the_bonus_lands_on_the_player_game_not_on_the_role_average():
    """Two players, one on a qualifying hero. Averaging the triggers instead would be wrong.

    Role score must be mean(100*1.5, 20*1.0) = 85, not mean(100, 20) * (1 + 0.5/2) = 75.
    """
    per = _per({"s": {1: {10: 100.0, 11: 20.0}, 2: {10: 100.0, 11: 20.0}}})
    only_10 = lambda _mid, acct: 0.50 if acct == 10 else 0.0     # noqa: E731
    got = co.series_scores(per, 2, only_10)["E"]["s"]
    assert got == pytest.approx(2 * 85.0)
    assert got != pytest.approx(2 * 75.0)


def test_a_trigger_confined_to_discarded_games_is_worth_nothing():
    """Top two of the series are kept, so a bonus on the third game cannot show up at all."""
    per = _per({"s": {1: {10: 100.0}, 2: {10: 90.0}, 3: {10: 10.0}}})
    counts = np.array([1, 1, 1])
    base = co.price(per, 1, counts, co._zero)
    worst_only = lambda mid, _acct: 0.90 if mid == 3 else 0.0     # noqa: E731
    assert co.price(per, 1, counts, worst_only) == pytest.approx(base)


def test_a_trigger_on_the_weak_series_is_worth_less_than_its_frequency_implies():
    """The Underdog's shape: fires half the time, on the half the period's max throws away."""
    per = _per({"weak": {1: {10: 10.0}, 2: {10: 10.0}},
                "strong": {3: {10: 100.0}, 4: {10: 100.0}}})
    counts = np.full(2000, 2)
    base = co.price(per, 1, counts, co._zero)
    weak_only = lambda mid, _acct: 0.50 if mid in (1, 2) else 0.0     # noqa: E731
    exact = co.price(per, 1, counts, weak_only) / base - 1.0
    naive = 0.50 * 0.50           # fires on half of all player-maps
    assert exact < naive / 2
    assert co.attenuation(exact, 0.50, 50) < 0.5


def test_an_uncorrelated_trigger_keeps_its_full_naive_value():
    """the Lucky's shape: the trigger says nothing about the game, so nothing is attenuated."""
    per = _per({"a": {1: {10: 100.0}, 2: {10: 100.0}},
                "b": {3: {10: 40.0}, 4: {10: 40.0}}})
    counts = np.full(2000, 2)
    base = co.price(per, 1, counts, co._zero)
    exact = co.price(per, 1, counts, _flat(0.20)) / base - 1.0
    assert co.attenuation(exact, 1.0, 20) == pytest.approx(1.0, abs=1e-9)


def test_more_series_never_lowers_the_expected_period_score():
    """The period keeps a maximum, so exposure is monotone. A team that plays more cannot lose."""
    scores = {"E": {f"s{i}": float(i) for i in range(20)}}
    vals = [co.expected_period(scores, np.full(3000, k)) for k in (1, 3, 6)]
    assert vals[0] < vals[1] < vals[2]


def test_a_role_scores_only_when_every_current_player_appears():
    """A game with one of the two players is a stand-in, not a role score, and must be dropped."""
    per = _per({"s": {1: {10: 100.0}, 2: {10: 100.0, 11: 50.0}, 3: {10: 100.0, 11: 50.0}}})
    assert co.series_scores(per, 2, co._zero)["E"]["s"] == pytest.approx(2 * 75.0)


def test_a_series_with_too_few_complete_games_is_dropped_entirely():
    per = _per({"s": {1: {10: 100.0}}})
    assert co.series_scores(per, 1, co._zero) == {}


# --------------------------------------------------------- what the public numbers mean

def test_the_community_categories_overlap_so_a_share_of_the_eight_is_not_a_denominator():
    """The reading that divides one value by the sum of eight is arithmetically impossible."""
    with open(co.COMMUNITY, encoding="utf-8") as fh:
        players = json.load(fh)["players"]
    sums = [sum(v.values()) for v in players.values()]
    assert max(sums) > 100.0
    assert sum(1 for s in sums if s > 100.0) > len(sums) / 2


def test_the_parser_reads_the_source_rather_than_a_transcription():
    text = ('const x = [{name:"Alpha",values:v(1,2,3,4,5,6,7,8)},'
            '{name:"Beta",values:v(10,20,30,40,50,60,70,80)}];')
    got = co.parse_community_frequencies(text)
    assert got["Alpha"]["crimson"] == 1 and got["Alpha"]["heroic"] == 8
    assert got["Beta"]["elemental"] == 60


def test_replication_recovers_a_frequency_it_was_given_exactly():
    """A player whose games are 50 percent red must come back as 50 percent, not as a count."""
    cats = {1: {"isred": True}, 2: {"isred": False}}
    rows = []
    for p in range(6):
        for i in range(20):
            rows.append({"player_name": f"P{p}", "hero_id": str(1 if i % 2 else 2)})
    community = {f"P{p}": {"crimson": 50.0} for p in range(6)}
    got = co.replicate_frequencies(rows, cats, community)["Crimson"]
    assert got["our_mean_percent"] == pytest.approx(50.0)
    assert got["mean_offset"] == pytest.approx(0.0)


# ----------------------------------------------------------------- evidence boundaries

def test_a_slot_with_no_public_source_is_dropped_loudly_not_zeroed_quietly():
    state = {"banners": {"support": {"slots": [
        {"stat": "gpm", "displayed_multiplier": 1.5},
        {"stat": "watchers_taken", "displayed_multiplier": 1.3}]}}}
    keep, drop = co.banner_weights(state)["support"]
    assert keep == [("gpm", 1.5)]
    assert drop == ["watchers_taken"]


def test_the_tormentor_bound_treats_a_zero_as_an_exact_negative():
    """killed_by credits heroes only, so no unaccounted death means no Tormentor death."""
    extras = {1: {"all_unattributed_deaths": 0}, 2: {"all_unattributed_deaths": 0},
              3: {"all_unattributed_deaths": 2}, 4: {"all_unattributed_deaths": 0}}
    got = co.tormented_bound(extras, "all")
    assert got["exact_negatives"] == 3
    assert got["upper_bound_trigger_rate"] == pytest.approx(0.25)


def test_the_suffix_bonuses_are_exactly_what_the_client_displays():
    """Three of these were wrong in a hand-typed copy of the ruleset. Pin all eight."""
    assert co.SUFFIX_BONUS == {
        "the Tormented": 23, "the Flayed Twins Acolyte": 9, "the Patient": 23,
        "the Underdog": 6, "the Decisive": 24, "the Clutch": 16,
        "the Lucky": 21, "the Cruel": 13}


def test_the_bonuses_are_read_from_the_ruleset_and_not_re_typed_in_the_module():
    """The root cause was a second copy of a fact. There must not be a second copy."""
    src = inspect.getsource(co)
    body = src.split("def _pool_bonuses", 1)[1].split("PREFIX_BONUS =", 1)[0]
    assert 'bonus_percent' in body            # it reads the field
    for stale in ('"the Flayed Twins Acolyte": 30', '"the Tormented": 13', '"the Cruel": 19'):
        assert stale not in src, f"stale suffix constant still present: {stale}"
    pool = fq.load_rules()["coach_titles"]["selectable_pool_2026"]["suffixes"]
    assert co.SUFFIX_BONUS == {e["name"]: e["bonus_percent"] for e in pool}


def test_the_tormented_breakpoint_is_computed_at_twenty_three_percent():
    """At 13 percent the breakpoint sits roughly twice as high; the verdict must not inherit it."""
    at_23 = co.breakpoint_rate(0.03262, co.SUFFIX_BONUS["the Tormented"], 1.864)
    at_13 = co.breakpoint_rate(0.03262, 13, 1.864)
    assert at_23 == pytest.approx(0.0761, abs=5e-4)
    assert at_13 > 1.7 * at_23


def test_a_game_level_condition_counts_once_per_match_not_once_per_player():
    """Eight of our players in one game is one coin flip, not eight."""
    matches = {101, 102, 103}
    assert co.bernoulli_units("match", matches, "Xtreme Gaming") == {m: m for m in matches}
    team = co.bernoulli_units("team_game", matches, "Xtreme Gaming")
    assert set(team) == {(m, "Xtreme Gaming") for m in matches}
    assert len(team) == len(matches)


def test_duplicate_player_rows_cannot_tighten_a_match_level_bound():
    """The bug this guards: more players per game must not shrink a zero-event interval."""
    per_one = {"E": {"s": {1: {10: 5.0}, 2: {10: 5.0}}}}
    per_many = {"E": {"s": {1: {10: 5.0, 11: 5.0}, 2: {10: 5.0, 11: 5.0}}}}
    a = co.scored_matches(per_one, 1)
    b = co.scored_matches(per_many, 2)
    assert a == b == {1, 2}
    assert len(co.bernoulli_units("match", b, "Org")) == 2


def test_only_complete_series_contribute_matches_to_the_denominator():
    per = {"E": {"good": {1: {10: 1.0}, 2: {10: 1.0}}, "short": {3: {10: 1.0}}}}
    assert co.scored_matches(per, 1) == {1, 2}


def test_every_suffix_declares_the_unit_its_condition_is_drawn_on():
    assert set(co.SUFFIX_SCOPE) == set(co.SUFFIX_BONUS)
    assert co.SUFFIX_SCOPE["the Underdog"] == "team_game"
    assert all(co.SUFFIX_SCOPE[s] == "match" for s in co.SUFFIX_BONUS if s != "the Underdog")


def test_every_prefix_is_classified_and_none_is_silently_missing():
    covered = set(co.PREFIX_FLAG) | set(co.PREFIX_NO_TABLE)
    assert covered == set(co.PREFIX_BONUS)


def test_the_first_blood_suffixes_are_read_off_the_same_field_in_opposite_directions():
    """the Patient wants a late first blood; the Acolyte wants one before the horn, hence negative."""
    rows = [{"match_id": "1", "account_id": "10", "duration": "2000", "win": "1",
             "start_time": "1000", "_series": "s", "_league": "L"}]
    for fb, patient, acolyte in ((900, True, False), (100, False, False), (-3, False, True)):
        table = co.suffix_trigger_table(rows, {1: {"first_blood_time": fb}})
        assert table[(1, 10)]["the Patient"] is patient
        assert table[(1, 10)]["the Flayed Twins Acolyte"] is acolyte


# ------------------------------------------------------------------- end-to-end sanity

ART = os.path.join("predictions", "ti2026", "fantasy", "coach_pricing_20260812.json")


@pytest.mark.skipif(not os.path.exists(ART), reason="coach pricing not generated")
def test_the_published_totals_are_reproduced_by_rerunning_the_generator():
    """The artifact must be a function of the inputs, not a hand-written table."""
    with open(ART, encoding="utf-8") as fh:
        art = json.load(fh)
    ex = art.get("exact_pricing")
    if not ex:
        pytest.skip("artifact predates the generator")
    got = co.build(os.path.join("predictions", "ti2026", "fantasy",
                                ex["state"]), draws=ex["draws"])
    for k, v in ex["total_gain_over_no_coach"].items():
        assert got["total_gain_over_no_coach"][k] == pytest.approx(v, abs=1e-9), k
    assert not math.isnan(got["roles"]["core"]["base_expected_period_score"])
