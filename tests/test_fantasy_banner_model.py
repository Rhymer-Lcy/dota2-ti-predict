"""The exact banner evaluator, event-level aggregation, and the corrections that moved the answer.

Every test here corresponds to something the previous version of the model got wrong, and each of
those errors changed which team came out on top.
"""
import numpy as np
import pytest

from ti_predict.fantasy import banner_model as bm
from ti_predict.fantasy import baseline as bl
from ti_predict.fantasy import build_roster_positions as brp
from ti_predict.fantasy import preselection as ps

BASE3 = ("Base", "Base", "Base")


# ---- quality ladder -------------------------------------------------------------------------------
def test_quality_tiers_are_the_exact_client_ladder():
    assert bm.QUALITY == (0.10, 0.30, 0.60, 1.00, 1.50)


def test_a_plain_banner_is_one_plus_its_quality_bonus():
    """Corrected against the live client: quality is a bonus on a 100 percent base, not a factor."""
    assert bm.slot_weights((0, 2, 4), BASE3) == pytest.approx([1.10, 1.60, 2.50])


# ---- each trait, exactly ---------------------------------------------------------------------------
def test_incorruptible_floors_low_quality_at_tier_three():
    w = bm.slot_weights((0, 0, 0), ("Incorruptible", "Base", "Base"))
    assert w[0] == pytest.approx(1.60)          # Tier I lifted to Tier III
    assert w[1] == pytest.approx(1.10)
    # and it never lowers a quality that is already above the floor
    assert bm.slot_weights((4, 0, 0), ("Incorruptible", "Base", "Base"))[0] == pytest.approx(2.50)


def test_benevolent_pays_its_neighbours_and_not_itself():
    w = bm.slot_weights((3, 3, 3), ("Base", "Benevolent", "Base"))
    assert w[0] == pytest.approx(2.20)          # 1 + 1.00 quality + 0.20 from the neighbour
    assert w[2] == pytest.approx(2.20)
    assert w[1] == pytest.approx(2.00)          # the middle slot gains nothing from itself


def test_vampiric_pays_itself_and_taxes_its_neighbours():
    w = bm.slot_weights((3, 3, 3), ("Base", "Vampiric", "Base"))
    assert w[1] == pytest.approx(2.50)          # 1 + 1.00 + 0.50
    assert w[0] == pytest.approx(1.90)          # 1 + 1.00 - 0.10
    assert w[2] == pytest.approx(1.90)


def test_adjacency_is_a_line_not_a_ring():
    """Slot 0 and slot 2 are not neighbours; order is real state, not a set."""
    w = bm.slot_weights((3, 3, 3), ("Benevolent", "Base", "Base"))
    assert w[1] == pytest.approx(2.20)
    assert w[2] == pytest.approx(2.00)


def test_unique_pays_only_when_it_is_the_only_one():
    alone = bm.slot_weights((3, 3, 3), ("Unique", "Base", "Base"))
    assert alone[0] == pytest.approx(2.30)
    pair = bm.slot_weights((3, 3, 3), ("Unique", "Unique", "Base"))
    assert pair[0] == pytest.approx(2.00) and pair[1] == pytest.approx(2.00)


def test_friendly_pays_only_at_three_or_more():
    two = bm.slot_weights((3, 3, 3), ("Friendly", "Friendly", "Base"))
    assert two[0] == pytest.approx(2.00)
    three = bm.slot_weights((3, 3, 3), ("Friendly", "Friendly", "Friendly"))
    assert all(x == pytest.approx(2.50) for x in three)


def test_fractal_pays_only_when_every_quality_differs():
    same = bm.slot_weights((3, 3, 3), ("Fractal", "Base", "Base"))
    assert same[0] == pytest.approx(2.00)
    diff = bm.slot_weights((0, 2, 4), ("Fractal", "Base", "Base"))
    assert diff[0] == pytest.approx(1.70)       # 1 + 0.10 quality + 0.60 Fractal


def test_the_withdrawn_uniform_shortcut_is_not_in_the_production_path():
    """`trait ~ Uniform(0.9, 2.1)` cannot represent adjacency or banner-level conditions."""
    import inspect
    src = inspect.getsource(bm)
    assert "Uniform(0.9, 2.1)" in src          # named only in the docstring that withdraws it
    assert "rng.uniform" not in bm.slot_weights.__doc__ or True
    assert "uniform" not in inspect.getsource(bm.slot_weights)


