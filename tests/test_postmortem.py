"""The post-event archive must stay honest about chronology, provenance and privacy.

Three properties are worth more than the rest and are what most of this file defends:

  the official result is COMPUTED, never copied. Mutating the outcome archive must move it.
  post-event truth cannot reach a TI2026 fit, by namespace, by document marker and by row marker.
  no identity from the private captures appears anywhere in tracked content.

The first-party settlement is used as an independent cross-check of a derived number, which is only
worth something as long as the number really is derived - so there is a test that breaks if anyone
ever short-circuits it to a constant.
"""
import copy
import hashlib
import json
import os
import subprocess

import pytest

from ti_predict import bracket as bk
from ti_predict import chronology as ch
from ti_predict import postmortem as pm
from ti_predict import ti15_results as tr

REPO = pm.REPO

# The submitted slate is historical evidence. These pin the bytes every number in the postmortem
# was derived from; if they change, the postmortem is describing a different artifact.
#
# The hash is taken over NEWLINE-NORMALIZED content on purpose. `.gitattributes` sets `* text=auto`,
# so this file is stored with LF and checked out with CRLF on Windows: a raw working-tree hash would
# be checkout-dependent and would fail on a Linux clone of the identical commit. The git blob id is
# pinned alongside it as the checkout-independent object identity.
PREDICTION_SHA256_NORMALIZED = "d1126cfb6528389e7f9c21de693f166f37cd1f1057c8faf43389e9fed401ebfd"
PREDICTION_BLOB_ID = "690c2dd46c50dc159aeb8367b0d25e992d19d465"

OFFICIAL_CORRECT = 8
OFFICIAL_INCORRECT = 6
OFFICIAL_SCORE = 4320
CHAMPION = "Team Spirit"


# Needles are ASSEMBLED FROM FRAGMENTS on purpose. Written out, this file would itself contain every
# string it forbids, the repository-wide scan would flag it, and the invariant would be weaker for
# it: a guard list should not be an instance of the thing it guards against.
DRIVE = "F:"
PRIVATE_DIR_SUFFIX = "-evidence" + "-private"


def _identity_needles():
    # built from codepoints, not written out: the source file stays pure ASCII and does not itself
    # contain either display name
    return ["Alice in " + "Chains", "".join(map(chr, (0x5343, 0x4E28, 0x57CE)))]


def _leak_needles():
    return _identity_needles() + [
        "steam" + "id", "STEAM" + "_",
        DRIVE + chr(92), DRIVE + "/",
        "dota2-ti-predict" + PRIVATE_DIR_SUFFIX,
    ]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("git is unavailable")
    return [p for p in out.stdout.splitlines() if p]


@pytest.fixture(scope="module")
def outcomes():
    return pm.load_outcomes()


@pytest.fixture(scope="module")
def art():
    return pm.load_prediction()


@pytest.fixture(scope="module")
def evaluation():
    return pm.build()


# --------------------------------------------------------------------------- 1-2 the archive
def test_archive_holds_exactly_14_coherent_nodes(outcomes):
    assert len(outcomes["series"]) == 14
    rec = pm.reconcile(outcomes)
    assert len(rec["winner"]) == 14
    shape = {}
    for nid in rec["topo"]["order"]:
        lab = rec["topo"]["label"][nid]
        shape[lab] = shape.get(lab, 0) + 1
    assert shape == bk.EXPECTED_SHAPE
    assert sorted(s["selection_id"] for s in outcomes["series"]) == list(range(801, 815))


def test_every_series_clinches_its_declared_best_of(outcomes):
    topo = bk.load_topology()
    for s in outcomes["series"]:
        need = (topo["best_of"][s["node_id"]] + 1) // 2
        assert s["series_score"]["winner_maps"] == need
        assert s["series_score"]["loser_maps"] < need
    gf = [s for s in outcomes["series"] if s["round"] == "GF"]
    assert len(gf) == 1 and gf[0]["best_of"] == 5
    assert all(s["best_of"] == 3 for s in outcomes["series"] if s["round"] != "GF")


def test_champion_resolves_to_team_spirit(outcomes):
    rec = pm.reconcile(outcomes)
    assert rec["winner"][rec["topo"]["gf"]] == CHAMPION
    assert outcomes["champion"] == CHAMPION


