"""Properties of the coach pricer, checked by recomputation rather than by reading the artifact.

An earlier version of this file asserted that particular numbers appeared in a generated JSON,
which tests nothing except that the file was written. What matters is whether the pricer has the
properties the scoring rules demand: that the bonus lands on the player-game and not on the role
average, that a trigger correlated with bad games is worth less than its frequency implies, and
that a trigger uncorrelated with anything is worth exactly its frequency implies.
"""
import inspect
import json
from collections import Counter
import math
import os

import numpy as np
import pytest

from ti_predict.fantasy import coach_optimize as co
from ti_predict.fantasy import fetch_match_extras as fme
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


def test_more_series_never_lowers_the_projected_period_score():
    """The period keeps a maximum, so exposure is monotone. A team that plays more cannot lose."""
    scores = {"E": {f"s{i}": float(i) for i in range(20)}}
    vals = [co.project_period(scores, np.full(3000, k)) for k in (1, 3, 6)]
    assert vals[0] < vals[1] < vals[2]


# --------------------------------------------- events are blocks, not a bag of series

FEW_HIGH = {f"h{i}": 100.0 for i in range(2)}
MANY_LOW = {f"l{i}": 10.0 for i in range(40)}


def test_an_event_is_weighted_equally_no_matter_how_many_series_it_left_behind():
    """Two series at a big event must not be drowned by forty at a small one."""
    counts = np.full(3000, 3)
    both = {"few_high": dict(FEW_HIGH), "many_low": dict(MANY_LOW)}
    block = co.project_period(both, counts)
    pooled = co.project_period_pooled(both, counts)
    assert block == pytest.approx((100.0 + 10.0) / 2, abs=1e-9)
    # the withdrawn estimator lands far below, dragged down by sheer series count
    assert pooled < block - 20.0


def test_duplicating_every_series_inside_an_event_does_not_move_the_projection():
    """Same distribution, twice the rows. A period estimate must not notice."""
    counts = np.full(6000, 3)
    once = {"A": {f"s{i}": float(i) for i in range(10)}, "B": dict(MANY_LOW)}
    twice = {"A": {**{f"s{i}": float(i) for i in range(10)},
                   **{f"copy{i}": float(i) for i in range(10)}}, "B": dict(MANY_LOW)}
    a, b = co.project_period(once, counts), co.project_period(twice, counts)
    assert a == pytest.approx(b, rel=0.02)


def test_adding_series_to_one_event_does_not_buy_that_event_more_weight():
    """Attendance is not evidence. Growing one event's pool must not tilt the estimate to it."""
    counts = np.full(6000, 3)
    small = {"A": dict(FEW_HIGH), "B": {f"l{i}": 10.0 for i in range(5)}}
    grown = {"A": dict(FEW_HIGH), "B": {f"l{i}": 10.0 for i in range(200)}}
    assert co.project_period(small, counts) == pytest.approx(
        co.project_period(grown, counts), rel=1e-9)
    # the withdrawn estimator moves a long way on exactly that change
    assert co.project_period_pooled(small, counts) - co.project_period_pooled(
        grown, counts) > 10.0


def test_a_simulated_period_never_mixes_series_from_two_tournaments():
    """A TI run happens inside one event. Its maximum cannot come from a different one."""
    counts = np.full(4000, 5)
    scores = {"A": {"a": 1.0}, "B": {"b": 100.0}}
    # every A-period must score 1 and every B-period 100, so the mean is exactly their average
    assert co.project_period(scores, counts) == pytest.approx(50.5, abs=1e-9)
    # pooling lets an A-period pick up B's series, which lifts it far above 50.5
    assert co.project_period_pooled(scores, counts) > 90.0


def test_the_bootstrap_projects_through_the_same_primitive_as_production():
    """One estimand. If these ever diverge the interval stops describing the estimate."""
    src = inspect.getsource(co.bootstrap_gap)
    assert "project_period(" in src
    assert "np.concatenate" not in src and "extend(" not in src
    assert inspect.getsource(co.price).count("projector(") == 1


