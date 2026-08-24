"""The Fantasy settlement addendum must archive new truth without disturbing old truth.

Four properties are what this file exists to defend:

  the sealed closure's historical status survives verbatim. A later capture does not get to edit
  what was known at seal time; it gets its own file and says so.
  the account mapping is proved from configuration, never from scores. A mapping that reads the
  realized totals would assume the very comparison it is used to make, so there is a test that
  scrambles the totals and requires the mapping not to move.
  the transcription is checkable. Every frame reconciles emblem rows -> role score -> displayed
  total within display rounding and nothing wider, and mutating a single row must break it.
  no identity spreads. The four raw frames stay private, and nothing they also show reaches a
  tracked file.
"""
import copy
import json
import os
import subprocess

import pytest

from ti_predict import chronology as ch
from ti_predict import fantasy_settlement as fsm

REPO = fsm.REPO

NEW_IDS = ["ti2026-ev-007", "ti2026-ev-008", "ti2026-ev-009", "ti2026-ev-010"]
NEW_PUBLIC_ARTIFACTS = [
    "data/ti2026/outcomes/fantasy_results.json",
    "predictions/ti2026/postmortem/fantasy_settlement_addendum.json",
    "data/ti2026/evidence/private_evidence_index.json",
]

# Assembled from fragments on purpose: written out, this file would itself contain every string it
# forbids and the repository-wide privacy scan would flag it.
DRIVE = "F:"
PRIVATE_DIR_SUFFIX = "-evidence" + "-private"


def _identity_needles():
    return ["Alice in " + "Chains", "".join(map(chr, (0x5343, 0x4E28, 0x57CE)))]


def _leak_needles():
    return _identity_needles() + [
        "steam" + "id", "STEAM" + "_",
        DRIVE + chr(92), DRIVE + "/",
        "dota2-ti-predict" + PRIVATE_DIR_SUFFIX,
    ]


@pytest.fixture(scope="module")
def results():
    return json.load(open(fsm.RESULTS, encoding="utf-8"))


@pytest.fixture(scope="module")
def addendum():
    return json.load(open(fsm.ADDENDUM, encoding="utf-8"))


@pytest.fixture(scope="module")
def index():
    return fsm.load_index()


# --------------------------------------------------------------------------- 1-3 evidence hygiene
def test_the_four_evidence_ids_are_new_and_unique(index):
    ids = [e["evidence_id"] for e in index["evidence"]]
    assert len(ids) == len(set(ids)), "duplicate evidence id in the public index"
    assert set(NEW_IDS) <= set(ids)
    # one id per (account, period), no collisions and no gaps
    assert sorted(fsm.EVIDENCE[k]["evidence_id"] for k in fsm.EVIDENCE) == NEW_IDS
    assert len(fsm.EVIDENCE) == 4


def test_new_public_entries_keep_the_raw_frames_private(index):
    for e in [e for e in index["evidence"] if e["evidence_id"] in NEW_IDS]:
        assert e["raw_evidence_public"] is False
        assert e["raw_evidence_storage"] == "private_local_external"
        assert e["reason_not_committed"]
        assert len(e["sha256"]) == 64
        assert e["source_tier"] == 1 and e["operator_supplied"] is True
        assert e["pixels"] == [2048, 1152]


def test_new_evidence_is_post_event_and_never_a_production_input(index):
    for e in [e for e in index["evidence"] if e["evidence_id"] in NEW_IDS]:
        assert e["evidence_phase"] == "post_event"
        assert e["observed_after_prediction"] is True
        assert e["used_in_original_production"] is False
        assert e["valid_production_input"] is False
        assert e["period"] in fsm.PERIODS and e["account_role"] in fsm.ACCOUNTS
        with pytest.raises(SystemExit):
            ch.assert_production_document(e, "a production input")


# --------------------------------------------------------------------------- 4-5 privacy
def test_results_are_labelled_only_by_anonymous_account_role(results, addendum):
    """Every result-bearing structure is keyed operator/target. The sealed review labels appear
    only inside the block whose job is to state the correspondence between the two label systems."""
    for period in fsm.PERIODS:
        assert set(results["periods"][period]) == set(fsm.ACCOUNTS)
        assert set(addendum["official_results"][period]) == set(fsm.ACCOUNTS)
        assert set(addendum["structural_attribution"][period]["coach_titles"]) == set(fsm.ACCOUNTS)
    assert set(addendum["two_period_arithmetic_sums"]) >= set(fsm.ACCOUNTS)
    assert addendum["account_mapping"]["mapping"] == {"account_a": "operator", "account_b": "target"}
    for rec in results["periods"]["main_event"].values():
        assert rec["account_role"] in fsm.ACCOUNTS


