"""Failure rehearsal: every official-path defect must fail closed with an actionable message."""
import json
import subprocess
import sys

import pytest

import ti_predict.predict_ti15 as pt
from ti_predict.predict_ti15 import load_teams, resolve_draw

TEAMS = load_teams()
NAMES = [t["team"] for t in TEAMS]


def _draw(tmp_path, obj, name="draw.json", raw=None):
    p = tmp_path / name
    p.write_text(raw if raw is not None else json.dumps(obj), encoding="utf-8")
    return str(p)


def test_corrupt_json_fails_closed(tmp_path):
    with pytest.raises(SystemExit, match="cannot read"):
        resolve_draw(TEAMS, _draw(tmp_path, None, raw="{not valid json"), require_r1=True)


def test_non_object_json_fails_closed(tmp_path):
    with pytest.raises(SystemExit, match="top-level"):
        resolve_draw(TEAMS, _draw(tmp_path, ["just", "a", "list"]))


def test_missing_pod_keys_fail_closed(tmp_path):
    with pytest.raises(SystemExit, match="8 teams"):
        resolve_draw(TEAMS, _draw(tmp_path, {"r1_pairings": []}))


def test_r1_team_repeated_fails_closed(tmp_path):
    a, b = NAMES[:8], NAMES[8:]
    r1 = [[a[0], a[1]], [a[0], a[2]], [a[3], a[4]], [a[5], a[6]],
          [b[0], b[1]], [b[2], b[3]], [b[4], b[5]], [b[6], b[7]]]
    with pytest.raises(SystemExit, match="every team exactly once"):
        resolve_draw(TEAMS, _draw(tmp_path, {"podA": a, "podB": b, "r1_pairings": r1}),
                     require_r1=True)


def test_missing_universe_fails_closed(monkeypatch):
    monkeypatch.setattr(pt, "UNIVERSE_CSV", str(pt.UNIVERSE_CSV) + ".does-not-exist")
    with pytest.raises(SystemExit, match="regenerate it per docs/lockday-runbook.md"):
        pt.bt_strengths_for(TEAMS, 1_700_000_000)


def test_official_cli_blocks_without_inputs():
    """CLI-level: official mode with no draw / synthetic strengths / date-only cutoff must exit
    nonzero before any simulation work."""
    r = subprocess.run([sys.executable, "-m", "ti_predict.predict_ti15", "--official",
                        "--cutoff", "2026-08-13"], capture_output=True, text=True, timeout=120)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "OFFICIAL RUN BLOCKED" in out
    assert "timezone-aware" in out          # date-only cutoff named explicitly
    assert "--draw" in out and "--strengths" in out
