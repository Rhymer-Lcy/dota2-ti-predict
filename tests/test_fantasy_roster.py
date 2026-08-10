"""Roster positions, pair completeness, and readiness with a single source.

Three corrections are locked down here, each of which changed the ranking:
  - fantasy roles come from the roster of record, never from play statistics;
  - a two-player role scores only on maps where BOTH current players appear;
  - readiness is derived from one structured register, so a rule cannot be simultaneously graded
    non-blocking and listed as a blocker.
"""
import copy
import json

import pytest

from ti_predict.fantasy import baseline as bl
from ti_predict.fantasy import build_roster_positions as brp
from ti_predict.fantasy import questions as fq

TAILUNG = 1026694469
TOPSON = 94054712


# ---- the position table -------------------------------------------------------------------------
def test_every_team_has_positions_one_to_five_exactly_once():
    roles = brp.load_positions()
    assert len(roles) == 16
    for org, r in roles.items():
        accts = r["core"] + r["mid"] + r["support"]
        assert len(accts) == 5 and len(set(accts)) == 5, org


def test_the_fantasy_roles_are_the_official_position_split():
    """Core is 1 and 3, Mid is 2, Support is 4 and 5 -- not a guess from last hits."""
    assert brp.FANTASY_ROLE == {1: "core", 2: "mid", 3: "core", 4: "support", 5: "support"}
    roles = brp.load_positions()
    for org, r in roles.items():
        assert len(r["core"]) == 2 and len(r["mid"]) == 1 and len(r["support"]) == 2, org


def test_account_ids_are_unique_across_the_whole_field():
    roles = brp.load_positions()
    accts = [a for r in roles.values() for v in r.values() for a in v]
    assert len(accts) == 80 and len(set(accts)) == 80


def test_the_replaced_player_is_inactive_and_the_replacement_holds_his_position():
    lgd = brp.load_positions()["LGD Gaming"]
    assert lgd["mid"] == [TOPSON]
    assert TAILUNG in brp.inactive_accounts()
    assert TAILUNG not in [a for r in brp.load_positions().values()
                           for v in r.values() for a in v]


def test_the_replacement_does_not_inherit_the_replaced_players_history():
    rows, _dropped, inactive = bl.load_stats()
    assert TAILUNG in inactive
    assert not [r for r in rows if int(r["account_id"]) in (TAILUNG,)]
    # Topson has no rows of his own in this window either, and that must stay visible
    assert not [r for r in rows if int(r["account_id"]) == TOPSON]


def test_lgd_mid_is_reported_as_insufficient_evidence_rather_than_imputed():
    r = bl.build()
    ranked = {(e["organization"], e["role"]) for e in r["ranking"]}
    assert ("LGD Gaming", "mid") not in ranked
    ex = next(e for e in r["excluded"]
              if e["organization"] == "LGD Gaming" and e["role"] == "mid")
    assert ex["sample"]["maps_complete_pair"] == 0
    assert "never played" in ex["exclusion_reason"]


def test_the_statistical_role_guess_is_kept_but_demoted():
    assert "EXPLORATORY ONLY" in bl.assign_roles_from_statistics.__doc__
    assert not hasattr(bl, "assign_roles")          # the old production entry point is gone