def test_no_new_public_artifact_carries_an_identity_or_a_private_path():
    for rel in NEW_PUBLIC_ARTIFACTS:
        src = open(os.path.join(REPO, rel), encoding="utf-8").read()
        for needle in _leak_needles():
            assert needle not in src, f"{rel} leaks {needle!r}"


def test_no_new_raw_frame_is_tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("git is unavailable")
    tracked = [p for p in out.stdout.splitlines() if p]
    for key in fsm.EVIDENCE:
        name = fsm.CANONICAL_FILENAME[key]
        assert not any(p.endswith(name) for p in tracked), name
    assert not any("fantasy/settlement" in p for p in tracked)


# --------------------------------------------------------------------------- 6-7 the arithmetic
def test_every_frame_reconciles_within_display_rounding(results):
    for period in fsm.PERIODS:
        for account in fsm.ACCOUNTS:
            rec = results["periods"][period][account]["internal_reconciliation"]
            assert rec["all_within_tolerance"], (period, account, rec)
            for role, r in rec["per_role"].items():
                assert r["abs_difference"] <= r["tolerance"], (period, account, role, r)
            assert rec["abs_difference"] <= rec["tolerance"]
            # the tolerance really is display rounding and nothing wider
            assert rec["tolerance"] < 0.03


def test_a_mistranscribed_emblem_row_fails_closed(monkeypatch):
    frames = copy.deepcopy(fsm.FRAMES)
    frames[("target", "main_event")]["roles"]["core"]["emblems"][0]["points"] += 1.0
    monkeypatch.setattr(fsm, "FRAMES", frames)
    with pytest.raises(SystemExit):
        fsm.assert_reconciled()


def test_derived_differences_are_exact_at_display_precision(results):
    for period in fsm.PERIODS:
        d = results["derived_arithmetic"]["per_period_differences"][period]
        o = results["periods"][period]["operator"]["direct_first_party_facts"]
        t = results["periods"][period]["target"]["direct_first_party_facts"]
        assert d["target_minus_operator"] == round(t["displayed_total"] - o["displayed_total"], 2)
        for role in fsm.ROLES:
            expect = round(t["roles"][role]["displayed_score"] - o["roles"][role]["displayed_score"], 2)
            assert d["per_role_target_minus_operator"][role] == expect
        assert d["sum_matches_overall_within_display_rounding"] is True


# --------------------------------------------------------------------------- 8 the two-period sums
def test_two_period_sums_are_not_claimed_to_be_official(results, addendum):
    for doc in (results["derived_arithmetic"]["two_period_arithmetic_sums"],
                addendum["two_period_arithmetic_sums"]):
        assert doc["is_official_overall_total"] is False
        assert doc["why_not"]
        assert doc["label"].startswith("arithmetic sum")
        assert "percentile" not in json.dumps({k: v for k, v in doc.items()
                                               if k != "percentiles_are_not_combined"}).lower()
        for account in fsm.ACCOUNTS:
            expect = round(sum(fsm.FRAMES[(account, p)]["displayed_total"] for p in fsm.PERIODS), 2)
            assert doc[account] == expect


def test_percentiles_are_never_combined(results):
    """A percentile is reported against its own period and nothing else."""
    for period in fsm.PERIODS:
        for account in fsm.ACCOUNTS:
            f = results["periods"][period][account]["direct_first_party_facts"]
            assert isinstance(f["displayed_percentile_pct"], float)
            assert f["percentile_scope"]
    sums = results["derived_arithmetic"]["two_period_arithmetic_sums"]
    assert "percentile" not in [k.lower() for k in sums]
    for period in fsm.PERIODS:
        diffs = results["derived_arithmetic"]["per_period_differences"][period]
        assert not any("percentile" in k for k in diffs)


