"""TI15 result data: alias resolution, standings reconstruction, and the map-expansion contract."""
from collections import Counter

import pytest

from ti_predict import ti15_results as tr


def test_the_reconciliation_gate_passes():
    rep = tr.verify_standings()
    assert rep["swiss_series"] == 39 and rep["elimination_series"] == 5
    assert rep["total_series"] == 44
    assert rep["standings_reproduced"] and rep["unique_surviving_orgs"] == 8


def test_standings_are_reconstructed_not_copied():
    """Every published cell must fall out of the 39 series alone."""
    got = tr.standings()
    for _, team, sw, sl, mw, ml in tr.PUBLISHED_STANDINGS:
        g = got[team]
        assert (g["sw"], g["sl"], g["mw"], g["ml"]) == (sw, sl, mw, ml), team


def test_a_corrupted_series_is_caught_by_the_gate():
    """The gate is only worth having if a wrong result actually trips it."""
    bad = list(tr.SWISS)
    bad[0] = (1, "LGD Gaming", "Team Falcons", 2, 1)      # flip round 1 match 1
    orig, tr.SWISS = tr.SWISS, bad
    try:
        with pytest.raises(SystemExit):
            tr.verify_standings()
    finally:
        tr.SWISS = orig
    tr.verify_standings()                                  # and the real data still passes


def test_every_series_totals_16_teams_per_round():
    for rnd, n in {1: 8, 2: 8, 3: 8, 4: 8, 5: 7}.items():
        teams = [t for r, w, l, *_ in tr.SWISS if r == rnd for t in (w, l)]
        assert len(teams) == 2 * n and len(set(teams)) == 2 * n, rnd


def test_the_four_zero_and_zero_four_teams_play_only_four_series():
    got = tr.standings()
    assert got["TEAM VISION"]["sw"] + got["TEAM VISION"]["sl"] == 4
    assert got["HULIGANI"]["sw"] + got["HULIGANI"]["sl"] == 4
    for _, team, sw, sl, *_ in tr.PUBLISHED_STANDINGS:
        if team not in ("TEAM VISION", "HULIGANI"):
            assert sw + sl == 5, team


def test_alias_table_collapses_the_three_renamed_orgs():
    assert tr.canon("TEAM VISION") == "PARIVISION"
    assert tr.canon("BoomBoys") == "BetBoom Team"
    assert tr.canon("Iron Wing") == tr.canon("1w Team") == "Tundra Esports"


def test_an_unknown_identity_raises_instead_of_guessing():
    with pytest.raises(KeyError):
        tr.canon("Team Vsion")


def test_alias_mapping_is_injective_over_the_ti15_field():
    field = {t for _, t, *_ in tr.PUBLISHED_STANDINGS}
    assert len({tr.canon(t) for t in field}) == 16


def test_map_expansion_matches_the_reported_scores():
    rows, prov = tr.build_rows()
    assert prov["series_expanded"] == 44
    by_series = {}
    for r in rows:
        by_series.setdefault(r["series_id"], []).append(r)
    assert len(by_series) == 44
    for i, (_, w, l, wm, lm) in enumerate(tr.SWISS + tr.ELIMINATION):
        maps = by_series[tr.SERIES_ID_BASE + i]
        assert len(maps) == wm + lm
        assert sum(m["a_won"] for m in maps) == wm
        assert all(m["team_a"] == tr.canon(w) and m["team_b"] == tr.canon(l) for m in maps)


def test_each_series_carries_total_weight_one():
    """A 2-0 and a 2-1 must weigh the same; a series is never counted twice."""
    rows, _ = tr.augmented_universe()
    ti = [r for r in rows if r.get("ti15_stage")]
    per = Counter()
    for r in ti:
        per[r["series_id"]] += r["w"]
    assert len(per) == 44
    for sid, w in per.items():
        assert w == pytest.approx(1.0), sid


def test_round_one_timestamps_come_from_the_official_feed():
    times = tr.feed_round1_times()
    assert len(times) == 8, "the saved league feed should carry all eight round-1 nodes"
    r1 = {frozenset((tr.canon(w), tr.canon(l))) for r, w, l, *_ in tr.SWISS if r == 1}
    assert r1 == set(times), "the feed's round-1 pairings must reconcile with the reported results"


def test_ti15_series_ids_cannot_collide_with_the_universe():
    rows, _ = tr.augmented_universe()
    base = {r["series_id"] for r in rows if not r.get("ti15_stage")}
    ti = {r["series_id"] for r in rows if r.get("ti15_stage")}
    assert not (base & ti)


def test_stage_selection_excludes_the_elimination_round_when_asked():
    rows, _ = tr.augmented_universe(use_stages=("swiss",))
    ti = [r for r in rows if r.get("ti15_stage")]
    assert {r["ti15_stage"] for r in ti} == {"swiss"}
    assert len({r["series_id"] for r in ti}) == 39


def test_collapsing_timestamps_changes_only_the_timestamps():
    a, _ = tr.build_rows()
    b, _ = tr.build_rows(collapse_to="2026-08-16T00:00:00Z")
    assert [(r["team_a"], r["team_b"], r["a_won"]) for r in a] == \
           [(r["team_a"], r["team_b"], r["a_won"]) for r in b]
    assert len({r["start_time"] // 1000 for r in b}) == 1


def test_the_fixed_bracket_seats_exactly_the_survivors():
    seated = [t for pair in tr.UBQF.values() for t in pair]
    assert sorted(seated) == sorted(tr.FINAL_EIGHT)
    assert len({tr.canon(t) for t in seated}) == 8
    eliminated = {t for _, t, *_ in tr.PUBLISHED_STANDINGS} - set(tr.FINAL_EIGHT)
    assert len(eliminated) == 8
    assert not (eliminated & set(seated))
