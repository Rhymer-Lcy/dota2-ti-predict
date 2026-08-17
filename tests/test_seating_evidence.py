"""The four seeded Main Event participants must rest on one archived, hash-pinned client capture.

The saved Valve feed proves the bracket graph but carries no team ids in its Playoff nodes, so the
seating is the one load-bearing input it cannot verify. These tests police that gap: the bytes, the
transcription, the alias resolution, the provenance labels, and the fail-closed behaviour when any
of it is disturbed. They also assert that the superseded secondary-source evidence is really gone
from the current tree rather than lingering as dead weight.
"""
import copy
import json
import os

import pytest

from ti_predict import seating_evidence as se
from ti_predict import ti15_results as tr

REPO = se.REPO
EVIDENCE_DIR = os.path.join(REPO, "data", "ti2026", "inputs", "evidence", "main_event_seating")
CLIENT_PNG = ("data/ti2026/inputs/evidence/main_event_seating/"
              "ti15_main_event_bracket_client_crop_20260817.png")
FULL_CAPTURE_SHA = "3a3abff414059d56c6301cfd6fd12dfa81062990c89bf0fdff65a4f854ebfb52"


@pytest.fixture(scope="module")
def doc():
    return se.load_record()


def _write(tmp_path, doc, image=True):
    """Materialize a (possibly tampered) record plus its evidence dir, for fail-closed tests."""
    d = tmp_path / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    src = os.path.join(REPO, doc["image"]["path"])
    dst = d / os.path.basename(doc["image"]["path"])
    if image and os.path.exists(src):
        dst.write_bytes(open(src, "rb").read())
    doc["image"]["path"] = str(dst)          # absolute: tmp_path may be on another drive
    p = d / "ti15_main_event_seating.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p), str(d)


# ------------------------------------------------------------------ the archive
def test_exactly_one_seeded_participant_image_is_required(doc):
    assert isinstance(doc["image"], dict), "the record holds a single image, not a list"
    assert "images" not in doc, "the two-image schema is gone"
    on_disk = sorted(f for f in os.listdir(EVIDENCE_DIR) if not f.endswith(".json"))
    assert on_disk == [os.path.basename(CLIENT_PNG)], on_disk


def test_the_image_is_the_expected_client_crop(doc):
    assert doc["image"]["path"] == CLIENT_PNG
    assert os.path.exists(os.path.join(REPO, CLIENT_PNG))
    assert doc["image"]["transformation"] == "crop only"
    g = doc["image"]["crop_geometry"]
    assert g["source_pixels"] == [2048, 1152]
    assert g["box_left_upper_right_lower"] == [424, 0, 2048, 1000]
    assert doc["image"]["pixels"] == [1624, 1000]


def test_the_private_original_is_recorded_but_not_published(doc):
    """Its hash is kept so the excerpt's lineage stays checkable; its bytes are not republished."""
    assert doc["image"]["original_private_capture_sha256"] == FULL_CAPTURE_SHA
    assert doc["image"]["original_private_capture_bytes"] == 1212870
    for dirpath, _, names in os.walk(os.path.join(REPO, "data")):
        for n in names:
            p = os.path.join(dirpath, n)
            if n.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.getsize(p) == 1212870:
                assert se._sha256(p) != FULL_CAPTURE_SHA, f"the full capture is published at {p}"


def test_hash_and_byte_size_match_the_record(doc):
    p = os.path.join(REPO, doc["image"]["path"])
    assert se._sha256(p) == doc["image"]["sha256"]
    assert os.path.getsize(p) == doc["image"]["bytes"] == 427163


def test_archived_bytes_are_a_real_complete_png(doc):
    """Guards against a re-encoded, cropped, truncated or text-normalized archive."""
    b = open(os.path.join(REPO, doc["image"]["path"]), "rb").read()
    assert b[:8] == bytes.fromhex("89504e470d0a1a0a"), "not a PNG"
    assert b[-8:-4] == b"IEND", "truncated PNG"
    assert len(b) == doc["image"]["bytes"]
    assert doc["image"]["transformation"] == "crop only"


# ------------------------------------------------------------------ provenance
def test_source_is_first_party_in_client_with_no_url(doc):
    src = doc["source"]
    assert src["type"] == se.FIRST_PARTY == "first-party in-client capture, privacy-preserving crop"
    assert src["source_url"] is None
    assert src["acquisition_date"] == "2026-08-17"
    assert src["network_access_used"] is False
    assert "logged-in Dota 2 client" in src["description"]
    assert "privacy-preserving crop" in src["description"]


def test_seating_and_topology_provenance_are_kept_apart(doc):
    r = doc["provenance_roles"]
    assert "client screenshot" in r["seating_source"]
    assert "league feed" in r["topology_source"]
    assert "WHO" in r["seating_role"]
    assert "winner/loser edges" in r["topology_role"]
    assert "not used to derive the graph" in r["roles_are_separate"]