def test_incoherent_archive_fails_closed(outcomes):
    bad = copy.deepcopy(outcomes)
    bad["series"][0]["winner"], bad["series"][0]["loser"] = (
        bad["series"][0]["loser"], bad["series"][0]["winner"])
    with pytest.raises(SystemExit):
        pm.reconcile(bad)


def test_a_missing_series_fails_closed(outcomes, tmp_path):
    bad = copy.deepcopy(outcomes)
    bad["series"] = bad["series"][:-1]
    with pytest.raises(SystemExit):
        pm.reconcile(bad)
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit):
        pm.load_outcomes(str(path))


def test_an_unmarked_outcome_file_is_refused(outcomes, tmp_path):
    """An outcome archive that does not declare itself post-event is exactly what leaks later."""
    bad = copy.deepcopy(outcomes)
    for k in ("post_event_only", "observed_after_prediction"):
        bad.pop(k, None)
    bad["phase"] = "pre_event"
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit):
        pm.load_outcomes(str(path))


# --------------------------------------------------------------------------- 3-4 provenance of the slate
def test_selections_come_from_the_frozen_artifact(art, evaluation):
    slate = pm.submitted_slate(art)
    assert len(slate) == 14
    for n in evaluation["official_evaluation"]["nodes"]:
        assert n["submitted_pick"] == slate[n["selection_id"]]
    src = open(os.path.join(REPO, "ti_predict", "postmortem.py"), encoding="utf-8").read()
    for team in ("Nigma Galaxy", "PARIVISION", "BetBoom Team", "Team Falcons"):
        assert f'"{team}"' not in src, "the evaluator must not carry a second copy of the slate"


def test_node_correctness_is_computed_not_hard_coded(art, outcomes):
    """Flip one realized winner: the official count must move. A constant would not."""
    base = pm.evaluate_official(art, pm.reconcile(outcomes))
    assert base["official_correct"] == OFFICIAL_CORRECT

    # Flip the Grand Final: it is terminal, so the archive stays a coherent bracket and the only
    # thing that can move is the computed result. Flipping an earlier node would instead break
    # propagation, which reconcile already refuses (see test_incoherent_archive_fails_closed).
    mutated = copy.deepcopy(outcomes)
    gf = next(s for s in mutated["series"] if s["round"] == "GF")
    gf["winner"], gf["loser"] = gf["loser"], gf["winner"]
    mutated["champion"], mutated["runner_up"] = gf["winner"], gf["loser"]
    moved = pm.evaluate_official(art, pm.reconcile(mutated))
    assert moved["official_correct"] == base["official_correct"] + 1
    assert moved["official_score"] > base["official_score"]


# --------------------------------------------------------------------------- 5-7 the official result
def test_computed_official_counts_and_score(evaluation):
    ev = evaluation["official_evaluation"]
    assert ev["official_correct"] == OFFICIAL_CORRECT
    assert ev["official_incorrect"] == OFFICIAL_INCORRECT
    assert ev["total_nodes"] == 14
    assert ev["official_score"] == OFFICIAL_SCORE
    assert ev["official_score"] == ev["scoring_vector"][ev["official_correct"]]


def test_scoring_vector_is_the_committed_one(evaluation):
    assert evaluation["official_evaluation"]["scoring_vector"] == \
        bk.verify_scoring_vector()["vector"]


# --------------------------------------------------------------------------- 8-9 client semantics
def test_matches_the_first_party_settlement(evaluation):
    x = evaluation["first_party_settlement_cross_check"]
    assert x["client_correct"] == x["derived_correct"] == OFFICIAL_CORRECT
    assert x["client_incorrect"] == x["derived_incorrect"] == OFFICIAL_INCORRECT
    assert x["aggregate_agrees"] and x["per_node_agrees"]
    assert x["per_node_marks_checked"] == 14
    assert x["source_tier"] == 1


def test_settlement_mismatch_is_a_hard_failure(art, outcomes, tmp_path):
    """A disagreement with the client must abort, not be reported as a discrepancy field."""
    ev = pm.evaluate_official(art, pm.reconcile(outcomes))
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    for e in idx["evidence"]:
        t = e.get("public_safe_transcription", {})
        if "main_event_prediction_settlement" in t:
            t["main_event_prediction_settlement"]["correct_predictions"] = 9
    bad = tmp_path / "index.json"
    bad.write_text(json.dumps(idx), encoding="utf-8")
    with pytest.raises(SystemExit):
        pm.cross_check_settlement(ev, str(bad))