def test_the_bootstrap_keeps_series_inside_their_own_event(monkeypatch):
    """Every replicate must hand project_period a dict still keyed by event."""
    per = {"A": {"s1": {1: {10: 10.0}, 2: {10: 10.0}}},
           "B": {"s2": {3: {10: 90.0}, 4: {10: 90.0}}}}
    seen = []
    real = co.project_period
    monkeypatch.setattr(co, "project_period",
                        lambda sc, c, seed=co.SEED: seen.append(sorted(sc)) or real(sc, c, seed))
    table = {(m, 10): {"the Lucky": False, "the Underdog": False} for m in (1, 2, 3, 4)}
    co.bootstrap_gap(per, 1, np.full(50, 2), "the Lucky", "the Underdog", table, reps=3)
    assert seen and all(ev == ["A", "B"] for ev in seen)


def test_a_role_scores_only_when_every_current_player_appears():
    """A game with one of the two players is a stand-in, not a role score, and must be dropped."""
    per = _per({"s": {1: {10: 100.0}, 2: {10: 100.0, 11: 50.0}, 3: {10: 100.0, 11: 50.0}}})
    assert co.series_scores(per, 2, co._zero)["E"]["s"] == pytest.approx(2 * 75.0)


def test_a_series_with_too_few_complete_games_is_dropped_entirely():
    per = _per({"s": {1: {10: 100.0}}})
    assert co.series_scores(per, 1, co._zero) == {}


# ------------------------------------------------------------------- joint pricing

CATS = {7: {"isaquatic": True}, 8: {"isaquatic": False}}
HEROES = {(1, 10): 7, (2, 10): 8, (3, 10): 7, (4, 10): 8}


def _table(trigger_on):
    return {(m, 10): {"the Lucky": m in trigger_on} for m in (1, 2, 3, 4)}


def test_the_joint_bonus_resolves_both_indicators_on_the_same_player_game():
    """Prefix and suffix are decided per player-game, so their overlap is visible there."""
    fn = co.joint_bonus_fn("Elemental", "the Lucky", "additive", HEROES, CATS, _table({1, 2}))
    p, s_ = co.PREFIX_BONUS["Elemental"] / 100, co.SUFFIX_BONUS["the Lucky"] / 100
    assert fn(1, 10) == pytest.approx(p + s_)      # aquatic hero AND lucky duration
    assert fn(2, 10) == pytest.approx(s_)         # lucky only
    assert fn(3, 10) == pytest.approx(p)          # aquatic only
    assert fn(4, 10) == pytest.approx(0.0)        # neither


def test_additive_and_multiplicative_differ_only_where_both_fire():
    add = co.joint_bonus_fn("Elemental", "the Lucky", "additive", HEROES, CATS, _table({1, 2}))
    mul = co.joint_bonus_fn("Elemental", "the Lucky", "multiplicative", HEROES, CATS,
                            _table({1, 2}))
    p, s_ = co.PREFIX_BONUS["Elemental"] / 100, co.SUFFIX_BONUS["the Lucky"] / 100
    assert mul(1, 10) - add(1, 10) == pytest.approx(p * s_)     # the interaction term
    for mid in (2, 3, 4):
        assert mul(mid, 10) == pytest.approx(add(mid, 10))


def test_a_joint_gain_is_not_the_sum_of_two_standalone_gains():
    """top-two and best-series are maxima, so a player-game bonus does not pass through linearly."""
    per = _per({"s1": {1: {10: 100.0}, 2: {10: 99.0}, 3: {10: 98.0}},
                "s2": {4: {10: 90.0}, 5: {10: 10.0}, 6: {10: 10.0}}})
    counts = np.full(4000, 2)
    base = co.price(per, 1, counts, co._zero)
    only_p = lambda mid, _a: 0.30 if mid in (3, 5) else 0.0      # noqa: E731
    only_s = lambda mid, _a: 0.30 if mid in (3, 6) else 0.0      # noqa: E731
    both = lambda mid, a: only_p(mid, a) + only_s(mid, a)        # noqa: E731
    gp = co.price(per, 1, counts, only_p) / base - 1
    gs = co.price(per, 1, counts, only_s) / base - 1
    gj = co.price(per, 1, counts, both) / base - 1
    assert gj != pytest.approx(gp + gs, abs=1e-6)                # interaction is real


