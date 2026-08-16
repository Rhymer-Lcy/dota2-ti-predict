"""Within-league early->late assimilation diagnostic: split safety, population audit, claim limits.

These tests police the CLAIM as much as the code. The diagnostic is not a group-to-playoff replay
and must never be asserted as one, so the population and the strength of what it supports are
themselves under test.
"""
import pytest

from ti_predict import sequential_assimilation as sa
from ti_predict.backtest import load


@pytest.fixture(scope="module")
def uni():
    u, _, _ = load()
    return u


@pytest.fixture(scope="module")
def report(uni):
    return sa.run(0.6, uni=uni, population="all")


@pytest.fixture(scope="module")
def folds_report(uni):
    return sa.run(0.6, uni=uni, population="folds")


# ------------------------------------------------------------------ split safety
def test_split_never_cuts_a_series_in_half(uni):
    for lg in sorted({str(m["leagueid"]) for m in uni if m["leagueid"]})[:40]:
        sp = sa.league_split(uni, lg, 0.6)
        if sp is None:
            continue
        early = {m["series_id"] for m in sp["early"] if m["series_id"]}
        late = {m["series_id"] for m in sp["late"] if m["series_id"]}
        assert not (early & late), lg


def test_evaluation_only_uses_teams_seen_in_the_early_phase(uni):
    sp = sa.league_split(uni, "19696", 0.6)
    seen = {m["team_a"] for m in sp["early"]} | {m["team_b"] for m in sp["early"]}
    assert all(m["team_a"] in seen and m["team_b"] in seen for m in sp["eligible"])
    assert {m["match_id"] for m in sp["eligible"]} <= {m["match_id"] for m in sp["late"]}


def test_no_arm_trains_on_the_maps_it_is_scored_on(uni):
    sp = sa.league_split(uni, "19696", 0.6)
    eval_ids = {m["match_id"] for m in sp["eligible"]}
    for cut in (sp["league_start"], sp["late_start"]):
        assert not ({m["match_id"] for m in uni if m["start_time"] < cut} & eval_ids)


def test_the_concurrent_arm_really_excludes_the_league(uni):
    sp = sa.league_split(uni, "19696", 0.6)
    ev_ids = {m["match_id"] for m in uni if str(m["leagueid"]) == "19696"}
    conc = [m for m in uni if m["start_time"] < sp["late_start"] and m["match_id"] not in ev_ids]
    assert not ({m["match_id"] for m in conc} & ev_ids)


# ------------------------------------------------------------------ population audit
def test_selection_rule_is_structural_and_declares_itself(report):
    r = report["selection_rule"]
    assert r["min_early_series"] == sa.MIN_EARLY_SERIES
    assert r["min_eligible_late_maps"] == sa.MIN_EVAL_MAPS
    assert r["requires_pre_league_training_data"] is True
    assert r["refers_to_observed_performance"] is False


def test_inclusion_depends_only_on_structure_not_on_outcomes(uni, report):
    """Recomputing eligibility from counts alone must reproduce the included set exactly."""
    included = {e["leagueid"] for e in report["events"]}
    rebuilt = set()
    for lg in sorted({str(m["leagueid"]) for m in uni if m["leagueid"]}):
        sp = sa.league_split(uni, lg, 0.6)
        if sp is None:
            continue
        if len(sp["eligible"]) < sa.MIN_EVAL_MAPS or sp["n_early_series"] < sa.MIN_EARLY_SERIES:
            continue
        if not [m for m in uni if m["start_time"] < sp["league_start"]]:
            continue
        rebuilt.add(lg)
    assert rebuilt == included


def test_every_excluded_league_carries_a_stated_reason(report):
    assert report["skipped"], "the audit is meaningless if nothing was excluded"
    for s in report["skipped"]:
        assert s["reason"] in ("no valid chronological split", "below the structural minimums",
                               "no pre-league training data (opens the scan window)")


def test_the_fold_population_is_a_strict_subset_of_the_broad_one(report, folds_report):
    broad = {e["leagueid"] for e in report["events"]}
    folds = {e["leagueid"] for e in folds_report["events"]}
    assert folds < broad
    assert all(e["preregistered_fold"] for e in folds_report["events"])


