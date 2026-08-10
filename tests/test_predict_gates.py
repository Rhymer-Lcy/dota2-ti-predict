"""Gating: cutoff format, draw-file validation (valid and invalid boundaries)."""
import json

import pytest

from ti_predict.predict_ti15 import (_tz_aware, load_teams, parse_cutoff, resolve_draw,
                                     synthetic_strengths)

TEAMS = load_teams()
NAMES = [t["team"] for t in TEAMS]


def _write(tmp_path, obj):
    p = tmp_path / "draw.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def _valid_draw():
    a, b = NAMES[:8], NAMES[8:]
    r1 = [[a[i], a[i + 1]] for i in range(0, 8, 2)] + [[b[i], b[i + 1]] for i in range(0, 8, 2)]
    return {"podA": a, "podB": b, "r1_pairings": r1}


def test_tz_aware_accepts_only_timestamped_utc():
    assert _tz_aware("2026-08-13T15:00:00Z")
    assert _tz_aware("2026-08-13T15:00:00+00:00")
    assert not _tz_aware("2026-08-13")                          # date-only
    assert not _tz_aware("2026-08-13T15:00:00")                 # naive (no timezone)
    assert not _tz_aware(None)


def test_parse_cutoff_date_and_iso():
    ts_date, iso_date = parse_cutoff("2026-08-13")
    ts_iso, iso_iso = parse_cutoff("2026-08-13T15:00:00Z")
    assert ts_iso - ts_date == 15 * 3600
    assert iso_iso.endswith("+00:00")


def test_synthetic_strengths_covers_16():
    s = synthetic_strengths(TEAMS)
    assert len(s) == 16 and set(s) == set(NAMES)


def test_valid_draw_resolves(tmp_path):
    pods, r1, src = resolve_draw(TEAMS, _write(tmp_path, _valid_draw()), require_r1=True)
    assert len(pods[0]) == 8 and len(pods[1]) == 8 and len(r1) == 8


def test_missing_r1_rejected_when_required(tmp_path):
    d = _valid_draw(); d.pop("r1_pairings")
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d), require_r1=True)


def test_duplicate_pods_rejected(tmp_path):
    d = _valid_draw(); d["podB"] = d["podA"]
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d), require_r1=True)


def test_wrong_pod_size_rejected(tmp_path):
    d = _valid_draw(); d["podA"] = d["podA"][:7]
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d))


def test_r1_wrong_count_rejected(tmp_path):
    d = _valid_draw(); d["r1_pairings"] = d["r1_pairings"][:7]
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d), require_r1=True)


def test_r1_cross_pod_rejected(tmp_path):
    d = _valid_draw(); d["r1_pairings"][0] = [d["podA"][0], d["podB"][0]]
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d), require_r1=True)


def test_unknown_team_rejected(tmp_path):
    d = _valid_draw(); d["podA"][0] = "Not A Real Team"
    with pytest.raises(SystemExit):
        resolve_draw(TEAMS, _write(tmp_path, d))


# ---- candidate mode: the production answer as of now, under the SAME gates as --official ----
def test_candidate_mode_answers_to_the_official_gates():
    """A candidate run must not be a soft path around the gate; only its label and path differ."""
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "ti_predict.predict_ti15", "--candidate",
                        "--cutoff", "2026-08-13"], capture_output=True, text=True, timeout=180)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "OFFICIAL RUN BLOCKED" in out
    assert "timezone-aware" in out and "--draw" in out and "--strengths" in out


def test_candidate_status_and_filename_cannot_be_confused_with_the_final_run():
    from ti_predict.predict_ti15 import build, load_teams, resolve_draw, synthetic_strengths
    from ti_predict.rosters import roster_audit
    teams = load_teams()
    pods, r1, src = resolve_draw(teams, None)
    out = build(teams, synthetic_strengths(teams), [pods], r1, src, 400, 1, "candidate", None,
                "synthetic (non-predictive)", None, c=0.0, provenance=None, draw_state=None,
                rosters=roster_audit(orgs=[t["team"] for t in teams]))
    assert out["manifest"]["status"] == "SUBMISSION-GRADE CANDIDATE - NOT FINAL LOCK-DAY RUN"
    assert out["manifest"]["status"] != "OFFICIAL"