# --------------------------------------------------------------------------- 9-10 history preserved
def test_the_sealed_closure_is_untouched():
    closure = os.path.join(fsm.REPO, "predictions", "ti2026", "postmortem", "fantasy_closure.json")
    doc = json.load(open(closure, encoding="utf-8"))
    assert doc["realized_fantasy_outcome"]["status"] == "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED"
    assert doc["status"] == "SEALED"
    out = subprocess.run(["git", "diff", "--quiet", "HEAD", "--",
                          "predictions/ti2026/postmortem/fantasy_closure.json"], cwd=REPO)
    if out.returncode == 128:
        pytest.skip("git is unavailable")
    assert out.returncode == 0, "the sealed Fantasy closure has been modified"


def test_the_addendum_records_the_transition(addendum, results):
    assert addendum["original_closure_status"] == "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED"
    assert addendum["current_status"] == "OFFICIAL_FANTASY_OUTCOME_ARCHIVED"
    assert addendum["update_type"] == "post_seal_first_party_evidence_addendum"
    assert results["status"] == "OFFICIAL_FANTASY_OUTCOME_ARCHIVED"
    sup = results["supersedes_knowledge_state_of"]
    assert sup["historical_status"] == "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED"
    assert sup["historical_status_is_preserved"] is True
    assert [e["evidence_id"] for e in addendum["evidence"]] == NEW_IDS


def test_frozen_pre_event_fantasy_artifacts_are_unchanged():
    out = subprocess.run(["git", "diff", "--quiet", "HEAD", "--",
                          "predictions/ti2026/fantasy",
                          "predictions/ti2026/playoffs",
                          "predictions/ti2026/group-stage",
                          "data/ti2026/inputs"], cwd=REPO)
    if out.returncode == 128:
        pytest.skip("git is unavailable")
    assert out.returncode == 0, "a frozen pre-event artifact was modified by the addendum"


# --------------------------------------------------------------------------- 11 chronology
def test_the_settlement_files_cannot_reach_a_production_fit(results, addendum):
    for doc in (results, addendum):
        assert doc["post_event_only"] is True
        assert doc["observed_after_prediction"] is True
        assert doc["valid_production_input"] is False
        with pytest.raises(SystemExit):
            ch.assert_production_document(doc, "a production input")
    for path in (fsm.RESULTS, fsm.ADDENDUM):
        assert ch.is_post_event_path(path)
        with pytest.raises(SystemExit):
            ch.assert_production_input(path, "a production input")
    rows = [{"phase": "post_event", "account_role": "operator", "points": 82839.01}]
    with pytest.raises(SystemExit):
        ch.assert_production_rows(rows, "the frozen estimator")


def test_the_addendum_module_does_not_import_a_production_estimator():
    src = open(os.path.join(REPO, "ti_predict", "fantasy_settlement.py"), encoding="utf-8").read()
    for forbidden in ("predict_main_event", "predict_ti15", "banner_model", "coach_optimize",
                      "preselection", "fastvalue"):
        assert f"import {forbidden}" not in src, f"the addendum must not re-run {forbidden}"
    assert "read_not_recomputed" in src


# --------------------------------------------------------------------------- 12-13 the account mapping
def test_the_account_mapping_is_proven(addendum):
    m = addendum["account_mapping"]
    assert m["status"] == "ACCOUNT_MAPPING_PROVEN"
    assert m["mapping"] == {"account_a": "operator", "account_b": "target"}
    assert m["unresolved"] == []
    assert m["score_information_used"] is False
    for s in m["supports"]:
        assert s["configuration_match"] is True
        assert s["configuration_fields_compared"] >= 20
        assert s["label_published_in_evidence_index"] == s["review_label"]


def test_the_mapping_does_not_depend_on_realized_scores(monkeypatch):
    """Swap the realized totals between accounts. A mapping that reads scores would move; this
    one must not, because it is a configuration match."""
    before = fsm.account_mapping()
    frames = copy.deepcopy(fsm.FRAMES)
    for period in fsm.PERIODS:
        o, t = frames[("operator", period)], frames[("target", period)]
        o["displayed_total"], t["displayed_total"] = t["displayed_total"], o["displayed_total"]
        o["displayed_percentile_pct"], t["displayed_percentile_pct"] = (
            t["displayed_percentile_pct"], o["displayed_percentile_pct"])
    monkeypatch.setattr(fsm, "FRAMES", frames)
    assert fsm.account_mapping() == before