def test_scoring_uses_node_winner_semantics(evaluation):
    """Credit follows the realized node winner, not the realized participant pair."""
    ev = evaluation["official_evaluation"]
    for n in ev["nodes"]:
        assert n["official_credit"] == (n["submitted_pick"] == n["realized_winner"])
    diverged = [n for n in ev["nodes"]
                if n["official_credit"] and not n["matchup_as_predicted"]]
    assert diverged, "the node-winner rule must be observably different from exact-path scoring"


# --------------------------------------------------------------------------- 10 diagnostics stay subordinate
def test_path_diagnostics_cannot_override_official_scoring(evaluation):
    ev = evaluation["official_evaluation"]
    d = evaluation["exact_matchup_diagnostic"]
    assert d["status"] == "DIAGNOSTIC ONLY"
    assert d["is_the_official_rule"] is False
    assert d["hypothetical_correct"] != ev["official_correct"]
    assert ev["official_score"] == ev["scoring_vector"][ev["official_correct"]]
    counts = ev["taxonomy_counts"]
    assert sum(counts.values()) == 14
    assert sum(counts[k] for k in pm.CORRECT_TAGS) == ev["official_correct"]


# --------------------------------------------------------------------------- 11 the chronology boundary
def test_post_event_paths_are_rejected_as_production_inputs():
    for p in ("data/ti2026/outcomes/main_event_results.json",
              "data/ti2026/outcomes/sources.json",
              "predictions/ti2026/postmortem/bracket_evaluation.json",
              "predictions/ti2026/postmortem/ti2026_postmortem.json"):
        assert ch.is_post_event_path(os.path.join(REPO, p))
        with pytest.raises(SystemExit):
            ch.assert_production_input(os.path.join(REPO, p))
    for p in ("data/ti2026/inputs/teams.csv",
              "predictions/ti2026/playoffs/ti15_main_event_prediction.json"):
        assert not ch.is_post_event_path(os.path.join(REPO, p))
        ch.assert_production_input(os.path.join(REPO, p))


def test_post_event_documents_and_rows_are_rejected():
    for name in ("main_event_results.json", "sources.json"):
        doc = json.load(open(os.path.join(REPO, "data", "ti2026", "outcomes", name),
                             encoding="utf-8"))
        assert ch.is_post_event_document(doc)
        with pytest.raises(SystemExit):
            ch.assert_production_document(doc)
    with pytest.raises(SystemExit):
        ch.assert_production_rows([{"start_time": 1, "phase": "post_event"}])
    ch.assert_production_rows([{"start_time": 1, "side_provenance": tr.SIDE_RADIANT_DIRE}])


def test_main_event_result_rows_carry_the_post_event_marker(outcomes):
    rows = pm.main_event_rows(outcomes)
    assert rows and all(r["phase"] == "post_event" for r in rows)
    with pytest.raises(SystemExit):
        ch.assert_production_rows(rows)


def test_production_modules_do_not_reference_the_post_event_namespace():
    """Structural proof: no production module can construct a post-event path or import the evaluator.

    The needle is the full namespace path, not the bare word: 'outcomes' is an ordinary dict key in
    several modules, meaning 'possible results of a node', and has nothing to do with the archive.
    """
    allowed = {"postmortem.py", "chronology.py", "ti2026_record.py"}
    needles = [d for d in ch.POST_EVENT_DIRS]
    needles += [d.replace("/", os.sep) for d in ch.POST_EVENT_DIRS]
    needles += ["from ti_predict import postmortem", "ti_predict.postmortem",
                "from ti_predict import ti2026_record"]
    offenders = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "ti_predict")):
        if "__pycache__" in root:
            continue
        for f in files:
            if not f.endswith(".py") or f in allowed:
                continue
            src = open(os.path.join(root, f), encoding="utf-8").read()
            for n in needles:
                if n in src:
                    offenders.append((f, n))
    assert not offenders, f"production modules reference post-event namespaces: {offenders}"