def test_no_secondary_source_provenance_survives_in_the_record(doc):
    """The superseded Weibo evidence must leave no trace in the current record."""
    blob = json.dumps(doc).lower()
    for gone in ("weibo", "secondary", "community reporting", "primary_source_verified",
                 "publisher", "schedule/list view", "bracket view"):
        assert gone not in blob, gone


def test_the_record_does_not_rewrite_where_the_model_input_came_from(doc):
    note = doc["evidence_strength"]["original_model_input_provenance"]
    assert "not a claim that the screenshot was the original source" in note


# ------------------------------------------------------------------ transcription
def test_transcription_covers_exactly_the_four_seeded_matches(doc):
    seats = doc["transcription"]["seats"]
    assert len(seats) == 4
    assert sorted(s["selection_id"] for s in seats) == [801, 802, 803, 804]
    assert sorted(s["node_id"] for s in seats) == [14, 15, 16, 17]
    assert all(s["best_of"] == 3 for s in seats)
    assert [s["client_block"] for s in sorted(seats, key=lambda x: x["selection_id"])] == \
        ["A", "B", "C", "D"]


def test_display_names_resolve_to_eight_unique_canonical_teams(doc):
    seats = doc["transcription"]["seats"]
    display = [t for s in seats for t in s["display"]]
    assert len(set(display)) == 8
    canon = [tr.canon(t) for t in display]
    assert len(set(canon)) == 8
    assert set(canon) == {tr.canon(t) for t in tr.FINAL_EIGHT}
    for s in seats:
        assert [tr.canon(t) for t in s["display"]] == list(s["canonical"])


def test_client_abbreviations_map_to_the_transcribed_display_names(doc):
    abbr = doc["transcription"]["abbreviations"]
    assert set(abbr) == {"IW", "TSpirit", "VSN", "BB", "Liquid", "TY", "NGX", "FLCN"}
    display = {t for s in doc["transcription"]["seats"] for t in s["display"]}
    assert set(abbr.values()) == display


def test_the_transcription_matches_the_committed_production_constant(doc):
    for s in doc["transcription"]["seats"]:
        assert tuple(tr.UBQF[s["node_id"]]) == tuple(s["display"]), s["selection_id"]


def test_production_runtime_does_not_depend_on_image_parsing(doc):
    assert "never OCR" in doc["transcription"]["runtime_contract"]


# ------------------------------------------------------------------ the gate
def test_verify_passes_on_the_real_evidence_and_the_real_seats():
    seats = {nid: (tr.canon(a), tr.canon(b)) for nid, (a, b) in tr.UBQF.items()}
    rep = se.verify(seats=seats)
    assert rep["production_seat_check"]["matches_evidence"]
    assert rep["source_type"] == se.FIRST_PARTY
    assert rep["source_url"] is None
    assert len(rep["seats"]) == 4
    assert rep["image"]["bytes"] == 427163


def test_altered_seating_fails_closed():
    seats = {nid: (tr.canon(a), tr.canon(b)) for nid, (a, b) in tr.UBQF.items()}
    seats[14] = ("Team Falcons", "Team Spirit")            # wrong team in the first quarterfinal
    with pytest.raises(SystemExit):
        se.verify(seats=seats)


def test_a_missing_node_in_production_seats_fails_closed():
    seats = {nid: (tr.canon(a), tr.canon(b)) for nid, (a, b) in tr.UBQF.items()}
    del seats[17]
    with pytest.raises(SystemExit):
        se.verify(seats=seats)


