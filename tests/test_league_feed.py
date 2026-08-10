"""The official league feed: round 1 is read, pod membership is never invented, and the gate holds.

The distinction these tests protect: the two-pod STRUCTURE is an official rule, while the pod
MEMBERSHIP is unpublished. A feed with no pod field is evidence about the feed, not about the format,
so it may never be turned into an "undivided 16-team Swiss" claim.
"""
import json
import os

import pytest

from ti_predict.league_feed import FEED_JSON, parse_draw
from ti_predict.predict_ti15 import draw_status, load_teams, resolve_draw
from ti_predict.swiss import admissible_two_pod_partitions, is_two_pod, teams_of

TEAMS = load_teams()
ORGS = {t["team"] for t in TEAMS}
NAMES = [t["team"] for t in TEAMS]
R1 = [[NAMES[2 * i], NAMES[2 * i + 1]] for i in range(8)]
DRAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "ti2026", "inputs", "draw.json")
has_feed = pytest.mark.skipif(not os.path.exists(FEED_JSON), reason="league feed snapshot absent")
has_draw = pytest.mark.skipif(not os.path.exists(DRAW), reason="draw.json absent (draw not posted)")


def _write(tmp_path, obj):
    p = tmp_path / "draw.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


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
def test_feed_silence_leaves_membership_unresolved_but_never_denies_the_structure():
    """The A/B labels are broadcast blocks (two start times), not pods, and absence != open-16."""
    d = parse_draw()
    assert d["structure"] == "two_pod" and d["structure_status"] == "confirmed"
    assert d["pod_membership_status"] == "unresolved"
    assert "podA" not in d and "podB" not in d
    times = {s["scheduled_utc"] for s in d["r1_schedule"]}
    assert len(times) == 2                         # the .A / .B suffixes are two start times


@has_draw
def test_draw_file_separates_structure_from_membership():
    st = draw_status(DRAW)
    assert st["r1_status"] == "official"
    assert st["structure"] == "two_pod" and st["structure_status"] == "confirmed"
    assert st["pod_membership_status"] == "unresolved"
    assert st["structure_evidence"] and st["feed_sha256"]


@has_draw
def test_unresolved_membership_asks_the_caller_to_marginalize():
    pods, r1, _ = resolve_draw(TEAMS, DRAW)
    assert pods is None                            # None == "marginalize", not "no pods"
    assert len(r1) == 8
    hyps = admissible_two_pod_partitions([tuple(p) for p in r1])
    assert len(hyps) == 35 and all(is_two_pod(h) for h in hyps)


def test_every_admissible_membership_respects_the_posted_round_one(tmp_path):
    for podA, podB in admissible_two_pod_partitions([tuple(p) for p in R1]):
        pod_of = {t: "A" for t in podA}
        pod_of.update({t: "B" for t in podB})
        assert len(podA) == 8 and len(podB) == 8 and set(podA + podB) == ORGS
        for a, b in R1:
            assert pod_of[a] == pod_of[b]


def test_open_16_is_refused_for_an_official_run(tmp_path):
    """The comparator must never become the official structure, however it is declared."""
    p = _write(tmp_path, {"structure": "open-16", "structure_status": "confirmed",
                          "pod_membership_status": "confirmed", "r1_status": "official",
                          "r1_pairings": R1})
    with pytest.raises(SystemExit, match="sensitivity comparator"):
        resolve_draw(TEAMS, p, require_r1=True)
    pods, _, _ = resolve_draw(TEAMS, p)            # still available for research
    assert not is_two_pod(pods) and sorted(teams_of(pods)) == sorted(ORGS)


def test_assumed_structure_blocks_an_official_run(tmp_path):
    """A structure the operator merely assumes is not a structure an official slate may claim."""
    p = _write(tmp_path, {"structure": "two_pod", "structure_status": "assumed",
                          "pod_membership_status": "unresolved", "r1_status": "official",
                          "r1_pairings": R1})
    with pytest.raises(SystemExit, match="CONFIRMED pairing structure"):
        resolve_draw(TEAMS, p, require_r1=True)
    pods, _, _ = resolve_draw(TEAMS, p)            # research mode still runs
    assert pods is None


def test_bad_status_values_fail_closed(tmp_path):
    with pytest.raises(SystemExit, match="structure must be"):
        resolve_draw(TEAMS, _write(tmp_path, {"structure": "three_pod"}))
    with pytest.raises(SystemExit, match="structure_status must be"):
        resolve_draw(TEAMS, _write(tmp_path, {"structure_status": "probably fine"}))
    with pytest.raises(SystemExit, match="pod_membership_status must be"):
        resolve_draw(TEAMS, _write(tmp_path, {"pod_membership_status": "probably fine"}))


def test_a_published_membership_is_still_validated(tmp_path):
    """Declaring the membership confirmed does not exempt it from the partition checks."""
    with pytest.raises(SystemExit, match="8 teams"):
        resolve_draw(TEAMS, _write(tmp_path, {"pod_membership_status": "confirmed",
                                              "r1_pairings": R1}))
    podA, podB = admissible_two_pod_partitions([tuple(p) for p in R1])[0]
    good = _write(tmp_path, {"structure": "two_pod", "structure_status": "confirmed",
                             "pod_membership_status": "confirmed", "podA": podA, "podB": podB,
                             "r1_status": "official", "r1_pairings": R1})
    pods, r1, _ = resolve_draw(TEAMS, good, require_r1=True)
    assert is_two_pod(pods) and len(r1) == 8