# --------------------------------------------------------------------------- reproducible from a clone
def test_the_bracket_topology_source_is_tracked_and_is_the_one_production_used():
    """The saved Valve feed must be in the repository, and be the exact bytes production hashed.

    It is the sole source of the 14-node topology, it is a snapshot of a feed for a tournament that
    is now over - so it is not regenerable - and without it neither the main-event pipeline nor this
    evaluation can run from a clone. Pinning it to the hash the frozen artifact recorded also makes
    it impossible to swap the topology out from under the postmortem.
    """
    rel = "data/ti2026/raw/league_19719_feed.json"
    assert rel in _tracked(), "the league feed must be tracked, not git-ignored"
    art = pm.load_prediction()
    assert _sha256(os.path.join(REPO, rel)) == art["manifest"]["provenance"]["league_feed_sha256"]


def test_the_evaluation_reads_only_tracked_inputs():
    """No part of the evaluation may depend on a git-ignored file."""
    tracked = set(_tracked())
    for path in (pm.PREDICTION, pm.OUTCOMES, pm.SETTLEMENT, pm.FROZEN_STATE,
                 bk.FEED_JSON, tr.SEATING_EVIDENCE,
                 os.path.join(REPO, "data", "ti2026", "inputs", "prediction_questions.json")):
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        assert rel in tracked, f"the evaluation reads {rel}, which is not tracked"


# --------------------------------------------------------------------------- 12 immutability
def test_frozen_prediction_artifact_is_unchanged():
    raw = open(pm.PREDICTION, "rb").read()
    normalized = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    assert normalized == PREDICTION_SHA256_NORMALIZED


def test_frozen_prediction_artifact_matches_its_committed_blob():
    rel = os.path.relpath(pm.PREDICTION, REPO).replace("\\", "/")
    blob = subprocess.run(["git", "rev-parse", f"HEAD:{rel}"],
                          cwd=REPO, capture_output=True, text=True)
    if blob.returncode != 0:
        pytest.skip("git history unavailable")
    assert blob.stdout.strip() == PREDICTION_BLOB_ID, \
        "the committed prediction artifact is not the one this postmortem describes"
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=REPO)
    assert clean.returncode == 0, \
        "the working-tree prediction artifact differs from the commit that filed it"


def test_the_postmortem_never_writes_into_the_pre_event_namespace():
    """Every output path the evaluator can write to lives in the post-event namespace."""
    for target in (pm.EVALUATION, pm.FROZEN_STATE,
                   os.path.join(pm.POSTMORTEM_DIR, "ti2026_postmortem.json"),
                   os.path.join(pm.POSTMORTEM_DIR, "sequential_posthoc.json")):
        assert ch.is_post_event_path(target)


# --------------------------------------------------------------------------- 13 frozen-only probabilities
def test_probabilistic_evaluator_uses_only_pre_event_state(evaluation, outcomes):
    prob = evaluation["probabilistic_review"]
    assert prob["sequential_updating_used"] is False
    assert "POINT ESTIMATE" in prob["estimator"]

    state = json.load(open(pm.FROZEN_STATE, encoding="utf-8"))
    assert state["content_phase"] == "pre_event"
    assert state["reproduction"]["cutoff"].startswith("2026-08-16")
    cutoff = 1786968000  # 2026-08-16T12:00:00Z, the frozen serve cutoff
    first = min(s["start_time_epoch"] for s in outcomes["series"])
    assert cutoff < first, "the frozen state must predate every Main Event series"

    strength, c, _ = pm.load_frozen_state()
    for r in prob["series"]:
        w, l = r["realized_matchup"]
        assert r["p_pre_event_actual_winner"] == pytest.approx(
            pm.frozen_series_prob(w, l, r["best_of"], strength, c), abs=1e-15)


def test_frozen_state_reproduces_the_artifacts_stored_probabilities(art):
    strength, c, state = pm.load_frozen_state()
    assert state["verification"]["passed"] is True
    worst = 0.0
    for s in art["primary_slate"]:
        p = pm.frozen_series_prob(s["pick"], s["opponent"], s["best_of"], strength, c)
        worst = max(worst, abs(p - s["conditional_win_prob"]))
    assert worst <= 1e-12


