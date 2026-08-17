"""Period-1 Fantasy value model: the scoring chain, the fast evaluator, leakage and isolation.

The fast path exists so that a reroll decision costs a matrix-vector product instead of a rebuild.
These tests pin the two things that makes true: that every nonlinear step (top-two selection,
best-series maximum) is honoured exactly, and that a missing value can never be read as a zero.
"""
import json
import os
import subprocess

import numpy as np
import pytest

from ti_predict.fantasy import banner_model as bm
from ti_predict.fantasy import build_main_event as bme
from ti_predict.fantasy import fastvalue as fv
from ti_predict.fantasy import main_event_exposure as mex

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_EVENT = os.path.join(REPO, "predictions", "ti2026", "fantasy", "main_event")
BRANCH_POINT = "68cb2a14c32184404ebe5f487abd893ad6e0c484"


# ---------------------------------------------------------------- scoring chain

def _toy_entry(scores_by_game, players_per_game, series_of_game, event_of_series):
    """A hand-built cache entry whose single stat column is the player-game score itself."""
    X, game, series, event = [], [], [], []
    for g, vals in enumerate(scores_by_game):
        assert len(vals) == players_per_game
        for v in vals:
            row = np.full(len(fv.STATS), np.nan)
            row[fv.STAT_INDEX["kills"]] = v
            X.append(row)
            game.append(g)
            series.append(series_of_game[g])
            event.append(event_of_series[series_of_game[g]])
    X = np.array(X)
    game = np.array(game)
    series = np.array(series)
    event = np.array(event)
    return {"X": X, "game": game, "n_games": len(scores_by_game),
            "series": series, "n_series": len(set(series_of_game)),
            "event": event, "n_events": len(set(event_of_series)),
            "prefix": np.zeros((len(X), len(fv.PREFIX_BONUS)), dtype=bool),
            "suffix": np.zeros((len(X), len(fv.SUFFIX_BONUS)), dtype=bool),
            "col_coverage": 1.0 - np.isnan(X).mean(axis=0),
            "game_series": fv._first_of(game, series),
            "series_event": fv._first_of(series, event)}


UNIT_W = np.zeros(len(fv.STATS))
UNIT_W[fv.STAT_INDEX["kills"]] = 1.0


def test_role_score_is_the_arithmetic_mean_of_two_players():
    e = _toy_entry([[100.0, 300.0], [50.0, 50.0]], 2, [0, 0], {0: 0})
    S, _ = fv.series_scores(e, UNIT_W)
    # role-game scores are 200 and 50; the series keeps the top two, so 250
    assert S[0] == pytest.approx(250.0)


def test_series_uses_the_top_two_games_only():
    e = _toy_entry([[10.0], [100.0], [40.0]], 1, [0, 0, 0], {0: 0})
    S, _ = fv.series_scores(e, UNIT_W)
    assert S[0] == pytest.approx(140.0), "100 + 40, never 150"


def test_period_takes_the_best_series_and_never_the_sum():
    e = _toy_entry([[10.0], [10.0], [100.0], [100.0]], 1, [0, 0, 1, 1], {0: 0, 1: 0})
    # two series in one event scoring 20 and 200
    one = fv.period_score(e, UNIT_W, {1: 1.0})
    assert one == pytest.approx(110.0), "one draw averages the two series, it does not add them"
    many = fv.period_score(e, UNIT_W, {6: 1.0})
    assert many < 220.0, "more draws must never reach the sum of both series"
    assert many > one, "more draws must still be worth something"


def test_more_series_helps_monotonically_but_saturates():
    e = _toy_entry([[1.0], [2.0], [10.0], [20.0], [5.0], [6.0]], 1,
                   [0, 0, 1, 1, 2, 2], {0: 0, 1: 0, 2: 0})
    vals = [fv.period_score(e, UNIT_W, {n: 1.0}) for n in (2, 3, 4, 5, 6)]
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:])), "monotone in the number of draws"
    assert vals[-1] <= max(30.0, 3.0, 11.0) + 1e-9, "cannot exceed the best series"


def test_expected_max_closed_form_matches_simulation():
    rng = np.random.default_rng(7)
    pool = np.sort(rng.lognormal(0, 0.5, 40))
    for n in (2, 3, 6):
        sim = rng.choice(pool, size=(200000, n)).max(axis=1).mean()
        assert fv.expected_max(pool, n) == pytest.approx(sim, rel=0.01)