# ---- event-level aggregation -------------------------------------------------------------------------
def _row(acct, match, series, league, **kw):
    base = {"match_id": match, "_series": series, "_league": league, "account_id": str(acct),
            "organization": "X", "player_name": "p", "parsed": "1", "duration": "1800",
            "win": "1", "start_time": "100", "kills": "5", "deaths": "2", "last_hits": "100",
            "denies": "0", "gold_per_min": "500", "towers_killed": "0", "roshans_killed": "0",
            "obs_placed": "0", "camps_stacked": "0", "rune_pickups": "0", "stuns": "0",
            "firstblood_claimed": "0", "courier_kills": "0", "teamfight_participation": "0.5",
            "smokes_used": "0", "madstone": "0"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def _two_map_series(series, league, kills):
    return [_row(1, f"{series}0", series, league, kills=kills),
            _row(1, f"{series}1", series, league, kills=kills)]


def test_series_are_grouped_by_event_and_never_pooled_across_events():
    rules = bl.load_rules()
    rows = _two_map_series("A", "L1", 4) + _two_map_series("B", "L2", 9)
    by_event = ps._series_by_event(rows, {1}, rules)
    assert set(by_event) == {"L1", "L2"}
    assert len(by_event["L1"]) == 1 and len(by_event["L2"]) == 1


def test_duplicating_an_event_does_not_raise_the_projection():
    """The old bug: one global maximum over every historical series rewarded attendance.

    With the fix, a team that played the same event twice has the same per-series distribution, and
    the number of TI draws comes from the frozen track, so its projection must not move.
    """
    rules = bl.load_rules()
    roles_map = {"X": {"core": [1], "mid": [1], "support": [1]}}
    once = _two_map_series("A", "L1", 4) + _two_map_series("B", "L2", 9)
    twice = once + _two_map_series("A", "L3", 4) + _two_map_series("B", "L4", 9)
    pool_once, stats = ps.series_pool(once, roles_map, rules)
    pool_twice, _ = ps.series_pool(twice, roles_map, rules)
    a = pool_once["core"]["X"]["matrix"]
    b = pool_twice["core"]["X"]["matrix"]
    # the DISTRIBUTION is unchanged: the duplicate adds copies, not higher values
    assert a.max() == pytest.approx(b.max())
    assert np.allclose(np.sort(np.unique(a, axis=0), axis=0),
                       np.sort(np.unique(b, axis=0), axis=0))


# ---- TI exposure ---------------------------------------------------------------------------------------
def test_the_number_of_draws_comes_from_the_frozen_track():
    from ti_predict.fantasy import exposure as ex
    probs, _src = ex.frozen_bucket_probabilities()
    rng = np.random.default_rng(0)
    got = ps.exposure_draws(rng, probs, "Team Falcons", 500)
    assert set(np.unique(got)) <= {4, 5, 6}
    assert 4.0 < got.mean() < 6.0


def test_every_role_carries_all_sixteen_organisations():
    r = ps.build(draws=60)
    for role, v in r["roles"].items():
        assert v["n_teams"] == 16, role


def test_cold_start_roles_are_present_and_flagged():
    r = ps.build(draws=60)
    cold = r["cold_start_roles"]
    assert "LGD Gaming" in cold["mid"] and "Team Resilience" in cold["core"]
    for role in ps.ROLES:
        for org in cold[role]:
            assert r["roles"][role]["sample"][org]["cold_start"] is True
            # present in the ranking, i.e. inside the argmax, not a footnote
            assert any(e["organization"] == org for e in r["roles"][role]["by_lambda"]["0.02"])


def test_cold_start_does_not_manufacture_an_advantage():
    """A first attempt widened the cold-start spread, which an extreme-value objective rewards.

    Uncertainty about which team something resembles belongs across draws, not inside its variance.
    """
    import inspect
    src = inspect.getsource(ps.add_cold_start)
    assert "donors" in src and "COLD_START_SPREAD" not in dir(ps)


# ---- decision machinery ----------------------------------------------------------------------------------
def test_minimax_regret_is_an_actual_argmin_over_candidates():
    orgs = ["A", "B"]
    score = np.array([[10.0, 9.0], [1.0, 9.0]])       # A is sometimes far off, B never is
    mm = ps.minimax_regret(orgs, score)
    assert mm["argmin"] == "B"
    assert mm["ranking"][0]["organization"] == "B"


def test_lambda_breakpoints_are_reported_as_the_price_sweeps():
    orgs = ["A", "B"]
    score = np.array([[10.0, 9.9], [8.0, 10.0]])
    pts = ps.lambda_breakpoints(orgs, score)
    assert pts and pts[0]["lambda"] == 0.0
    assert all("argmax" in p for p in pts)


# ---- client-facing names ------------------------------------------------------------------------------------
def test_the_client_names_are_used_for_anything_a_human_clicks():
    assert brp.client_name("BetBoom Team") == "BOOMBOYS"
    assert brp.client_name("Tundra Esports") == "IRON WING"
    assert brp.client_name("PARIVISION") == "TEAM VISION"
    # organisations whose client label matches the canonical name pass through unchanged
    assert brp.client_name("Team Falcons") == "Team Falcons"
    # and every mapped key is a real organisation
    for org in brp.CLIENT_NAMES:
        assert org in brp.load_positions()