def test_a_wrong_recorded_hash_fails_closed(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["image"]["sha256"] = "0" * 64
    rec, ev = _write(tmp_path, bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_wrong_recorded_byte_count_fails_closed(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["image"]["bytes"] = 999
    rec, ev = _write(tmp_path / "b", bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_missing_evidence_file_fails_closed(tmp_path, doc):
    rec, ev = _write(tmp_path, copy.deepcopy(doc), image=False)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_tampered_transcription_fails_closed(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["transcription"]["seats"][2]["display"] = ["Team Liquid", "Team Spirit"]   # duplicate team
    rec, ev = _write(tmp_path, bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_downgrading_the_source_type_fails_closed(tmp_path, doc):
    """A future edit must not quietly swap the first-party capture for something weaker."""
    bad = copy.deepcopy(doc)
    bad["source"]["type"] = "secondary/community reporting source"
    rec, ev = _write(tmp_path, bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_smuggling_a_url_back_in_fails_closed(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["source"]["source_url"] = "https://example.invalid/whatever"
    rec, ev = _write(tmp_path / "c", bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_missing_record_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        se.verify(record_path=str(tmp_path / "absent.json"))


# ------------------------------------------------------------------ current-tree hygiene
def test_no_superseded_seating_evidence_remains_in_the_current_tree():
    gone = ("ti15_main_event_bracket_weibo_20260816.jpg",
            "ti15_main_event_schedule_weibo_20260816.jpg",
            "ti15_main_event_bracket_official_client_20260817.png")
    root = os.path.join(REPO, "data")
    for dirpath, _, names in os.walk(root):
        for n in names:
            assert n not in gone, os.path.join(dirpath, n)


def test_the_seating_directory_holds_exactly_one_image_and_one_record():
    listing = sorted(os.listdir(EVIDENCE_DIR))
    imgs = [f for f in listing if f.lower().endswith(se.IMAGE_SUFFIXES)]
    recs = [f for f in listing if f.lower().endswith(".json")]
    assert len(imgs) == 1 and len(recs) == 1, listing
    assert listing == sorted(imgs + recs), "no stray files in the seating evidence directory"


def test_a_second_seating_image_fails_closed_at_runtime(tmp_path, doc):
    """Finding #2: this invariant is enforced by production code, not only by tests."""
    rec, ev = _write(tmp_path, copy.deepcopy(doc))
    import shutil
    shutil.copy(os.path.join(ev, os.path.basename(CLIENT_PNG)),
                os.path.join(ev, "an_extra_capture.png"))
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_stray_non_evidence_file_fails_closed(tmp_path, doc):
    rec, ev = _write(tmp_path / "s", copy.deepcopy(doc))
    open(os.path.join(ev, "notes.txt"), "w").write("stray")
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_a_non_crop_transformation_fails_closed(tmp_path, doc):
    bad = copy.deepcopy(doc)
    bad["image"]["transformation"] = "crop and redact"
    rec, ev = _write(tmp_path / "t", bad)
    with pytest.raises(SystemExit):
        se.verify(record_path=rec, evidence_dir=ev)


def test_the_seat_table_is_derived_not_independently_typed():
    """Finding #3: exactly one declarative seat table exists, and UBQF is mechanically derived."""
    seats = {s["node_id"]: tuple(s["display"]) for s in
             se.load_record()["transcription"]["seats"]}
    assert tr.UBQF == seats
    assert tr.UBQF == tr.opening_seats()
    src = open(os.path.join(REPO, "ti_predict", "ti15_results.py"), encoding="utf-8").read()
    assert "UBQF = opening_seats()" in src
    # No module-level literal may map node ids to pairs -- that would be a second seat table.
    # FINAL_EIGHT is deliberately NOT caught here: it is the survivor list reconstructed from the
    # Swiss results, an independent fact whose agreement with the seating is the real cross-check.
    import ast
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, int)]
            assert not set(keys) & set(se.EXPECTED_NODES),                 f"a node-keyed seat literal reappeared at line {node.lineno}"


def test_the_declared_trust_boundary_is_stated_not_overclaimed(doc):
    t = doc["transcription"]["trust_boundary"]
    assert "cannot be eliminated cryptographically" in t
    assert "not that the review read it correctly" in t
    assert "ONLY declarative table" in doc["transcription"]["single_source_of_seats"]


def test_no_secondary_source_reference_remains_in_seating_provenance():
    """Scoped to SEATING provenance, not a repo-wide ban on the word.

    `data/ti2026/inputs/roster_events.csv` and `fantasy/roster_positions.csv` legitimately cite
    `lgd-official-weibo` as one source of the LGD position-2 roster change. That is a different
    fact with its own genuine provenance and must not be collateral damage here.
    """
    targets = [os.path.join(REPO, "ti_predict", "seating_evidence.py"),
               os.path.join(REPO, "README.md"),
               os.path.join(REPO, "docs", "CHECKPOINT.md")]
    targets += [os.path.join(EVIDENCE_DIR, f) for f in os.listdir(EVIDENCE_DIR)
                if f.endswith(".json")]
    hits = []
    for p in targets:
        txt = open(p, encoding="utf-8").read().lower()
        for term in ("weibo", "secondary/community", "primary_source_verified"):
            if term in txt:
                hits.append((os.path.relpath(p, REPO), term))
    assert not hits, f"stale secondary-source seating provenance: {hits}"


def test_the_unrelated_roster_source_tag_is_deliberately_untouched():
    """Proves the cleanup was surgical: a real, different citation still stands."""
    p = os.path.join(REPO, "data", "ti2026", "inputs", "roster_events.csv")
    assert "lgd-official-weibo" in open(p, encoding="utf-8").read()


# ------------------------------------------------------------------ display names
def test_display_map_covers_the_three_renamed_organizations():
    d = se.display_names()
    assert d["Tundra Esports"] == "Iron Wing"
    assert d["PARIVISION"] == "TEAM VISION"
    assert d["BetBoom Team"] == "BoomBoys"
    assert len(d) == 8
    for canon, disp in d.items():
        assert tr.canon(disp) == canon
