"""Fail-closed gate on the four seeded Main Event participants.

The saved Valve league feed proves the bracket GRAPH: fourteen nodes and their winner/loser edges.
It cannot prove WHO sits in the four seeded slots, because every Playoff node in that snapshot
carries team_id_1 = team_id_2 = 0. So the seating would otherwise be a naked hand-entered constant
(`ti15_results.UBQF`) behind a load-bearing input. That is the gap this closes, and the two
provenance roles stay separate: the feed answers the graph, the screenshot answers the seating.

The evidence is one archived first-party capture -- a privacy-preserving CROP of an operator
screenshot of the logged-in Dota 2 client's Match Predictions page -- plus a reviewed transcription,
both living alone in data/ti2026/inputs/evidence/main_event_seating/. The uncropped original is
deliberately absent: it carried the operator's persona, a friend's name and account statistics, none
of which is evidence for anything claimed here.

The reviewed transcription is also the SINGLE declarative table of opening participants:
ti15_results.UBQF is derived from it, so there is no second hand-maintained seat table. That makes
the seat-equality check below a check on the PIPELINE PATH (what production is about to enumerate is
what the evidence says) rather than two independent tables agreeing -- stated plainly rather than
overclaimed.

TRUST BOUNDARY, declared: human review of the capture-to-transcription step. Runtime OCR is
intentionally excluded, so that step cannot be closed cryptographically. The hash proves the image
has not changed since it was reviewed -- not that the review read it correctly -- and any future
change to the image invalidates the gate until a human re-reviews it.

The runtime contract is deliberately NOT image parsing. OCR at production time would be a fragile
dependency that could drift silently; instead the contract is:

    immutable screenshot bytes (sha256- and size-pinned)
      + reviewed transcription
      + seat equality against what production is about to enumerate

Any mismatch aborts before a single probability is computed.

Run: python -m ti_predict.seating_evidence
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE_DIR = os.path.join(REPO, "data", "ti2026", "inputs", "evidence", "main_event_seating")
RECORD = os.path.join(EVIDENCE_DIR, "ti15_main_event_seating.json")
EXPECTED_SELECTIONS = (801, 802, 803, 804)
EXPECTED_NODES = (14, 15, 16, 17)
FIRST_PARTY = "first-party in-client capture, privacy-preserving crop"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_record(path=None):
    """Read the evidence record, or exit with a reason it cannot be trusted."""
    path = path or RECORD
    if not os.path.exists(path):
        raise SystemExit(f"seating evidence record not found: {path}\nThe four seeded Main Event "
                         "participants are not derivable from the saved Valve feed (its Playoff "
                         "nodes carry no team ids), so production cannot proceed without it.")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"seating evidence record unreadable: {e}")


def verify(seats=None, record_path=None, evidence_dir=None):
    """Verify the archived evidence and, if `seats` is given, that production matches it.

    `seats` is {node_id: (canonicalA, canonicalB)} -- exactly what the caller is about to pass to
    bracket.enumerate_structure. Returns a manifest-ready dict. Raises SystemExit on any problem.
    """
    from ti_predict import ti15_results as tr
    doc = load_record(record_path)
    base = evidence_dir or EVIDENCE_DIR
    problems = []

    # 0. the dedicated seating directory holds exactly one record and exactly one image. Enforced
    #    here, in production, not only in tests: a stray second capture would leave a reviewer
    #    guessing which one the transcription describes.
    try:
        listing = sorted(os.listdir(base))
    except OSError as e:
        raise SystemExit(f"seating evidence directory unreadable: {e}")
    imgs = [f for f in listing if f.lower().endswith(IMAGE_SUFFIXES)]
    recs = [f for f in listing if f.lower().endswith(".json")]
    if len(imgs) != 1:
        problems.append(f"expected exactly one seating image in {base}, found {len(imgs)}: {imgs}")
    if len(recs) != 1:
        problems.append(f"expected exactly one seating record in {base}, found {len(recs)}: {recs}")
    stray = [f for f in listing if f not in imgs + recs]
    if stray:
        problems.append(f"unexpected files in the seating evidence directory: {stray}")

    src = doc.get("source") or {}
    if src.get("type") != FIRST_PARTY:
        problems.append(f"source.type must be {FIRST_PARTY!r}, found {src.get('type')!r}")
    if src.get("source_url") is not None:
        problems.append("source.source_url must be null for an in-client capture")
    if src.get("network_access_used") is not False:
        problems.append("source.network_access_used must be false")

    # 1. the single archived image still exists, sits in the evidence directory, and is byte-exact
    img = doc.get("image") or {}
    shot = None
    if not img:
        problems.append("the record carries no image block")
    else:
        p = img["path"] if os.path.isabs(img["path"]) else os.path.join(REPO, img["path"])
        if os.path.dirname(os.path.abspath(p)) != os.path.abspath(base):
            problems.append(f"{img['path']} is outside the evidence directory")
        if not os.path.exists(p):
            problems.append(f"archived evidence missing: {img['path']}")
        else:
            size, got = os.path.getsize(p), _sha256(p)
            if size != img.get("bytes"):
                problems.append(f"{img['path']} is {size} bytes, recorded {img.get('bytes')}")
            if got != img.get("sha256"):
                problems.append(f"{img['path']} sha256 {got} != recorded {img.get('sha256')} "
                                "(the archived bytes changed; this is no longer the captured file)")
            if imgs and os.path.basename(p) != imgs[0]:
                problems.append(f"the record names {os.path.basename(p)} but the directory holds "
                                f"{imgs[0]}")
            shot = {"path": img["path"], "sha256": got, "bytes": size,
                    "pixels": img.get("pixels"),
                    "transformation": img.get("transformation"),
                    "crop_geometry": img.get("crop_geometry"),
                    "original_private_capture_sha256": img.get("original_private_capture_sha256"),
                    "original_is_deliberately_not_in_this_repository":
                        img.get("original_is_deliberately_not_in_this_repository")}

    if img and img.get("transformation") != "crop only":
        problems.append("image.transformation must be 'crop only'; redaction or repainting would "
                        "make the capture no longer a faithful excerpt")
    if img and not img.get("original_private_capture_sha256"):
        problems.append("image.original_private_capture_sha256 must record the private original")

    # 2. the transcription is structurally complete
    trs = (doc.get("transcription") or {}).get("seats") or []
    if len(trs) != 4:
        problems.append(f"transcription must hold exactly 4 seeded matches, found {len(trs)}")
    if sorted(s["selection_id"] for s in trs) != list(EXPECTED_SELECTIONS):
        problems.append(f"selection ids must be {list(EXPECTED_SELECTIONS)}")
    if sorted(s["node_id"] for s in trs) != list(EXPECTED_NODES):
        problems.append(f"node ids must be {list(EXPECTED_NODES)}")
    display = [t for s in trs for t in s["display"]]
    if len(set(display)) != 8:
        problems.append(f"the eight display participants must be distinct, found {len(set(display))}")

    # 3. display names resolve to eight unique canonical organizations, matching the record
    canon = []
    for s in trs:
        try:
            got = [tr.canon(t) for t in s["display"]]
        except KeyError as e:
            problems.append(f"selection {s['selection_id']}: unresolvable display name {e}")
            continue
        if got != list(s["canonical"]):
            problems.append(f"selection {s['selection_id']}: alias resolution {got} disagrees with "
                            f"the recorded canonical {s['canonical']}")
        canon += got
    if len(set(canon)) != 8:
        problems.append(f"canonical resolution must give 8 unique organizations, got {len(set(canon))}")

    # 4. the seats production is about to use are exactly the transcribed ones
    seat_check = None
    if seats is not None:
        want = {s["node_id"]: tuple(s["canonical"]) for s in trs}
        got = {int(n): tuple(p) for n, p in seats.items()}
        if set(got) != set(want):
            problems.append(f"production seats cover nodes {sorted(got)}, evidence {sorted(want)}")
        else:
            bad = {n: (got[n], want[n]) for n in want if got[n] != want[n]}
            if bad:
                problems.append(f"production seating disagrees with the evidence: {bad}")
        seat_check = {"nodes_checked": sorted(want), "matches_evidence": not problems}

    if problems:
        raise SystemExit("SEATING EVIDENCE GATE FAILED:\n  - " + "\n  - ".join(problems))

    roles = doc["provenance_roles"]
    return {
        "gate": "seeded Main Event participants verified against archived first-party evidence",
        "evidence_record": os.path.relpath(record_path or RECORD, REPO).replace("\\", "/"),
        "image": shot,
        "source_type": src["type"],
        "source_description": src["description"],
        "source_url": None,
        "acquisition_date": src["acquisition_date"],
        "evidence_scope": doc["evidence_scope"],
        "seating_source": roles["seating_source"],
        "topology_source": roles["topology_source"],
        "roles_are_separate": roles["roles_are_separate"],
        "runtime_contract": doc["transcription"]["runtime_contract"],
        "trust_boundary": doc["transcription"]["trust_boundary"],
        "single_source_of_seats": doc["transcription"]["single_source_of_seats"],
        "directory_contents": {"images": imgs, "records": recs},
        "seats": [{"selection_id": s["selection_id"], "node_id": s["node_id"],
                   "client_block": s["client_block"], "client_date": s["client_date"],
                   "display": list(s["display"]),
                   "canonical": list(s["canonical"])} for s in trs],
        "production_seat_check": seat_check,
        "evidence_strength": doc["evidence_strength"]["statement"],
        "original_model_input_provenance":
            doc["evidence_strength"]["original_model_input_provenance"],
    }


def display_names(record_path=None):
    """{canonical organization: client-facing display name}, taken from the evidence itself.

    The client shows TI-branded names; the model works in canonical organizations. Deriving the map
    from the archived transcription keeps the two in step instead of re-typing a third copy.
    """
    doc = load_record(record_path)
    out = {}
    for s in doc["transcription"]["seats"]:
        for disp, can in zip(s["display"], s["canonical"]):
            out[can] = disp
    return out


def main():
    rep = verify()
    print("seating evidence gate: PASS")
    print(f"  record   : {rep['evidence_record']}")
    print(f"  source   : {rep['source_type']} ({rep['source_description']})")
    print(f"  url      : {rep['source_url']}   acquired {rep['acquisition_date']}")
    i = rep["image"]
    print(f"  image    : {i['path']}")
    print(f"             sha256 {i['sha256']}  ({i['bytes']} bytes, {i['transformation']})")
    print(f"  seating  : {rep['seating_source']}")
    print(f"  topology : {rep['topology_source']}")
    print("  transcribed seating:")
    for s in rep["seats"]:
        print(f"    {s['selection_id']} / node {s['node_id']} "
              f"[{s['client_date']} block {s['client_block']}]: "
              f"{s['display'][0]} vs {s['display'][1]}  ->  "
              f"{s['canonical'][0]} vs {s['canonical'][1]}")
    print("  display map   : " + ", ".join(f"{k} -> {v}" for k, v in display_names().items()
                                           if k != v))


if __name__ == "__main__":
    main()