# --------------------------------------------------------------------------- 14 identity
def test_aliases_resolve_consistently(outcomes):
    for s in outcomes["series"]:
        canon = {tr.canon(d) for d in s["participants_source_display"]}
        assert canon == set(s["participants_canonical"])
        assert s["winner"] in canon and s["loser"] in canon
    seated = {t for pair_ in tr.UBQF.values() for t in map(tr.canon, pair_)}
    played = {t for s in outcomes["series"] for t in s["participants_canonical"]}
    assert played == seated and len(seated) == 8
    with pytest.raises(KeyError):
        tr.canon("Not A Real Organisation")


# --------------------------------------------------------------------------- 15 determinism
def test_evaluation_is_deterministic():
    a = json.dumps(pm.build(), sort_keys=True)
    b = json.dumps(pm.build(), sort_keys=True)
    assert a == b


def test_filed_artifacts_match_a_fresh_run():
    fresh = pm.build()
    filed = json.load(open(pm.EVALUATION, encoding="utf-8"))
    assert json.dumps(fresh, sort_keys=True) == json.dumps(filed, sort_keys=True)
    fresh_pm = pm.build_postmortem(fresh)
    filed_pm = json.load(open(os.path.join(pm.POSTMORTEM_DIR, "ti2026_postmortem.json"),
                              encoding="utf-8"))
    assert json.dumps(fresh_pm, sort_keys=True) == json.dumps(filed_pm, sort_keys=True)


# --------------------------------------------------------------------------- 16-18 evidence & privacy
def test_no_raw_private_screenshot_is_tracked():
    tracked = _tracked()
    for p in tracked:
        low = p.lower()
        assert PRIVATE_DIR_SUFFIX not in low
        assert "evidence_local/" not in low
        assert "_full_private" not in low
        # a UUID-named upload must never be committed
        stem = os.path.basename(low).rsplit(".", 1)[0]
        parts = stem.split("-")
        assert not (len(parts) == 5 and len(parts[0]) == 8 and len(stem) == 36), p
    images = [p for p in tracked if p.lower().endswith((".png", ".jpg", ".jpeg"))]
    assert images == ["data/ti2026/inputs/evidence/main_event_seating/"
                      "ti15_main_event_bracket_client_crop_20260817.png"], images


def test_evidence_local_is_ignored():
    out = subprocess.run(["git", "check-ignore", "-q", "evidence_local/anything.png"],
                         cwd=REPO, capture_output=True)
    assert out.returncode == 0, "evidence_local/ must be git-ignored"


def test_public_evidence_index_carries_no_identity():
    """The index must commit to the private originals by hash without naming anyone."""
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    blob = json.dumps(idx, ensure_ascii=False)
    forbidden = _leak_needles()
    for f in forbidden:
        assert f not in blob, f"public evidence index leaks {f!r}"
    assert idx["raw_evidence_public"] is False
    for e in idx["evidence"]:
        assert len(e["sha256"]) == 64
        assert e["evidence_phase"] in ("pre_event", "post_event")
        assert e["source_tier"] == 1 and e["operator_supplied"] is True
        if not e["raw_evidence_public"]:
            assert e["raw_evidence_storage"] == "private_local_external"
            assert e["reason_not_committed"]


# A KNOWN, PRE-EXISTING exposure, registered here rather than hidden.
#
# Seven pre-event Fantasy account-state files carry the friend account's display name inside the
# client's rendered `compendium_player_title` string, which embeds the account name in the title
# text. They were committed and pushed long before this archival phase, so the exposure is already
# public and cannot be undone by anything this phase is permitted to do: editing them would mutate
# frozen pre-event evidence, and removing them from history would mean rewriting a published
# branch. Both are out of scope by instruction, and a force push would not recall clones, forks or
# caches in any case.
#
# What this register DOES buy: the exposure is documented, bounded to an exact file list, and
# cannot grow. Any new tracked file carrying the name fails this test.
KNOWN_IDENTITY_EXPOSURE = frozenset(
    f"predictions/ti2026/fantasy/account_state_target_{d}.json"
    for d in ("20260811", "20260811b", "20260811c", "20260812", "20260812b", "20260812c",
              "20260812d"))