def test_the_broad_population_is_not_a_tournament_population(report):
    """It contains season-long leagues, which is exactly why the strong claim is forbidden."""
    biggest = max(e["n_series"] for e in report["events"])
    assert biggest > 300, "a league of hundreds of series is not a tournament with a playoff stage"
    non_folds = [e for e in report["events"] if not e["preregistered_fold"]]
    assert len(non_folds) > 5


def test_manifest_accounts_for_every_league_considered(uni, report):
    m = sa.manifest(report)
    seen = {e["leagueid"] for e in m["included"]} | {e["leagueid"] for e in m["excluded"]}
    assert seen == {str(x["leagueid"]) for x in uni if x["leagueid"]}


# ------------------------------------------------------------------ what it may claim
def test_assimilation_helps_on_the_broad_population(report):
    for wt in ("map", "event"):
        c = sa.summarize(report, "side_aware", "logloss", wt)["comparisons"]["D_full_vs_C_concurrent"]
        assert c["pooled_delta"] < 0
        assert c["events_improved"] > c["events_worsened"]


def test_the_tournament_only_result_is_directional_but_not_asserted_significant(folds_report):
    """Guard against silently upgrading the weak claim: direction yes, significance not required."""
    c = sa.summarize(folds_report, "side_aware", "logloss",
                     "event")["comparisons"]["D_full_vs_C_concurrent"]
    assert c["pooled_delta"] < 0
    assert "significant" in c        # recorded, never assumed


def test_no_shrinkage_candidate_beats_the_plain_refit_anywhere(uni):
    """The one load-bearing finding: kappa<1 never wins, so production is untouched."""
    for pop in ("all", "folds"):
        for f in sa.SPLIT_FRACTIONS:
            rep = sa.run(f, uni=uni, population=pop)
            for wt in ("map", "event"):
                s = sa.summarize(rep, "side_aware", "logloss", wt)
                for k, v in s["comparisons"].items():
                    if k.startswith("kappa"):
                        assert not (v["significant"] and v["pooled_delta"] < 0), \
                            f"{pop}@{f}/{wt}/{k} would change production"


def test_kappa_one_is_in_the_candidate_set_and_is_the_plain_refit():
    assert 1.00 in sa.KAPPAS


def test_the_decay_origin_alone_explains_almost_nothing(report):
    s = sa.summarize(report, "side_aware", "logloss", "map")
    origin = abs(s["pooled"]["B_origin"] - s["pooled"]["A_pre"])
    total = abs(s["pooled"]["D_full"] - s["pooled"]["A_pre"])
    assert origin < 0.2 * total


def test_the_assimilation_comparisons_agree_in_sign_across_weightings(report):
    m = sa.summarize(report, "side_aware", "logloss", "map")["comparisons"]
    e = sa.summarize(report, "side_aware", "logloss", "event")["comparisons"]
    for k in ("D_full_vs_A_pre", "D_full_vs_B_origin", "D_full_vs_C_concurrent"):
        assert (m[k]["pooled_delta"] < 0) == (e[k]["pooled_delta"] < 0), k


def test_the_shrinkage_family_shows_no_consistent_margin(report):
    """kappa=0.75 flips sign between weightings. That instability IS the reason kappa=1 stands,
    so it is asserted rather than smoothed over."""
    m = sa.summarize(report, "side_aware", "logloss", "map")["comparisons"]
    e = sa.summarize(report, "side_aware", "logloss", "event")["comparisons"]
    flips = [k for k in m if k.startswith("kappa")
             and (m[k]["pooled_delta"] < 0) != (e[k]["pooled_delta"] < 0)]
    assert flips, "expected at least one shrinkage arm to be weighting-unstable"
    for k in flips:
        assert not m[k]["significant"] and not e[k]["significant"]


def test_summary_metrics_agree_across_the_two_prediction_forms(report):
    aware = sa.summarize(report, "side_aware", "logloss", "map")
    raw = sa.summarize(report, "raw", "logloss", "map")
    for k in aware["comparisons"]:
        a, r = aware["comparisons"][k]["pooled_delta"], raw["comparisons"][k]["pooled_delta"]
        assert (a < 0) == (r < 0), f"{k}: side-aware and raw disagree on sign"


def test_events_are_filtered_on_declared_minimums(report):
    for e in report["events"]:
        assert e["eligible_late_maps"] >= sa.MIN_EVAL_MAPS
        assert e["n_early_series"] >= sa.MIN_EARLY_SERIES
