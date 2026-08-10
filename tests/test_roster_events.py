"""The lock-period roster audit: structured provenance, and no silent resolution of a conflict."""
import pytest

from ti_predict.predict_ti15 import load_teams
from ti_predict.rosters import ROSTER_EVENTS_CSV, load_roster_events, roster_audit

ORGS = [t["team"] for t in load_teams()]


def _write(tmp_path, rows, header=None):
    header = header or ("organization,status,role,outgoing_player,outgoing_account_id,"
                        "incoming_player,incoming_account_id,reason_category,eligibility,"
                        "announced_utc,effective_status,evidence_tier,source,retrieved_at,note")
    p = tmp_path / "roster_events.csv"
    p.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
    return str(p)


def test_table_covers_exactly_the_sixteen():
    ev = load_roster_events(ROSTER_EVENTS_CSV, orgs=ORGS)
    assert sorted(ev) == sorted(ORGS)


def test_lgd_change_is_recorded_with_full_provenance():
    """TaiLung out (ineligible), Topson in at position 2 -- with numeric account ids on both."""
    r = load_roster_events(ROSTER_EVENTS_CSV)["LGD Gaming"]
    assert r["status"] == "CHANGED"
    assert r["outgoing_player"] == "TaiLung" and r["outgoing_account_id"] == "1026694469"
    assert r["incoming_player"] == "Topson" and r["incoming_account_id"] == "94054712"
    assert r["role"] == "2"
    assert "integrity" in r["reason_category"]
    assert r["evidence_tier"] == "1"
    assert r["announced_utc"].endswith("Z") and r["source"]


def test_audit_summary_lists_the_change_and_nothing_blocking():
    a = roster_audit(orgs=ORGS)
    assert a["teams_audited"] == 16
    assert [c["organization"] for c in a["changed"]] == ["LGD Gaming"]
    assert a["blocking"] == []


def test_changed_row_without_provenance_is_rejected(tmp_path):
    p = _write(tmp_path, ["Some Org,CHANGED,,,,,,,,,,,,,"])
    with pytest.raises(SystemExit, match="CHANGED but missing"):
        load_roster_events(p)


def test_account_id_must_be_numeric_never_inferred_from_a_nickname(tmp_path):
    p = _write(tmp_path, ["Some Org,CHANGED,2,Old,111,New,Topson,ban,ineligible,"
                          "2026-08-09T05:20:00Z,active,1,src,2026-08-10,"])
    with pytest.raises(SystemExit, match="numeric account id"):
        load_roster_events(p)


def test_unknown_status_is_rejected(tmp_path):
    p = _write(tmp_path, ["Some Org,PROBABLY-FINE,,,,,,,,,,,,,"])
    with pytest.raises(SystemExit, match="expected one of"):
        load_roster_events(p)


def test_conflict_and_unresolved_are_blocking(tmp_path):
    p = _write(tmp_path, ["Org A,CONFLICT,,,,,,,,,,,,,", "Org B,UNRESOLVED,,,,,,,,,,,,,",
                          "Org C,CONFIRMED,,,,,,,,,,,,,"])
    a = roster_audit(p)
    assert a["blocking"] == ["Org A", "Org B"]


def test_official_run_blocks_on_a_conflicting_roster(tmp_path, monkeypatch):
    """A source conflict must never be silently decided in favour of whichever lineup is modelled."""
    import ti_predict.rosters as rosters
    rows = [f"{o},CONFIRMED,,,,,,,,,,,,," for o in ORGS[:-1]]
    rows.append(f"{ORGS[-1]},CONFLICT,,,,,,,,,,,,,")
    p = _write(tmp_path, rows)
    monkeypatch.setattr(rosters, "ROSTER_EVENTS_CSV", p)
    a = rosters.roster_audit(orgs=ORGS)
    assert a["blocking"] == [ORGS[-1]]
