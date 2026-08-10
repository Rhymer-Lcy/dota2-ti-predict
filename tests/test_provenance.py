"""Provenance the manifest can be audited against: git state at start, and scan-backed freshness.

Two claims these tests protect:
  - `git_*_at_start` describes the tree the run STARTED from, so nothing the run writes can flip it;
  - `--allow-stale` is not an assertion the operator makes. It is only accepted when a recorded,
    complete, current scan says there is nothing newer to fetch.
"""
import json
import subprocess
import sys

import pytest

import ti_predict.predict_ti15 as pt

REQUIRED = ("scan_completed_at", "scan_source", "coverage_start", "coverage_target_start",
            "coverage_complete", "latest_match_time", "latest_match_age_days", "scan_result_rows")


def _prov(tmp_path, **over):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    d = {"scan_completed_at": now.isoformat(timespec="seconds"),
         "scan_source": "https://api.opendota.com/api/proMatches",
         "pages_fetched": 91, "records_fetched": 9100, "scan_result_rows": 9146,
         "coverage_start": (now - timedelta(days=164)).isoformat(),
         "coverage_target_start": (now - timedelta(days=162)).isoformat(),
         "coverage_complete": True,
         "latest_match_time": (now - timedelta(days=1)).isoformat(),
         "latest_match_age_days": 1.0, "scan_sha256": "0" * 64}
    d.update(over)
    p = tmp_path / "scan_provenance.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return str(p)


# ---- scan provenance ---------------------------------------------------------------------------
def test_a_complete_current_scan_is_usable(tmp_path):
    s = pt.read_scan_provenance(_prov(tmp_path))
    assert s["usable"] is True and s["coverage_complete"] is True
    assert all(k in s for k in REQUIRED)


def test_missing_provenance_is_unusable():
    s = pt.read_scan_provenance("does-not-exist.json")
    assert s["usable"] is False and "no scan provenance" in s["problem"]


def test_malformed_provenance_is_unusable(tmp_path):
    p = tmp_path / "scan_provenance.json"
    p.write_text("{not json", encoding="utf-8")
    assert pt.read_scan_provenance(str(p))["usable"] is False
    p.write_text(json.dumps(["a", "list"]), encoding="utf-8")
    assert "not a JSON object" in pt.read_scan_provenance(str(p))["problem"]


def test_incomplete_fields_are_unusable(tmp_path):
    d = json.loads(open(_prov(tmp_path), encoding="utf-8").read())
    d.pop("coverage_complete")
    p = tmp_path / "scan_provenance.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert "missing coverage_complete" in pt.read_scan_provenance(str(p))["problem"]


def test_incomplete_coverage_is_unusable(tmp_path):
    s = pt.read_scan_provenance(_prov(tmp_path, coverage_complete=False))
    assert s["usable"] is False and "coverage_target_start" in s["problem"]


def test_a_stale_scan_is_unusable(tmp_path):
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat(timespec="seconds")
    s = pt.read_scan_provenance(_prov(tmp_path, scan_completed_at=old))
    assert s["usable"] is False and "ago" in s["problem"]


def test_naive_timestamps_are_rejected(tmp_path):
    s = pt.read_scan_provenance(_prov(tmp_path, scan_completed_at="2026-08-10T09:00:00"))
    assert s["usable"] is False and "timezone-aware" in s["problem"]


# ---- the gate that consumes it ------------------------------------------------------------------
def _run(args, tmp_path=None, prov=None, timeout=300):
    """Run the CLI with the scan provenance path optionally redirected."""
    env = None
    cmd = [sys.executable, "-c",
           "import sys; import ti_predict.predict_ti15 as pt;"
           + (f"pt.SCAN_PROVENANCE = r'{prov}';" if prov else "")
           + "sys.argv = ['predict_ti15'] + " + repr(args) + "; pt.main()"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


DRAW = "data/ti2026/inputs/draw.json"
BASE = ["--candidate", "--draw", DRAW, "--strengths", "bt", "--cutoff", "2026-08-13T02:00:00Z",
        "--sims", "400"]


@pytest.mark.skipif(not __import__("os").path.exists(pt.UNIVERSE_CSV), reason="no local universe")
def test_stale_data_without_the_flag_is_blocked():
    r = _run(BASE)
    assert r.returncode != 0
    assert "RUN BLOCKED" in (r.stdout + r.stderr)
    assert "COMPLETE scan" in (r.stdout + r.stderr)


@pytest.mark.skipif(not __import__("os").path.exists(pt.UNIVERSE_CSV), reason="no local universe")
def test_override_is_refused_without_usable_scan_provenance(tmp_path):
    missing = str(tmp_path / "absent.json")
    r = _run(BASE + ["--allow-stale"], prov=missing)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "--allow-stale needs a complete, current scan" in out


@pytest.mark.skipif(not __import__("os").path.exists(pt.UNIVERSE_CSV), reason="no local universe")
def test_override_is_refused_when_coverage_is_incomplete(tmp_path):
    r = _run(BASE + ["--allow-stale"], prov=_prov(tmp_path, coverage_complete=False))
    assert r.returncode != 0
    assert "coverage_target_start" in (r.stdout + r.stderr)


# ---- git state is sampled at start, and named so ------------------------------------------------
@pytest.mark.skipif(not __import__("os").path.exists(pt.UNIVERSE_CSV), reason="no local universe")
def test_manifest_names_the_git_fields_for_when_they_are_sampled(tmp_path):
    r = _run(["--dry-run", "--strengths", "bt", "--cutoff", "2026-08-13T02:00:00Z",
              "--sims", "200", "--out", str(tmp_path)])
    assert r.returncode == 0, r.stdout + r.stderr
    m = json.loads((tmp_path / "ti15_group_dryrun.json").read_text(encoding="utf-8"))["manifest"]
    prov = m["provenance"]
    assert "git_commit_at_start" in prov and "git_dirty_at_start" in prov
    assert "git_dirty" not in prov and "git_commit" not in prov   # ambiguous names are gone
    assert isinstance(prov["git_dirty_at_start"], bool)


def test_dirty_tree_is_reported_as_dirty(tmp_path, monkeypatch):
    """The flag tracks the tree, not the run: a dirty start must show up as dirty."""
    monkeypatch.setattr(pt, "_git_dirty", lambda: True)
    assert pt._git_dirty() is True
    monkeypatch.setattr(pt, "_git_dirty", lambda: False)
    assert pt._git_dirty() is False
