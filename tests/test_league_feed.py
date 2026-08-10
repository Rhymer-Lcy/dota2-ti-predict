"""The official league feed: round 1 is read, pods are never invented, and the gate holds."""
import json
import os

import pytest

from ti_predict.league_feed import FEED_JSON, parse_draw
from ti_predict.predict_ti15 import draw_status, load_teams, resolve_draw
from ti_predict.swiss import is_two_pod, teams_of

ORGS = {t["team"] for t in load_teams()}
DRAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "ti2026", "inputs", "draw.json")
has_feed = pytest.mark.skipif(not os.path.exists(FEED_JSON), reason="league feed snapshot absent")
has_draw = pytest.mark.skipif(not os.path.exists(DRAW), reason="draw.json absent (draw not posted)")


@has_feed
def test_feed_confirms_the_swiss_format():
    d = parse_draw()
    assert d["swiss_format"] == {"team_count": 16, "max_rounds": 5, "win_loss_limit": 4,
                                 "advancing": 3}


@has_feed
def test_round_one_covers_each_of_the_sixteen_exactly_once():
    d = parse_draw()
    assert d["r1_status"] == "official"
    flat = [t for p in d["r1_pairings"] for t in p]
    assert len(d["r1_pairings"]) == 8
    assert len(flat) == 16 and len(set(flat)) == 16
    assert set(flat) == ORGS                       # every id resolved to a tracked organization


@has_feed
def test_pods_are_never_inferred_from_the_feed():
    """The feed exposes one undivided Swiss group; A/B labels are broadcast slots, not pods.

    Round-1 node names ("Match 1.A" .. "Match 4.B") split on SCHEDULED TIME, and a pod partition
    read off them would be a fabrication. parse_draw must report the structure as unresolved.
    """
    d = parse_draw()
    assert d["pods_status"] == "unresolved"
    assert "podA" not in d and "podB" not in d
    times = {s["scheduled_utc"] for s in d["r1_schedule"]}
    assert len(times) == 2                         # the A/B labels are two start times


@has_draw
def test_draw_file_declares_official_r1_and_unresolved_pods():
    st = draw_status(DRAW)
    assert st["r1_status"] == "official" and st["pods_status"] == "unresolved"
    assert st["pod_evidence_source"] and st["feed_sha256"]


@has_draw
def test_unresolved_pods_give_the_open_structure_in_research_mode():
    pods, r1, _ = resolve_draw(load_teams(), DRAW)
    assert not is_two_pod(pods)
    assert sorted(teams_of(pods)) == sorted(ORGS)
    assert len(r1) == 8


@has_draw
def test_unresolved_pods_block_an_official_run():
    with pytest.raises(SystemExit, match="pods_status='unresolved'"):
        resolve_draw(load_teams(), DRAW, require_r1=True)


def test_bad_pods_status_value_fails_closed(tmp_path):
    p = tmp_path / "draw.json"
    p.write_text(json.dumps({"pods_status": "probably fine"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="pods_status must be"):
        resolve_draw(load_teams(), str(p))


def test_missing_pods_without_a_declaration_still_fails_closed(tmp_path):
    """Silence is not consent: a draw with no pods and no pods_status is rejected, not opened up."""
    p = tmp_path / "draw.json"
    p.write_text(json.dumps({"r1_pairings": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="8 teams"):
        resolve_draw(load_teams(), str(p))


def test_open_structure_may_be_declared_explicitly_for_an_official_run(tmp_path):
    """If the single undivided 16-team Swiss IS the published format, say so and own the claim.

    'no pod split was found' must stay blocking; 'the published structure is one 16-team Swiss' is a
    positive, recorded declaration that unblocks the official run.
    """
    teams = load_teams()
    names = [t["team"] for t in teams]
    r1 = [[names[2 * i], names[2 * i + 1]] for i in range(8)]
    p = tmp_path / "draw.json"
    p.write_text(json.dumps({"pods_status": "confirmed", "structure": "open-16",
                             "r1_status": "official", "r1_pairings": r1}), encoding="utf-8")
    pods, got_r1, _ = resolve_draw(teams, str(p), require_r1=True)
    assert not is_two_pod(pods) and len(got_r1) == 8
    assert draw_status(str(p))["declared_structure"] == "open-16"


def test_unknown_structure_value_fails_closed(tmp_path):
    p = tmp_path / "draw.json"
    p.write_text(json.dumps({"structure": "three-pod"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="structure must be"):
        resolve_draw(load_teams(), str(p))
