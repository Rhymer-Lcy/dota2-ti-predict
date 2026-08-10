"""End-to-end build: manifest required fields, JSON/Markdown consistency, output structure."""
import pytest

from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.predict_ti15 import (build, draw_status, load_teams, resolve_draw,
                                     synthetic_strengths, to_markdown)
from ti_predict.rosters import roster_audit

REQUIRED_MANIFEST_FIELDS = ["mode", "status", "generated_at", "code_commit", "data_cutoff",
                            "strengths_source", "radiant_c", "half_life_days", "map_prob",
                            "n_sims", "seed", "c5_pairing_policy", "points_refinement",
                            "d4_primary", "d4_selection_sensitive_buckets", "tiebreak_diagnostic",
                            "draw_source", "draw_status", "roster_audit", "pods", "r1_pairings",
                            "teams", "expected_correct", "caveats"]


def _build_synth(n=800):
    teams = load_teams()
    strength = synthetic_strengths(teams)
    pods, r1, src = resolve_draw(teams, None)
    return build(teams, strength, [pods], r1, src, n, 20260813, "dry-run", None,
                 "synthetic (non-predictive)", None, c=0.0, provenance=None,
                 draw_state=draw_status(None), rosters=roster_audit(orgs=[t["team"] for t in teams]))


def test_manifest_has_required_fields():
    m = _build_synth()["manifest"]
    for f in REQUIRED_MANIFEST_FIELDS:
        assert f in m, f"missing manifest field: {f}"
    assert m["mode"] == "dry-run" and m["status"] != "OFFICIAL"


def test_probabilities_and_slate_structure():
    out = _build_synth()
    for t, row in out["probabilities"].items():
        assert sum(row.values()) == pytest.approx(1.0, abs=1e-3)   # outputs rounded to 4 decimals
    assert all(len(out["slate"][b]) == CAPACITY[b] for b in BUCKETS)


def test_markdown_is_generated_from_the_same_result():
    out = _build_synth()
    md = to_markdown(out)
    assert str(out["expected_correct"]) in md                   # MD derives from the JSON fact source
    assert out["manifest"]["status"] in md


def test_manifest_carries_the_draw_publication_status_and_roster_audit():
    """The artifact must say what was official and what was assumed, and who changed a lineup."""
    m = _build_synth()["manifest"]
    assert set(m["draw_status"]) >= {"r1_status", "structure", "structure_status",
                                     "pod_membership_status"}
    assert m["roster_audit"]["teams_audited"] == 16
    assert [c["organization"] for c in m["roster_audit"]["changed"]] == ["LGD Gaming"]
    assert m["roster_audit"]["blocking"] == []
    assert m["pods"]["structure"] in ("two_pod", "open-16")
    assert set(m["draw_status"]) >= {"structure", "structure_status", "pod_membership_status"}


def test_marginalized_membership_is_declared_and_measured():
    """With the membership unresolved the manifest must say so and quantify what it could cost."""
    from ti_predict.swiss import admissible_two_pod_partitions
    teams = load_teams()
    names = [t["team"] for t in teams]
    r1 = [(names[2 * i], names[2 * i + 1]) for i in range(8)]
    pods_list = admissible_two_pod_partitions(r1)[:4]      # a subset keeps the test fast
    out = build(teams, synthetic_strengths(teams), pods_list, r1, "test", 1200, 20260813,
                "dry-run", None, "synthetic (non-predictive)", None, c=0.0, provenance=None,
                draw_state=draw_status(None),
                rosters=roster_audit(orgs=names))
    pods = out["manifest"]["pods"]
    assert pods["structure"] == "two_pod"
    assert pods["pod_membership_status"] == "unresolved"
    ag = pods["membership_agreement"]
    assert ag["n_admissible_memberships"] == 4
    assert 0 <= ag["memberships_with_identical_slate"] <= 4
    assert ag["max_regret_expected_correct"] >= ag["mean_regret_expected_correct"]
    assert "held-out" in ag["regret_basis"]
