"""The inventory has to stay honest, and it has to stay out of the frozen track's way.

Three properties are worth protecting here:
  - the inventory validator refuses a document that guesses (an unresolved scoring coefficient
    filled in, a claim citing no source, a status invented on the spot);
  - the readiness gate refuses to call a question candidate-ready while the ruleset it depends on
    still has unresolved numbers, so "we do not know yet" cannot quietly become "here is an answer";
  - what the client says about the group-stage and bracket scoring curves is what the frozen
    contest_rules module already encodes. If those ever diverge, one of them is wrong.
"""
import copy
import json

import pytest

from ti_predict import contest_rules
from ti_predict.fantasy import questions as fq


@pytest.fixture(scope="module")
def doc():
    return fq.load_questions()


@pytest.fixture(scope="module")
def rules():
    return fq.load_rules()


def _write(tmp_path, obj, name="prediction_questions.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


# ---- the inventory describes the event Valve shipped -------------------------------------------
def test_group_stage_has_sixteen_slots_in_the_official_buckets(doc):
    group = [q for q in doc["questions"] if q["category"] == fq.FROZEN_TRACK_CATEGORY]
    assert sum(q["number_of_slots"] for q in group) == 16
    assert sum(len(q["selection_ids"]) for q in group) == 16
    ids = sorted(i for q in group for i in q["selection_ids"])
    assert ids == list(range(401, 417))          # Valve's own selection ids, contiguous
    caps = {q["official_en_label"]: q["number_of_slots"] for q in group}
    assert caps["4-0"] == contest_rules.CAPACITY["4-0"]
    assert caps["4-1"] == contest_rules.CAPACITY["4-1"]
    assert caps["Elimination Round Winner"] == contest_rules.CAPACITY["decider_win"]
    assert caps["Elimination Round Loser"] == contest_rules.CAPACITY["decider_loss"]
    assert caps["1-4"] == contest_rules.CAPACITY["1-4"]
    assert caps["0-4"] == contest_rules.CAPACITY["0-4"]


def test_bracket_has_fourteen_distinct_series_nodes(doc):
    br = next(q for q in doc["questions"] if q["question_id"] == "TI2026-Q-BRACKET")
    assert br["number_of_slots"] == 14
    assert sorted(br["selection_ids"]) == list(range(801, 815))
    nodes = [s["league_node_id"] for s in br["slot_map"]]
    assert len(set(nodes)) == 14
    assert not br["answerable_now"]              # unlocks only after the group stage


def test_the_client_scoring_curves_match_the_frozen_contest_rules(doc):
    """Independent confirmation, not a copy: these numbers came from the shipped client."""
    group = next(q for q in doc["questions"] if q["question_id"] == "TI2026-Q-GROUP-40")
    for n, pts in contest_rules.GROUP_SCORE.items():
        if n:
            assert f"{n}->{pts}" in group["scoring_rule"].replace(", ", ", ")
    br = next(q for q in doc["questions"] if q["question_id"] == "TI2026-Q-BRACKET")
    for n, pts in contest_rules.MAIN_EVENT_SCORE.items():
        if n:
            assert f"{n}->{pts}" in br["scoring_rule"]


def test_in_game_predictions_are_recorded_as_disabled(doc):
    a = next(a for a in doc["activities"] if a["activity_id"] == "TI2026-INGAME-PREDICTIONS")
    assert a["total_slots"] == 0 and a["status"] == "CONFIRMED"


def test_discovery_checklist_covers_all_eight_requested_categories(doc):
    assert all(key in doc["discovery_checklist_result"] for key in fq.DISCOVERY_KEYS)
    assert "NOT PRESENT" in doc["discovery_checklist_result"][
        "D_tournament_wide_player_predictions"]
    assert "NOT PRESENT" in doc["discovery_checklist_result"]["E_hero_predictions"]


def test_official_chinese_tab_labels_match_the_shipped_client(doc):
    labels = {a["activity_id"]: a["official_zh_label"] for a in doc["activities"]}
    assert labels["TI2026-PREDICTIONS"] == "赛事预测"
    assert labels["TI2026-FANTASY"] == "梦幻挑战"
    assert labels["TI2026-REWARDS"] == "奖赏"


def test_current_patch_is_not_overclaimed_as_the_ti_match_patch(doc):
    patch = doc["patch_context"]
    assert patch["current_public_patch"] == "7.41e"
    assert patch["ti2026_match_patch"] is None
    assert patch["ti2026_match_patch_status"] == "UNRESOLVED"


def test_each_fantasy_period_has_the_same_five_fixed_selection_slots(doc):
    fantasy = [q for q in doc["questions"] if q["category"].startswith("fantasy")]
    for period in (0, 1):
        period_questions = [q for q in fantasy if q["period"] == period]
        assert len(period_questions) == 5
        assert sum(q["number_of_slots"] or 0 for q in period_questions) == 5
        assert any(q["category"] == "fantasy_emblem_crafting"
                   and q["number_of_slots"] is None for q in period_questions)


def test_missing_screenshot_is_a_specific_phase_one_blocker(doc):
    reconciliation = doc["screenshot_reconciliation"]
    assert not reconciliation["evidence_available_in_this_run"]
    assert len(reconciliation["still_requires_live_client"]) >= 5
    assert doc["phase_1_status"] == "BLOCKED"


def test_every_lock_time_is_an_instant_not_a_local_wall_clock(doc):
    for q in doc["questions"]:
        if q.get("lock_time_utc"):
            assert q["lock_time_utc"].endswith("Z")


# ---- the fantasy ruleset refuses to guess -------------------------------------------------------
def test_the_stat_table_is_complete_and_partitioned_by_colour(rules):
    assert rules["stats"]["count"] == 18
    for colour in ("red", "blue", "green"):
        assert len(rules["stats"]["by_color"][colour]) == 6


def test_no_scoring_coefficient_has_been_filled_in(rules):
    assert rules["stats"]["status"] != "CONFIRMED"
    assert all(s["points_per_unit"] is None for s in rules["stats"]["list"])
    assert rules["blocking_unknowns"]


def test_the_period_structure_is_two_stages_not_daily(rules):
    assert rules["periods"]["count"] == 2
    assert [p["official_en_label"] for p in rules["periods"]["list"]] \
        == ["Group Stage", "The International"]


def test_the_selection_unit_is_a_team(rules):
    assert rules["structure"]["selection_unit"] == "team"
    assert rules["structure"]["players_scoring_per_role"] == {"core": 2, "mid": 1, "support": 2}


def test_the_shipped_coach_title_candidate_counts_are_exact(rules):
    assert len(rules["coach_titles"]["prefixes"]) == 19
    assert len(rules["coach_titles"]["suffixes"]) == 20


def test_scoring_formula_names_every_unresolved_operator(rules):
    formula = rules["scoring_pipeline"]["symbolic_formula"]
    assert formula["status"] == "PARTIAL"
    assert len(formula["unknown_operators"]) == 4


# ---- the readiness gate -------------------------------------------------------------------------
def test_no_fantasy_question_is_candidate_ready_while_the_rules_are_unresolved():
    rd = fq.readiness()
    for r in rd["questions"]:
        if r["category"].startswith("fantasy"):
            assert not r["candidate_ready"]
            assert any("unresolved" in b for b in r["blocked_by"])


def test_no_question_in_the_new_track_is_candidate_ready():
    assert fq.readiness()["candidate_ready_new_track"] == []


def test_the_frozen_group_stage_questions_are_marked_as_handled_elsewhere(doc):
    for q in doc["questions"]:
        if q["category"] == fq.FROZEN_TRACK_CATEGORY:
            assert "FROZEN" in q["handled_by"]


def test_markdown_renders_from_the_json():
    md = fq.to_markdown()
    assert "TI2026-Q-BRACKET" in md and "Blocking unknowns" in md


# ---- the validator refuses malformed or guessing documents --------------------------------------
def test_a_missing_required_field_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["questions"][0].pop("scoring_rule")
    with pytest.raises(SystemExit, match="missing scoring_rule"):
        fq.load_questions(_write(tmp_path, bad))


def test_a_duplicate_question_id_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["questions"].append(copy.deepcopy(bad["questions"][0]))
    with pytest.raises(SystemExit, match="duplicate question_id"):
        fq.load_questions(_write(tmp_path, bad))


def test_an_uncited_claim_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["questions"][0]["source"] = ["S99"]
    with pytest.raises(SystemExit, match="unknown source"):
        fq.load_questions(_write(tmp_path, bad))


def test_an_invented_status_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["questions"][0]["status"] = "PROBABLY"
    with pytest.raises(SystemExit, match="expected one of"):
        fq.load_questions(_write(tmp_path, bad))


def test_an_answerable_question_without_a_lock_time_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    q = next(q for q in bad["questions"] if q.get("answerable_now"))
    q.pop("lock_time_utc", None)
    q.pop("lock_time_note", None)
    with pytest.raises(SystemExit, match="states no lock time"):
        fq.load_questions(_write(tmp_path, bad))


def test_a_back_filled_scoring_coefficient_is_refused(tmp_path, rules):
    """The failure this guards against: pasting last year's points table into this year's schema."""
    bad = copy.deepcopy(rules)
    bad["stats"]["list"][0]["points_per_unit"] = 40
    with pytest.raises(SystemExit, match="may not be filled in"):
        fq.load_rules(_write(tmp_path, bad, "fantasy_rules.json"))


def test_a_stat_table_that_does_not_partition_by_colour_is_refused(tmp_path, rules):
    bad = copy.deepcopy(rules)
    bad["stats"]["by_color"]["red"] = bad["stats"]["by_color"]["red"][:-1]
    with pytest.raises(SystemExit, match="does not partition"):
        fq.load_rules(_write(tmp_path, bad, "fantasy_rules.json"))


def test_an_unconfirmed_ruleset_must_say_what_is_missing(tmp_path, rules):
    bad = copy.deepcopy(rules)
    bad["blocking_unknowns"] = []
    with pytest.raises(SystemExit, match="no blocking_unknowns"):
        fq.load_rules(_write(tmp_path, bad, "fantasy_rules.json"))


def test_an_incomplete_discovery_checklist_is_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["discovery_checklist_result"].pop("E_hero_predictions")
    with pytest.raises(SystemExit, match="discovery checklist is missing"):
        fq.load_questions(_write(tmp_path, bad))


def test_missing_screenshot_requests_are_refused(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["screenshot_reconciliation"]["still_requires_live_client"] = []
    with pytest.raises(SystemExit, match="no precise live-client requests"):
        fq.load_questions(_write(tmp_path, bad))


def test_a_missing_inventory_file_is_refused():
    with pytest.raises(SystemExit, match="not found"):
        fq.load_questions("does-not-exist.json")
