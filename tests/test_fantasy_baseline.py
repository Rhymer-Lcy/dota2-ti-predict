"""The scoring function and the four-level aggregation, checked on inputs small enough to verify.

The baseline's whole value is that it applies the real ruleset rather than an average of averages,
so the tests here are about the ruleset's awkward parts: the two stats that are not linear counts,
the two aggregation levels that are selections rather than sums, and the unresolved semantics that
must stay switchable instead of being quietly decided.
"""
import copy
import json

import pytest

from ti_predict.fantasy import baseline as bl
from ti_predict.fantasy import questions as fq

RULES = fq.load_rules()
COEF = {s["stat_id"]: s for s in RULES["stats"]["list"]}
R = {"coef": COEF, "layout": RULES["emblems"]["slot_layout"]["period_0_color_composition"],
     "pools": RULES["stats"]["by_color"], "deaths_credit": COEF["deaths"]["starting_points"]}


def _row(**kw):
    base = {"match_id": "1", "account_id": "1", "organization": "X", "player_name": "p",
            "parsed": "1", "_league": "L", "_series": "s1"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


# ---- the scoring function ----------------------------------------------------------------------
def test_a_linear_count_stat_is_count_times_coefficient():
    assert bl.map_score(_row(kills=7), "kills", R, False) == pytest.approx(7 * 107.0)


def test_creep_score_sums_last_hits_and_denies():
    """The client scores 'per last hit or deny', which is one stat over two columns."""
    assert bl.map_score(_row(last_hits=300, denies=20), "creep_score", R, False) \
        == pytest.approx(320 * 3.0)


def test_deaths_is_a_credit_minus_a_debit_and_the_floor_is_a_switch():
    assert bl.map_score(_row(deaths=0), "deaths", R, False) == pytest.approx(1950.0)
    assert bl.map_score(_row(deaths=10), "deaths", R, False) == pytest.approx(0.0)
    # the eleventh death is the whole question: free, or -195 against the rest of the banner
    assert bl.map_score(_row(deaths=11), "deaths", R, False) == pytest.approx(-195.0)
    assert bl.map_score(_row(deaths=11), "deaths", R, True) == pytest.approx(0.0)


def test_teamfight_participation_is_capped_not_linear():
    tfp = COEF["teamfight_participation"]["maximum_points"]
    assert bl.map_score(_row(teamfight_participation=0.5), "teamfight_participation", R, False) \
        == pytest.approx(0.5 * tfp)
    assert bl.map_score(_row(teamfight_participation=1.4), "teamfight_participation", R, False) \
        == pytest.approx(tfp)


def test_a_missing_column_scores_nothing_rather_than_zero():
    """An unparsed match has nulls, and a null is not a zero. It must not average into existence."""
    assert bl.map_score(_row(kills=""), "kills", R, False) is None
    assert bl.map_score(_row(kills=3), "watchers_taken", R, False) is None


def test_the_two_unobtainable_stats_are_excluded_by_construction():
    for s in ("watchers_taken", "lotuses_grabbed"):
        assert s not in bl.STAT_COLUMNS and s in bl.UNAVAILABLE


# ---- the four levels ---------------------------------------------------------------------------
def _series_rows(b_kills=10):
    """Two players, two series. Series A: maps of 1/2/3 kills each. Series B: one map of b_kills."""
    rows = []
    for series, maps in (("A", [(1, 1), (2, 2), (3, 3)]), ("B", [(b_kills, b_kills)])):
        for i, (k1, k2) in enumerate(maps):
            for acct, k in ((1, k1), (2, k2)):
                rows.append(_row(match_id=f"{series}{i}", _series=series, account_id=acct, kills=k))
    return rows


def test_a_series_keeps_its_top_two_maps_and_a_period_keeps_its_best_series():
    rows = _series_rows()
    got = bl.role_period_scores(rows, {1, 2}, "kills", R, "sum", False)
    # series A top two maps are 3 and 2 kills -> (3+2)*107; series B is a single 10-kill map -> 10*107
    assert got["L"] == pytest.approx(10 * 107.0)          # B wins the period, and it is a max


def test_the_unresolved_hypothesis_can_change_which_series_wins_the_period():
    """Not a level shift: with a long series and a short one, sum and mean pick different series."""
    rows = _series_rows(b_kills=4)
    s = bl.role_period_scores(rows, {1, 2}, "kills", R, "sum", False)["L"]
    m = bl.role_period_scores(rows, {1, 2}, "kills", R, "mean", False)["L"]
    assert s == pytest.approx((3 + 2) * 107.0)     # sum keeps the three-map series A
    assert m == pytest.approx(4 * 107.0)           # mean keeps the single strong map of series B
    assert s != m


def test_a_role_score_for_a_map_is_the_mean_over_that_roles_players():
    rows = [_row(match_id="m1", _series="s", account_id=1, kills=4),
            _row(match_id="m1", _series="s", account_id=2, kills=8)]
    got = bl.role_period_scores(rows, {1, 2}, "kills", R, "sum", False)
    assert got["L"] == pytest.approx(6 * 107.0)


def test_the_best_series_is_a_maximum_not_an_average_over_series():
    rows = [_row(match_id="a", _series="A", account_id=1, kills=1),
            _row(match_id="b", _series="B", account_id=1, kills=9)]
    got = bl.role_period_scores(rows, {1}, "kills", R, "sum", False)
    assert got["L"] == pytest.approx(9 * 107.0)


# ---- the ruleset the baseline reads --------------------------------------------------------------
def test_the_period_zero_layout_is_three_emblems_in_real_colours():
    layout = RULES["emblems"]["slot_layout"]["period_0_color_composition"]
    assert set(layout) == {"core", "mid", "support"}
    for role, colours in layout.items():
        assert len(colours) == 3
        assert set(colours) <= {"red", "blue", "green"}     # there is no yellow emblem
    assert set(layout["mid"]) == {"red", "blue", "green"}   # mid is the only three-colour banner


def test_the_slot_count_is_known_to_grow_with_tablet_level():
    g = RULES["emblems"]["slot_layout"]["grows_with_tablet_level"]
    assert g["status"] == "CONFIRMED" and g["period_1_slot_count"] is None


def test_a_banner_never_carries_the_same_stat_twice():
    """Core is red/green/red, so the two red slots need the best two DISTINCT red stats."""
    rows = []
    for i, (lh, k, tw) in enumerate([(300, 5, 2), (280, 6, 1), (310, 4, 3)]):
        rows.append(_row(match_id=f"m{i}", _series=f"s{i}", account_id=1,
                         last_hits=lh, denies=0, kills=k, towers_killed=tw, deaths=2,
                         gold_per_min=600, madstone=0, roshans_killed=1,
                         teamfight_participation=0.7, stuns=10, firstblood_claimed=0,
                         courier_kills=0))
    env = bl.envelope(rows, {"Org": {"core": [1]}}, R, "sum", False)
    slots = env[0]["slots"]
    assert len(slots) == 3
    assert len({s["stat"] for s in slots}) == 3
    assert sorted(s["colour"] for s in slots) == ["green", "red", "red"]


def test_the_valve_stat_enum_ordering_matches_every_helpstat_index():
    """Tier-1 cross-check: Valve's enum order is the localization's helpstat order."""
    alias = {"CS": "creep_score", "WARDS_PLANTED": "wards_placed",
             "LOTUSES_GAINED": "lotuses_grabbed", "MADSTONE": "madstone"}
    enum = RULES["engine_interface"]["stat_enum"]["values_0_to_17"]
    assert len(enum) == 18
    by_index = {s["helpstat_index"]: s["stat_id"] for s in RULES["stats"]["list"]}
    for i, name in enumerate(enum):
        assert by_index[i] == alias.get(name, name.lower())


def test_the_trait_taxonomy_is_closed_by_the_engine_enum():
    beh = RULES["emblems"]["traits"]["engine_behaviour_enum"]["mapping"]
    named = {t["name"] for t in RULES["emblems"]["traits"]["list"]}
    assert set(beh.values()) | {"Base"} == named


def test_every_operation_costs_exactly_one_token():
    c = RULES["roll_tokens"]["cost_per_operation"]
    assert c["status"] == "CONFIRMED" and c["value"] == 1


def test_the_round_records_what_it_closed_and_why_the_rest_is_unreachable():
    assert RULES["closed_this_round"]["entries"]
    assert "no fantasy crafting data resource" in RULES["why_the_rest_cannot_be_closed_publicly"]


# ---- the generic / account-specific line ---------------------------------------------------------
def test_the_evidence_register_keeps_both_sides_of_the_line():
    ev = fq.load_generic_evidence()
    ids = {s["id"] for s in ev["sources"]}
    assert {"G1", "G2", "G3", "G4"} <= ids
    assert ev["generic_vs_account_specific"]["account_specific_examples"]


def test_historical_valve_material_cannot_pose_as_current(tmp_path):
    ev = fq.load_generic_evidence()
    assert ev["historical_valve_official"]["grade"] == "OFFICIAL-HISTORICAL"
    bad = copy.deepcopy(ev)
    bad["historical_valve_official"]["grade"] = "CONFIRMED"
    p = tmp_path / "generic_evidence.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="OFFICIAL-HISTORICAL"):
        fq.load_generic_evidence(str(p))


def test_an_untiered_source_is_refused(tmp_path):
    bad = copy.deepcopy(fq.load_generic_evidence())
    bad["sources"][0].pop("tier")
    p = tmp_path / "generic_evidence.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="missing tier"):
        fq.load_generic_evidence(str(p))


# ---- the fetcher -----------------------------------------------------------------------------
def test_an_unparsed_match_yields_nulls_not_zeros():
    """The distinction the whole baseline rests on: OpenDota returns null, and null is not zero."""
    from ti_predict.fantasy import fetch_player_stats as fp
    match = {"match_id": 1, "leagueid": 2, "start_time": 3, "duration": 2000, "radiant_win": True,
             "players": [{"account_id": 9, "player_slot": 0, "kills": 5}]}
    row = fp._rows_for(match, {9: ("p", "Org")})[0]
    assert row["parsed"] == 0
    assert row["smokes_used"] is None and row["madstone"] is None
    match["version"] = 22
    row = fp._rows_for(match, {9: ("p", "Org")})[0]
    assert row["parsed"] == 1
    # on a parse, an absent item-use key really does mean the item was never used
    assert row["smokes_used"] == 0 and row["madstone"] == 0


def test_only_ti_players_are_kept_and_the_win_flag_follows_the_slot():
    from ti_predict.fantasy import fetch_player_stats as fp
    match = {"match_id": 1, "leagueid": 2, "start_time": 3, "version": 22, "radiant_win": True,
             "players": [{"account_id": 9, "player_slot": 0}, {"account_id": 8, "player_slot": 128},
                         {"account_id": 7, "player_slot": 1}]}
    rows = fp._rows_for(match, {9: ("a", "A"), 8: ("b", "B")})
    assert {r["account_id"] for r in rows} == {9, 8}
    assert {r["account_id"]: r["win"] for r in rows} == {9: 1, 8: 0}


def test_coverage_is_measured_from_the_table_not_from_a_stale_provenance_file(tmp_path):
    """A provenance file is written when a run ends, so mid-pull it describes an earlier run."""
    empty = tmp_path / "player_map_stats.csv"
    empty.write_text("match_id\n", encoding="utf-8")
    c = bl.coverage(str(empty))
    assert c["matches_covered"] == 0 and c["complete"] is False
    assert c["matches_targeted"] > 0


def test_the_fetcher_covers_every_stat_the_baseline_can_score():
    from ti_predict.fantasy import fetch_player_stats as fp
    needed = {c for cols in bl.STAT_COLUMNS.values() for c in cols}
    assert needed <= set(fp.FIELDS)


def test_the_stale_calculator_roster_is_recorded_as_a_hazard():
    """The public calculator still lists the replaced LGD mid; that must never reach a candidate."""
    ev = fq.load_generic_evidence()
    calc = next(s for s in ev["sources"] if s["id"] == "G4")
    assert "TaiLung" in calc["stale_roster_warning"]
    assert calc["use"].startswith("external benchmark only")