# ---- pair completeness --------------------------------------------------------------------------
def _row(acct, match, series, **kw):
    base = {"match_id": match, "_series": series, "_league": "L", "account_id": str(acct),
            "organization": "X", "player_name": "p", "parsed": "1", "kills": "5"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_a_map_missing_one_of_the_pair_is_not_a_pair_observation():
    rules = bl.load_rules()
    # both players on both maps of series A; only one player on both maps of series B
    rows = ([_row(1, "a0", "A", kills=4), _row(2, "a0", "A", kills=8),
             _row(1, "a1", "A", kills=4), _row(2, "a1", "A", kills=8)]
            + [_row(1, "b0", "B", kills=100), _row(1, "b1", "B", kills=100)])
    table, sample = bl.series_table(rows, {1, 2}, rules)
    assert sample["maps_complete_pair"] == 2
    assert sample["maps_incomplete_pair"] == 2
    assert sample["series_eligible"] == 1
    # the 100-kill solo series must not win the period, because it is not an observation of the pair
    got = bl.banner_period_scores(table, ("kills",))["L"]
    assert got == pytest.approx(2 * 6 * 107.0)      # (4+8)/2 per map, top two maps, summed


def test_a_role_whose_pair_never_played_together_yields_no_table():
    rules = bl.load_rules()
    rows = [_row(1, "a0", "A"), _row(1, "a1", "A")]
    table, sample = bl.series_table(rows, {1, 2}, rules)
    assert table == {} and sample["maps_complete_pair"] == 0
    assert sample["maps_incomplete_pair"] == 2


def test_a_single_player_role_needs_only_that_player():
    rules = bl.load_rules()
    rows = [_row(1, "a0", "A", kills=3), _row(1, "a1", "A", kills=3)]
    table, sample = bl.series_table(rows, {1}, rules)
    assert sample["maps_complete_pair"] == 2 and table


def test_the_baseline_offers_no_synthetic_pair_path():
    """Direct pair observation and a synthetic pair estimate are different quantities.

    Nothing in the baseline may quietly average two players who never played together into a
    'pair'. If such an estimator is ever added it has to be its own labelled challenger.
    """
    assert not any(n for n in dir(bl) if "synthetic" in n.lower())
    r = bl.build()
    for e in r["ranking"]:
        assert e["sample"]["maps_complete_pair"] > 0


# ---- coverage taxonomy ---------------------------------------------------------------------------
def test_coverage_is_reported_as_five_distinct_questions():
    cov = bl.build()["sample_coverage"]
    assert set(cov) == {"roster_identity_coverage", "players_with_any_historical_match",
                        "players_with_usable_parsed_map", "players_passing_sample_threshold",
                        "role_pairs_with_complete_sample"}
    assert cov["roster_identity_coverage"]["active_slots"] == 80
    # a replacement with no history is identity-covered and history-empty; both must be visible
    assert TOPSON in cov["players_with_any_historical_match"]["without"]


def test_stat_availability_separates_defined_from_usable():
    sa = bl.build()["stat_availability"]
    assert sa["scoring_stats_defined_by_the_rules"] == 18
    assert sa["directly_usable_public_player_level"] == 15
    assert sa["unavailable_or_unsupported"] == 3
    assert sorted(sa["unavailable_list"]) == ["lotuses_grabbed", "tormentor_kills",
                                              "watchers_taken"]


# ---- readiness has one source --------------------------------------------------------------------
def test_a_second_hand_written_blocker_list_is_refused(tmp_path):
    rules = copy.deepcopy(fq.load_rules())
    rules["blocking_unknowns"] = ["something"]
    p = tmp_path / "fantasy_rules.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    with pytest.raises(SystemExit, match="second, hand-written copy"):
        fq.load_rules(str(p))


def test_an_unmeasured_unknown_is_refused(tmp_path):
    rules = copy.deepcopy(fq.load_rules())
    rules["unknowns"][0]["decision_status"] = None
    p = tmp_path / "fantasy_rules.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    with pytest.raises(SystemExit, match="must be MEASURED"):
        fq.load_rules(str(p))


def test_only_blocking_entries_block(tmp_path):
    rules = fq.load_rules()
    blk = fq.blockers(rules)
    for u in rules["unknowns"]:
        if u["decision_status"] in ("ROBUST", "SCALE_ONLY", "IRRELEVANT"):
            assert u["id"] not in blk["blocking_ids"], u["id"]
        if u["decision_status"] == "BLOCKING":
            assert u["id"] in blk["blocking_ids"]


def test_a_conditional_unknown_must_say_when_it_applies(tmp_path):
    rules = copy.deepcopy(fq.load_rules())
    cond = next(u for u in rules["unknowns"] if u["decision_status"] == "CONDITIONAL")
    cond.pop("condition")
    p = tmp_path / "fantasy_rules.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    with pytest.raises(SystemExit, match="states no condition"):
        fq.load_rules(str(p))


def test_the_rune_blocker_is_conditional_on_account_state_not_permanent():
    rules = fq.load_rules()
    rune = next(u for u in rules["unknowns"] if u["id"] == "rune_definition")
    assert rune["decision_status"] == "CONDITIONAL" and rune["blocking_for"] == ["mid"]
    # before the account's banner is known it must NOT be counted as a hard blocker
    assert "rune_definition" not in fq.blockers(rules)["blocking_ids"]
    assert "rune_definition" in fq.blockers(rules)["conditional_ids"]
    # once the account state is known to trigger it, it does block
    assert "rune_definition" in fq.blockers(rules, account_state_known=True)["blocking_ids"]
