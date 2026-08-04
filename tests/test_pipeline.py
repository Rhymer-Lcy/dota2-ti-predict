"""End-to-end build: manifest required fields, JSON/Markdown consistency, output structure."""
import pytest

from ti_predict.contest_rules import BUCKETS, CAPACITY
from ti_predict.predict_ti15 import build, load_teams, resolve_draw, synthetic_strengths, to_markdown

REQUIRED_MANIFEST_FIELDS = ["mode", "status", "generated_at", "code_commit", "data_cutoff",
                            "strengths_source", "radiant_c", "half_life_days", "map_prob",
                            "n_sims", "seed", "c5_pairing_policy", "d4_primary",
                            "d4_selection_sensitive_buckets", "tiebreak_diagnostic", "draw_source",
                            "pods", "r1_pairings", "teams", "expected_correct", "caveats"]


def _build_synth(n=800):
    teams = load_teams()
    strength = synthetic_strengths(teams)
    pods, r1, src = resolve_draw(teams, None)
    return build(teams, strength, pods, r1, src, n, 20260813, "dry-run", None,
                 "synthetic (non-predictive)", None, c=0.0, provenance=None)


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