def test_the_joint_gains_recompute_from_raw_inputs_rather_than_from_the_artifact():
    """Elemental+X is rebuilt from stats, heroes and extras, then checked against what shipped."""
    art_path = os.path.join("predictions", "ti2026", "fantasy", "coach_pricing_20260812.json")
    if not os.path.exists(art_path):
        pytest.skip("artifact not generated")
    with open(art_path, encoding="utf-8") as fh:
        jc = json.load(fh)["exact_pricing"]["joint_closing"]
    rules = co.bl.load_rules()
    rows, _d, _i = co.bl.load_stats()
    with open(os.path.join("predictions", "ti2026", "fantasy",
                           "account_state_target_20260812b.json"), encoding="utf-8") as fh:
        state = json.load(fh)
    weights = co.banner_weights(state)
    probs, _src = co.ex.frozen_bucket_probabilities()
    roles_map = co.bl.roles_from_roster()
    cats, heroes = co.load_hero_categories(), co.load_hero_maps()
    table = co.suffix_trigger_table(rows, co.load_extras())
    role_inputs = {}
    for role in co.ROLES:
        org = state["banners"][role]["canonical_team"]
        accounts = set(roles_map.get(org, {}).get(role, []))
        keep, _drop = weights[role]
        per = co.player_map_totals(rows, accounts, keep, rules)
        counts = co.exposure_counts(org, probs, 4000)
        role_inputs[role] = (per, len(accounts), counts,
                             co.price(per, len(accounts), counts, co._zero))
    for stacking, block in jc["by_stacking"].items():
        for suffix, published in block["joint_gain"].items():
            got = co.account_gain(role_inputs, lambda _r, s=suffix, st=stacking:
                                  co.joint_bonus_fn("Elemental", s, st, heroes, cats, table))
            assert got == pytest.approx(published, abs=1e-5), (stacking, suffix)


def test_leave_one_event_out_is_deterministic():
    per = _per({"s1": {1: {10: 10.0}, 2: {10: 12.0}},
                "s2": {3: {10: 40.0}, 4: {10: 44.0}}})
    per = {"A": per["E"], "B": {"s3": {5: {10: 90.0}, 6: {10: 95.0}}}}
    ri = {"core": (per, 1, np.full(500, 2), co.price(per, 1, np.full(500, 2), co._zero))}
    a = lambda _r: (lambda mid, _acct: 0.2 if mid in (1, 5) else 0.0)      # noqa: E731
    b = lambda _r: (lambda mid, _acct: 0.2 if mid in (3,) else 0.0)        # noqa: E731
    first = co.leave_one_event_out(ri, a, b)
    assert first == co.leave_one_event_out(ri, a, b)
    assert [f["dropped_event"] for f in first] == ["A", "B"]


def test_the_hierarchical_bootstrap_resamples_events_as_well_as_series(monkeypatch):
    """The outer level must actually vary which events a replicate sees."""
    per = {"A": {"s1": {1: {10: 10.0}, 2: {10: 10.0}}},
           "B": {"s2": {3: {10: 90.0}, 4: {10: 90.0}}}}
    ri = {"core": (per, 1, np.full(200, 2), co.price(per, 1, np.full(200, 2), co._zero))}
    seen = []
    real = co.project_period
    monkeypatch.setattr(co, "project_period",
                        lambda sc, c, seed=co.SEED: seen.append(
                            tuple(sorted(next(iter(v.values())) for v in sc.values())))
                        or real(sc, c, seed))
    zero = lambda _r: co._zero        # noqa: E731
    co.hierarchical_bootstrap(ri, zero, zero, reps=40)
    # with two events resampled with replacement, some replicates must draw the same event twice
    assert len({s for s in seen}) > 1


# ---------------------------------------------- incomplete predicates and dependence

def test_elemental_is_not_recorded_as_an_exact_predicate():
    """The flag is isaquatic; the condition is Aquatic, Fiery or Icy. Those are not the same."""
    assert co.PREFIX_FLAG["Elemental"] == ("isaquatic", "lower_bound")
    assert co.PREFIX_FLAG["Otherworldly"][1] == "lower_bound"
    assert co.PREFIX_FLAG["Crimson"][1] == "exact"
    src = inspect.getsource(co)
    assert "exact Elemental" not in src