def test_missing_values_fail_closed_rather_than_scoring_as_zero():
    e = _toy_entry([[10.0], [20.0]], 1, [0, 0], {0: 0})
    w = UNIT_W.copy()
    w[fv.STAT_INDEX["watchers_taken"]] = 1.5      # a column that is entirely NaN here
    with pytest.raises(ValueError, match="does not fully observe"):
        fv.series_scores(e, w)


def test_unobservable_stats_are_dropped_from_weights_and_reported():
    slots = [{"slot": 1, "stat": "watchers_taken", "colour": "blue", "multiplier": 1.1},
             {"slot": 2, "stat": "wards_placed", "colour": "blue", "multiplier": 1.8}]
    w = fv.banner_weights(slots)
    assert w[fv.STAT_INDEX["watchers_taken"]] == 0.0
    assert w[fv.STAT_INDEX["wards_placed"]] == pytest.approx(1.8)
    u = fv.unscored_weight(slots)
    assert u["unscored_stats"] == ["watchers_taken"]
    assert u["unscored_fraction"] == pytest.approx(1.1 / 2.9, abs=1e-4)


def test_breakpoint_shift_is_exactly_twice_the_per_player_game_value():
    """A constant added to every player-game shifts the period score by exactly 2k."""
    e = _toy_entry([[10.0], [20.0], [30.0], [5.0]], 1, [0, 0, 1, 1], {0: 0, 1: 0})
    base = fv.period_score(e, UNIT_W, {3: 0.5, 5: 0.5})
    shifted = _toy_entry([[10.0 + 7], [20.0 + 7], [30.0 + 7], [5.0 + 7]], 1,
                         [0, 0, 1, 1], {0: 0, 1: 0})
    assert fv.period_score(shifted, UNIT_W, {3: 0.5, 5: 0.5}) == pytest.approx(base + 2 * 7)


# ---------------------------------------------------------------- shrinkage

def test_shrinkage_k_zero_reproduces_the_unshrunk_estimator():
    e = _toy_entry([[10.0], [20.0], [30.0], [5.0]], 1, [0, 0, 1, 1], {0: 0, 1: 0})
    S, sev = fv.series_scores(e, UNIT_W)
    pools = {"E": np.sort(S)}
    field = {"E": (np.array([0.0, 1000.0]), np.array([0.5, 0.5]))}
    exp = {3: 0.5, 6: 0.5}
    assert fv.period_score_shrunk(pools, field, exp, k=0.0) == \
        pytest.approx(fv.period_score(e, UNIT_W, exp))


def test_shrinkage_pulls_a_thin_pool_towards_the_field():
    pool = {"E": np.array([100.0, 110.0])}
    high = {"E": (np.array([500.0, 600.0]), np.array([0.5, 0.5]))}
    low = {"E": (np.array([1.0, 2.0]), np.array([0.5, 0.5]))}
    exp = {4: 1.0}
    un = fv.period_score_shrunk(pool, {}, exp, k=5.0)
    assert fv.period_score_shrunk(pool, high, exp, k=5.0) > un
    assert fv.period_score_shrunk(pool, low, exp, k=5.0) < un


def test_shrinkage_weight_grows_with_the_team_s_own_sample():
    field = {"E": (np.array([0.0, 0.0]), np.array([0.5, 0.5]))}
    exp = {4: 1.0}
    thin = {"E": np.array([100.0, 100.0])}
    thick = {"E": np.full(50, 100.0)}
    # both pools are identical in value, so the only difference is how far each is dragged down
    assert fv.period_score_shrunk(thick, field, exp, k=5.0) > \
        fv.period_score_shrunk(thin, field, exp, k=5.0)