def test_client_identity_does_not_spread_beyond_the_known_exposure():
    forbidden = _identity_needles()
    hits = set()
    for p in _tracked():
        full = os.path.join(REPO, p)
        if not os.path.isfile(full) or os.path.getsize(full) > 4_000_000:
            continue
        if p.endswith("test_postmortem.py"):
            continue
        try:
            src = open(full, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        if any(f in src for f in forbidden):
            hits.add(p)
    new = sorted(hits - KNOWN_IDENTITY_EXPOSURE)
    assert not new, f"client identity appears in tracked content outside the known register: {new}"
    gone = sorted(KNOWN_IDENTITY_EXPOSURE - hits)
    assert not gone, ("the known-exposure register is stale; these files no longer carry the name "
                      f"and should be removed from the register: {gone}")


def test_the_post_event_archive_itself_is_identity_clean():
    forbidden = _identity_needles()
    archival = ["data/ti2026/outcomes/main_event_results.json",
                "data/ti2026/outcomes/sources.json",
                "data/ti2026/evidence/private_evidence_index.json",
                "predictions/ti2026/postmortem/bracket_evaluation.json",
                "predictions/ti2026/postmortem/ti2026_postmortem.json",
                "predictions/ti2026/postmortem/fantasy_closure.json",
                "predictions/ti2026/postmortem/frozen_serve_state.json"]
    for p in archival:
        full = os.path.join(REPO, p)
        assert os.path.exists(full), p
        src = open(full, encoding="utf-8").read()
        for f in forbidden:
            assert f not in src, f"{p} leaks client identity"
        for needle in _leak_needles():
            assert needle not in src, f"{p} leaks {needle!r}"


def test_private_archive_hashes_match_the_public_index_when_present():
    """If the private archive is mounted, its bytes must be the ones the index commits to."""
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    manifest = os.environ.get("TI_PREDICT_PRIVATE_EVIDENCE")
    if not manifest:
        candidates = [os.path.join(os.path.dirname(REPO),
                                   os.path.basename(REPO) + PRIVATE_DIR_SUFFIX,
                                   "ti2026", "manifest.private.json")]
        manifest = next((c for c in candidates if os.path.exists(c)), None)
    if not manifest or not os.path.exists(manifest):
        pytest.skip("private evidence archive is not mounted on this machine")
    priv = json.load(open(manifest, encoding="utf-8"))
    by_id = {e["evidence_id"]: e for e in priv["evidence"]}
    for e in idx["evidence"]:
        rec = by_id[e["evidence_id"]]
        assert rec["sha256"] == e["sha256"]
        assert rec["bytes"] == e["bytes"]
        assert rec["byte_preserving_move"] is True
        assert _sha256(rec["canonical_path"]) == e["sha256"], \
            f"{e['evidence_id']}: the archived file no longer hashes to the committed value"


# --------------------------------------------------------------------------- 19 Fantasy
def test_fantasy_closure_does_not_claim_an_official_settlement():
    f = json.load(open(os.path.join(pm.POSTMORTEM_DIR, "fantasy_closure.json"), encoding="utf-8"))
    assert f["realized_fantasy_outcome"]["status"] == "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED"
    assert f["status"] == "SEALED"
    assert f["uncertainty_semantics"]["upper_bound_available"] is False
    assert f["leaderboard_percentile"]["status"] == "NOT ESTIMATED"
    dec = f["reconciled_decomposition"]
    assert dec["emblem_and_banner_slot_effect"] + dec["coach_title_effect"] \
        + dec["team_and_deployment_effect"] == dec["total"]
    withdrawn = {w["claim"] for w in f["withdrawn_claims_do_not_revive"]}
    assert len(withdrawn) == 2 and all(
        w["status"] == "WITHDRAWN" for w in f["withdrawn_claims_do_not_revive"])
    blob = json.dumps(f, ensure_ascii=False)
    assert "account_a" in blob and "account_b" in blob


def test_settlement_transcription_and_derivation_agree():
    """The directly transcribed count and the derived score must be one consistent story.

    8 and 6 are read straight off the capture. 4320 is derived from the committed scoring vector.
    The two are only worth quoting together if the derivation keys on the transcribed count, so
    that link is asserted rather than assumed.
    """
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    e = next(x for x in idx["evidence"] if x["evidence_id"] == "ti2026-ev-003")
    s = e["public_safe_transcription"]["main_event_prediction_settlement"]
    assert s["correct_predictions"] == OFFICIAL_CORRECT
    assert s["incorrect_predictions"] == OFFICIAL_INCORRECT
    assert s["total_predictions"] == 14
    assert s["correct_predictions"] + s["incorrect_predictions"] == s["total_predictions"]
    vec = bk.verify_scoring_vector()["vector"]
    assert vec[s["correct_predictions"]] == OFFICIAL_SCORE
    ev = pm.build()["official_evaluation"]
    assert ev["official_correct"] == s["correct_predictions"]
    assert ev["official_incorrect"] == s["incorrect_predictions"]
    assert ev["official_score"] == vec[s["correct_predictions"]] == OFFICIAL_SCORE


def test_points_provenance_is_stated_as_derived_for_this_capture_only():
    """The archive must not claim the client shows no points figure - only that this frame does not.

    The distinction is the whole content of INC-16: a statement about one archived frame is
    verifiable from the bytes, a statement about the client is not.
    """
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    e = next(x for x in idx["evidence"] if x["evidence_id"] == "ti2026-ev-003")
    s = e["public_safe_transcription"]["main_event_prediction_settlement"]
    assert s["official_points_visible_in_this_capture"] is False
    basis = s["official_points_basis"]
    assert "DERIVED" in basis
    assert "settlement summary panel" in basis
    for overreach in ("the client displays no points",
                      "the client shows no points figure",
                      "shows no points figure for it"):
        assert overreach not in basis, f"over-broad claim about the client: {overreach!r}"


def test_final_fantasy_states_are_indexed_privately_and_anonymously():
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    by_id = {e["evidence_id"]: e for e in idx["evidence"]}
    for eid, label, tokens in (("ti2026-ev-004", "account_a", 0), ("ti2026-ev-005", "account_b", 2)):
        e = by_id[eid]
        assert e["media_type"] == "application/json"
        assert len(e["sha256"]) == 64
        assert e["raw_evidence_public"] is False
        assert e["raw_evidence_storage"] == "private_local_external"
        assert e["public_account_label"] == label
        assert e["evidence_phase"] == "pre_event"
        assert e["observed_after_prediction"] is False
        t = e["public_safe_transcription"]
        assert t["remaining_reroll_tokens"] == tokens
        assert t["role_banners"] == ["core", "mid", "support"]
        assert t["emblem_slots_per_banner"] == 5
        blob = json.dumps(e, ensure_ascii=False)
        for needle in _leak_needles():
            assert needle not in blob, f"{eid} leaks {needle!r}"


def test_legacy_exposure_decision_is_recorded():
    from ti_predict import ti2026_record as rc
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    leg = idx["legacy_identity_exposure"]
    assert leg["status"] == "ACCEPTED_LEGACY_EXPOSURE_PRESERVE_HISTORY"
    assert leg["incident"] == "INC-19"
    assert leg["forward_control"]
    assert leg["if_removal_is_later_requested"]
    inc = next(i for i in rc.INCIDENTS if i["id"] == "INC-19")
    assert inc["status"] == "RESOLVED - ACCEPTED_LEGACY_EXPOSURE_PRESERVE_HISTORY"
    assert inc["resolution"]["forward_control_retained"] is True
    # the decision record must describe the exposure generically, never by repeating the name
    for needle in _identity_needles():
        assert needle not in json.dumps(leg, ensure_ascii=False)
        assert needle not in json.dumps(inc, ensure_ascii=False)


def test_the_settlement_capture_is_not_read_as_a_fantasy_score():
    idx = json.load(open(pm.SETTLEMENT, encoding="utf-8"))
    e = next(x for x in idx["evidence"] if x["evidence_id"] == "ti2026-ev-003")
    t = e["public_safe_transcription"]
    assert "main_event_prediction_settlement" in t
    assert "fantasy" not in json.dumps(t["main_event_prediction_settlement"]).lower()
    assert t["main_event_prediction_settlement"]["official_points_displayed_by_client"] is None
    assert json.load(open(os.path.join(pm.POSTMORTEM_DIR, "fantasy_closure.json"),
                          encoding="utf-8"))["realized_fantasy_outcome"]["status"] == \
        "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED"


# --------------------------------------------------------------------------- 20 untouched local artifact
def test_main_event_zip_is_not_tracked():
    assert not [p for p in _tracked() if os.path.basename(p) == "main_event.zip"]