def test_unseen_prefix_triggers_can_be_forced_onto_chosen_games():
    """The whole point of the sensitivity: place the unseen mass where it hurts most."""
    cats = {7: {"isaquatic": True}, 8: {"isaquatic": False}}
    heroes = {(1, 10): 8, (2, 10): 8}
    fn = co.joint_bonus_fn("Elemental", None, "additive", heroes, cats, {})
    assert fn(1, 10) == 0.0
    forced = co.joint_bonus_fn("Elemental", None, "additive", heroes, cats, {},
                               extra_prefix=frozenset({(1, 10)}))
    assert forced(1, 10) == pytest.approx(co.PREFIX_BONUS["Elemental"] / 100)
    assert forced(2, 10) == 0.0


def test_the_adversarial_assignment_targets_the_rival_suffix_games():
    plan = {10: {"games": [1, 2, 3, 4], "already": set(), "n_extra": 2}}
    table = {(m, 10): {"the Lucky": m in (3, 4)} for m in (1, 2, 3, 4)}
    got = co.assign_missing(plan, "adversarial_to_leader", table, "the Lucky")
    assert got == frozenset({(3, 10), (4, 10)})


def test_role_random_streams_are_controllable_and_couple_by_organisation():
    """Core and Support are the same club, so at TI they play the same series."""
    orgs = {"core": "Xtreme Gaming", "mid": "Team Yandex", "support": "Xtreme Gaming"}
    by_org = co.role_streams(orgs, "by_organization")
    assert by_org["core"] == by_org["support"] != by_org["mid"]
    indep = co.role_streams(orgs, "independent")
    assert len(set(indep.values())) == 3
    common = co.role_streams(orgs, "common")
    assert len(set(common.values())) == 1


def test_dependence_changes_the_quantiles_but_not_the_mean():
    """A dependence assumption is not neutral: it drives every tail it touches."""
    per = {"E": {f"s{i}": {2 * i: {10: float(i)}, 2 * i + 1: {10: float(i)}}
                 for i in range(1, 40)}}
    ri = {"a": (per, 1, np.full(6000, 1), 1.0), "b": (per, 1, np.full(6000, 1), 1.0)}
    zero = lambda _r: co._zero        # noqa: E731
    common = co.account_period_draws(ri, zero, {"a": 1, "b": 1})
    indep = co.account_period_draws(ri, zero, {"a": 1, "b": 2})
    assert common.mean() == pytest.approx(indep.mean(), rel=0.06)
    assert np.percentile(common, 95) > np.percentile(indep, 95)     # perfect coupling fattens it


def test_recency_weights_come_from_dates_and_are_deterministic():
    dates = {"old": 0, "new": 90 * 86400}
    w = co.recency_weights(["old", "new"], 90, dates)
    assert w["new"] == pytest.approx(1.0)
    assert w["old"] == pytest.approx(0.5)          # exactly one half-life older
    assert co.recency_weights(["old", "new"], None, dates) == {"old": 1.0, "new": 1.0}
    assert w == co.recency_weights(["old", "new"], 90, dates)


def test_a_weighted_projection_follows_the_weights():
    scores = {"lo": {"s": 10.0}, "hi": {"s": 100.0}}
    counts = np.full(500, 1)
    assert co.project_period(scores, counts) == pytest.approx(55.0)
    assert co.project_period(scores, counts, weights={"lo": 0.0, "hi": 1.0}) == pytest.approx(100.0)
    assert co.project_period(scores, counts, weights={"lo": 3.0, "hi": 1.0}) == pytest.approx(32.5)


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


def test_killed_by_is_not_read_as_hero_only():
    """A killed_by carrying a creep and a tower must be recognised as carrying them."""
    kb = {"npc_dota_hero_lina": 3, "npc_dota_creep_badguys_melee": 1,
          "npc_dota_badguys_tower2_mid": 1}
    non_hero = [k for k in kb if not fme.is_hero(k)]
    assert sorted(non_hero) == ["npc_dota_badguys_tower2_mid", "npc_dota_creep_badguys_melee"]
    assert fme.is_hero("npc_dota_hero_lina")