def test_field_prior_weights_teams_equally_not_series():
    """A team playing twice as many series must not count twice in the prior."""
    built = {"cache": {}}
    for name, n_series in (("A", 2), ("B", 8)):
        scores = [[float(100 if name == "A" else 200)]] * (2 * n_series)
        series = [i // 2 for i in range(2 * n_series)]
        e = _toy_entry(scores, 1, series, {s: 0 for s in set(series)})
        e["events"] = ["EV"]
        built["cache"][(name, "mid")] = e
    _, field = fv.role_pools(built, "mid", UNIT_W, ["A", "B"])
    vals, wts = field["EV"]
    wts = wts / wts.sum()
    mass_a = float(wts[vals == 200.0].sum())     # each series score is 100 + 100 or 200 + 200
    mass_b = float(wts[vals == 400.0].sum())
    assert mass_a == pytest.approx(0.5) and mass_b == pytest.approx(0.5)


# ---------------------------------------------------------------- value function

@pytest.fixture(scope="module")
def live():
    built = fv.build_cache()
    exp = mex.exposure_distribution()
    return built, exp


def test_stat_value_scales_with_the_multiplier(live):
    built, exp = live
    e = built["cache"][("Team Falcons", "mid")]
    w = np.zeros(len(fv.STATS))
    w[fv.STAT_INDEX["gpm"]] = 1.0
    a = fv.period_score(e, w, exp["Team Falcons"]["dist"])
    w[fv.STAT_INDEX["gpm"]] = 2.0
    b = fv.period_score(e, w, exp["Team Falcons"]["dist"])
    assert b == pytest.approx(2.0 * a), "a single-stat banner is exactly linear in its multiplier"


def test_quality_change_recomputes_the_whole_trait_network():
    """Raising one slot's tier can switch Fractal off for a different slot."""
    spec = [{"quality_tier": t, "trait": "Fractal"} for t in ("I", "II", "III", "IV", "V")]
    before = bm.evaluate(spec)
    assert all(e["net_trait_bonus"] == pytest.approx(0.60) for e in before)
    spec[0]["quality_tier"] = "V"                       # now two slots share Tier V
    after = bm.evaluate(spec)
    assert all(e["net_trait_bonus"] == pytest.approx(0.0) for e in after), \
        "every Fractal on the banner must stop paying, not just the slot that changed"


def test_trait_change_recomputes_both_neighbours():
    spec = [{"quality_tier": t, "trait": "Base"} for t in ("I", "II", "III", "IV", "V")]
    spec[2]["trait"] = "Vampiric"
    ev = bm.evaluate(spec)
    assert ev[1]["net_trait_bonus"] == pytest.approx(-0.10)
    assert ev[3]["net_trait_bonus"] == pytest.approx(-0.10)
    assert ev[0]["net_trait_bonus"] == pytest.approx(0.0)


def test_team_change_leaves_the_banner_untouched(live):
    built, exp = live
    doc, _ = bme.load_state("operator")
    slots = bme.slots_of(doc, "mid")
    w1 = fv.banner_weights(slots)
    for team in ("Team Falcons", "PARIVISION", "Nigma Galaxy"):
        fv.period_score(built["cache"][(team, "mid")], w1, exp[team]["dist"])
    assert np.array_equal(fv.banner_weights(bme.slots_of(doc, "mid")), w1)


def test_fast_path_agrees_with_a_naive_reference(live):
    """The vectorised chain against an obvious, slow, per-row implementation."""
    built, exp = live
    team, role = "Team Liquid", "support"
    e = built["cache"][(team, role)]
    doc, _ = bme.load_state("target")
    w = fv.banner_weights(bme.slots_of(doc, role))
    fast, sev = fv.series_scores(e, w)

    per_row = np.nansum(e["X"] * w[None, :], axis=1)
    games = {}
    for i, g in enumerate(e["game"]):
        games.setdefault(int(g), []).append(per_row[i])
    role_game = {g: sum(v) / len(v) for g, v in games.items()}
    naive = {}
    for g, r in role_game.items():
        naive.setdefault(int(e["game_series"][g]), []).append(r)
    for s, vals in naive.items():
        assert fast[s] == pytest.approx(sum(sorted(vals, reverse=True)[:2]), rel=1e-9)


def test_exposure_is_the_double_elimination_range_not_the_swiss():
    d = mex.exposure_distribution()
    assert set(d) == {"Tundra Esports", "Team Spirit", "PARIVISION", "BetBoom Team",
                      "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"}
    for team, v in d.items():
        assert v["min_series"] == 2 and v["max_series"] == 6, team
        assert 2.0 < v["expected_series"] < 6.0


def test_exposure_reconstruction_agrees_with_the_committed_bracket():
    g = mex.consistency_gate()
    assert g["within_tolerance"], g["max_abs_deviation"]


# ---------------------------------------------------------------- reroll offers

@pytest.fixture(scope="module")
def offer_ctx(live):
    built, exp = live
    doc, _ = bme.load_state("target")
    return built, exp, doc


def test_a_stat_reroll_never_offers_the_current_stat_or_a_duplicate(offer_ctx):
    built, exp, doc = offer_ctx
    slots = bme.slots_of(doc, "core")
    offer = {"id": "T", "kind": "stat", "colour": "green", "which": "last"}
    got = bme.offer_outcomes(built, "core", slots, "PARIVISION", exp["PARIVISION"]["dist"],
                             None, None, offer, teams=sorted(exp))
    names = {o["outcome"].split("-> ")[1] for o in got["readings"]["resolved"]["outcomes"]}
    greens = [s for s in slots if s["colour"] == "green"]
    target = greens[-1]
    assert target["stat"] not in names, "a reroll is guaranteed to produce a DIFFERENT stat"
    for s in slots:
        if s is not target:
            assert s["stat"] not in names, "a banner never carries the same stat twice"


def test_offer_readings_report_combinatorial_fractions_not_probabilities(offer_ctx):
    built, exp, doc = offer_ctx
    slots = bme.slots_of(doc, "core")
    offer = {"id": "T", "kind": "quality", "colour": "red", "which": "random_one"}
    got = bme.offer_outcomes(built, "core", slots, "PARIVISION", exp["PARIVISION"]["dist"],
                             None, None, offer, teams=sorted(exp))
    for rd in got["readings"].values():
        assert rd["fraction_improving_is_a_combinatorial_fraction_not_a_probability"] is True
        assert rd["n_outcomes"] == len(rd["outcomes"])
        assert rd["min_delta"] <= rd["median_delta"] <= rd["max_delta"]


def test_ambiguous_target_semantics_produce_more_than_one_reading(offer_ctx):
    built, exp, doc = offer_ctx
    slots = bme.slots_of(doc, "core")
    offer = {"id": "T", "kind": "trait", "colour": "red", "which": "all_of_colour_reading",
             "semantics_status": "TARGET_SELECTION_SEMANTICS_UNKNOWN"}
    got = bme.offer_outcomes(built, "core", slots, "PARIVISION", exp["PARIVISION"]["dist"],
                             None, None, offer, teams=sorted(exp))
    assert set(got["readings"]) == {"all_of_colour", "single_unknown_slot"}, \
        "an unresolved target must be evaluated under every reading, never guessed"
    assert got["readings"]["all_of_colour"]["n_outcomes"] == 6 ** 3, \
        "three red slots, six other traits each"


def test_a_zero_gain_offer_is_reported_as_dominated(offer_ctx):
    """A stat reroll on a slot whose current stat is already the best cannot show a positive max."""
    built, exp, doc = offer_ctx
    slots = [dict(s) for s in bme.slots_of(doc, "mid")]
    offer = {"id": "T", "kind": "stat", "colour": "green", "which": "first"}
    got = bme.offer_outcomes(built, "mid", slots, "Team Falcons", exp["Team Falcons"]["dist"],
                             None, None, offer, teams=sorted(exp))
    rd = got["readings"]["resolved"]
    if rd["max_delta"] <= 0:
        assert rd["fraction_improving"] == 0.0


# ---------------------------------------------------------------- leakage and isolation

def test_no_main_event_match_is_in_the_fantasy_data():
    import csv
    p = os.path.join(fv.FPROC, "ti15_player_map_stats.csv")
    if not os.path.exists(p):
        pytest.skip("TI15 table not fetched in this environment")
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            assert int(r["start_time"]) < 1787184000, \
                f"match {r['match_id']} starts at or after the Main Event"


@pytest.mark.parametrize("path", [
    "data/ti2026/processed/universe_maps.csv",
    "predictions/ti2026/playoffs/ti15_main_event_prediction.json",
    "predictions/ti2026/playoffs/ti15_main_event_prediction.md",
    "predictions/ti2026/group-stage/ti15_group_prediction.json",
])
def test_audited_bracket_inputs_and_artifacts_are_untouched(path):
    r = subprocess.run(["git", "diff", "--quiet", BRANCH_POINT, "--", path],
                       cwd=REPO, capture_output=True)
    assert r.returncode == 0, f"{path} differs from the audited branch point {BRANCH_POINT[:7]}"


def test_generated_artifacts_carry_a_cutoff_and_disclaim_main_event_results():
    p = os.path.join(MAIN_EVENT, "team_rankings.json")
    if not os.path.exists(p):
        pytest.skip("artifacts not generated in this environment")
    with open(p, encoding="utf-8") as fh:
        m = json.load(fh)["manifest"]
    assert m["main_event_results_used"] is False
    assert m["information_cutoff"] == bme.INFO_CUTOFF
    assert m["code_commit"]