def test_the_configuration_pin_reproduces_the_frozen_states():
    """The two group-stage counterparts are tracked, so this runs on any clone. The two Main Event
    counterparts are private; where the archive is mounted the live check must agree with what the
    module records, and where it is not the recorded claim is carried."""
    for key, pin in fsm.FROZEN_PINS.items():
        live = fsm.verify_pin(key)
        if pin["kind"] == "tracked":
            assert live["checked"] is True and live["match"] is True, (key, live)
            assert live["fields_compared"] >= 16
        elif live.get("checked"):
            rec = fsm.PRIVATE_PIN_RECORDED[key]
            assert live["match"] == rec["match"], (key, live)
            assert live["fields_compared"] == rec["fields_compared"], (key, live)


def test_a_wrong_configuration_breaks_the_pin(monkeypatch):
    frames = copy.deepcopy(fsm.FRAMES)
    frames[("operator", "group_stage")]["roles"]["core"]["emblems"][0]["multiplier"] = 9.9
    monkeypatch.setattr(fsm, "FRAMES", frames)
    live = fsm.verify_pin(("operator", "group_stage"))
    assert live["match"] is False and live["mismatches"]


# --------------------------------------------------------------------------- 14 the retrospective
def test_the_gap_decomposition_is_an_exact_identity(addendum):
    g = addendum["frozen_vs_realized"]["main_event"]["gap_decomposition"]
    total = g["frozen_estimate_gap"] + g["excluded_term_gap"] + g["residual"]
    assert abs(total - g["realized_gap"]) < 1e-6
    assert g["exact_by_construction"] is True


def test_no_calibration_or_model_error_claim_is_made(addendum):
    lv = addendum["frozen_vs_realized"]["main_event"]["level_difference"]
    assert lv["is_model_error"] is False and lv["why_not"]
    assert any("calibrat" in s.lower() for s in addendum["does_not_prove"])
    assert any("not a calibration claim" in s.lower() for s in addendum["what_this_is_not"])


def test_the_unobservable_terms_are_not_retrofitted_into_the_forecast(addendum):
    u = addendum["frozen_vs_realized"]["main_event"]["excluded_terms"]
    assert set(u["unobservable_statistics"]) == {"madstone", "watchers_taken", "lotuses_grabbed"}
    fe = addendum["frozen_vs_realized"]["main_event"]["frozen_estimate"]
    assert fe["read_not_recomputed"] is True
    closure = fsm.load_closure()
    plug = closure["observed_data_plug_in_estimate"]
    # the frozen numbers in the addendum are the sealed ones, not recomputed ones
    assert fe["per_account"]["operator"] == plug["account_a_total"]
    assert fe["per_account"]["target"] == plug["account_b_total"]
    assert fe["difference_target_minus_operator"] == plug["difference_b_minus_a"]
    # every U term is an emblem actually displayed on the settled banner
    for account, blk in u["per_account"].items():
        for row in blk["emblems"]:
            banner = fsm.FRAMES[(account, "main_event")]["roles"][row["role"]]["emblems"]
            assert any(fsm.canonical_stat(e["stat"]) == row["stat"]
                       and e["points"] == row["points"] for e in banner), row


def test_the_group_stage_is_not_scored_against_an_invented_forecast(addendum):
    g = addendum["frozen_vs_realized"]["group_stage"]
    assert g["status"] == "NO_FROZEN_PRE_EVENT_FORECAST"
    assert "predicted" not in json.dumps(g).lower()
    for path in g["what_was_searched"]:
        assert os.path.exists(os.path.join(REPO, path)), path


def test_attribution_is_marked_unidentifiable_where_the_deployment_differed(addendum):
    for period in fsm.PERIODS:
        for role, r in addendum["structural_attribution"][period]["per_role"].items():
            assert r["identifiable"] == r["same_player_set"]
            if not r["same_player_set"]:
                assert "confounded" in r["attribution"]
            if r["isolates_emblem_construction"]:
                assert r["same_player_set"] and r["same_coach_title"]


# --------------------------------------------------------------------------- 15 determinism
def test_the_filed_artifacts_match_a_fresh_build(results, addendum):
    assert json.dumps(fsm.build_results(), sort_keys=True) == json.dumps(results, sort_keys=True)
    assert json.dumps(fsm.build_addendum(), sort_keys=True) == json.dumps(addendum, sort_keys=True)


def test_appending_to_the_index_is_idempotent():
    _, added = fsm.update_index(write=False)
    assert added == [], "the four records are already in the index; a rerun must add nothing"