def test_the_unrecorded_killer_residual_is_not_treated_as_non_hero_deaths():
    """Five deaths, four with a killer -- one is a parser gap, not four non-hero deaths."""
    match = {"match_id": 1, "first_blood_time": 100, "duration": 1800,
             "players": [{"account_id": 7, "deaths": 5,
                          "killed_by": {"npc_dota_hero_lina": 2,
                                        "npc_dota_creep_badguys_melee": 1,
                                        "npc_dota_badguys_tower2_mid": 1}}]}
    got = fme.extract(match, {7})
    assert got["all_deaths_with_no_recorded_killer"] == 1     # 5 - 4, not 5 - 2
    assert got["all_tormentor_deaths"] == 0


def test_no_field_or_helper_claims_the_residual_bounds_the_tormentor():
    """The withdrawn inference must not survive as a name."""
    for mod in (co, fme):
        src = inspect.getsource(mod)
        for banned in ("nonhero_deaths", "non_hero_deaths", "tormentor_upper_bound",
                       "unattributed_deaths"):
            assert banned not in src, f"{mod.__name__} still uses {banned}"
    assert not hasattr(co, "tormented_bound")
    assert any(f.endswith("deaths_with_no_recorded_killer") for f in fme.FIELDS)


def test_a_tormentor_death_is_counted_off_the_recorded_killer():
    match = {"match_id": 1, "first_blood_time": 10, "duration": 1800,
             "players": [{"account_id": 7, "deaths": 2,
                          "killed_by": {"npc_dota_hero_lina": 1, "npc_dota_miniboss": 1}},
                         {"account_id": 9, "deaths": 1,
                          "killed_by": {"npc_dota_hero_lina": 1}}]}
    got = fme.extract(match, {7})
    assert got["roster_tormentor_deaths"] == 1
    assert got["all_tormentor_deaths"] == 1
    assert got["roster_deaths_with_no_recorded_killer"] == 0


def test_the_tormentor_rate_is_direct_and_never_calls_itself_a_bound():
    extras = {1: {"all_tormentor_deaths": 0, "all_deaths": 50,
                  "all_deaths_with_no_recorded_killer": 0},
              2: {"all_tormentor_deaths": 1, "all_deaths": 50,
                  "all_deaths_with_no_recorded_killer": 1},
              3: {"all_tormentor_deaths": 0, "all_deaths": 50,
                  "all_deaths_with_no_recorded_killer": 0},
              4: {"all_tormentor_deaths": 0, "all_deaths": 50,
                  "all_deaths_with_no_recorded_killer": 0}}
    got = co.tormented_rate(extras, "all")
    assert got["matches_with_a_tormentor_death"] == 1
    assert got["trigger_rate"] == pytest.approx(0.25)
    assert got["attribution"].startswith("direct")
    assert "bounds neither direction" in got["why_the_residual_is_not_a_bound"]


def test_the_killer_inventory_separates_hero_from_non_hero_keys(tmp_path):
    keys = Counter({"npc_dota_hero_lina": 5, "npc_dota_creep_goodguys_melee": 2,
                    "npc_dota_miniboss": 1})
    out = tmp_path / "inv.json"
    original, fme.OUT_KILLERS = fme.OUT_KILLERS, str(out)
    try:
        fme.write_killers(keys)
    finally:
        fme.OUT_KILLERS = original
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["hero_keys"] == 1 and doc["non_hero_keys"] == 2
    assert doc["tormentor_keys"] == ["npc_dota_miniboss"]


def test_the_tormented_is_decided_from_extras_when_the_field_is_present():
    """Classification must follow attribution capability, not a hand-set label."""
    rows = [{"match_id": "1", "account_id": "10", "duration": "2000", "win": "1",
             "start_time": "1000", "_series": "s", "_league": "L"}]
    without = co.suffix_trigger_table(rows, {})
    assert "the Tormented" not in without[(1, 10)]
    with_ = co.suffix_trigger_table(rows, {1: {"first_blood_time": 10,
                                               "all_tormentor_deaths": 2}})
    assert with_[(1, 10)]["the Tormented"] is True


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
