"""The tracked inventory of everything TI2026 asks the entrant to answer, and its readiness gate.

Two files are the fact source and this module is their validator:
  inputs/prediction_questions.json  -- every in-client item that requires an answer, selection or
                                       configuration, with its rules, slots, lock time and source.
  inputs/fantasy/fantasy_rules.json -- the Fantasy scoring ruleset, with each runtime-supplied
                                       number recorded as null rather than guessed.

The point of the readiness gate is to make "we do not know the rules yet" a machine-checkable state
rather than a matter of judgement. A question whose scoring rule contains an unresolved number
cannot be optimised, and a candidate answer produced anyway would be a guess wearing the costume of
a model. `readiness()` therefore refuses per question, and names the missing facts.

Statuses on a question:
  CONFIRMED  -- rules, slots, candidates and lock time all established from a tier-1 source.
  PARTIAL    -- the structure is established but at least one scoring-relevant value is not.
  UNRESOLVED -- the question is known to exist but its rules are not established.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
QUESTIONS_JSON = os.path.join(INPUTS, "prediction_questions.json")
RULES_JSON = os.path.join(INPUTS, "fantasy", "fantasy_rules.json")
GENERIC_EVIDENCE_JSON = os.path.join(INPUTS, "fantasy", "generic_evidence.json")

STATUSES = ("CONFIRMED", "PARTIAL", "UNRESOLVED")
# What an unknown does to the ANSWER, which is a different question from what the
# evidence supports. CONDITIONAL means it blocks only in a state that can be checked.
DECISION_STATUSES = ("BLOCKING", "ROBUST", "SCALE_ONLY", "IRRELEVANT", "CONDITIONAL")
ANSWERABLE_STATUS = ("CONFIRMED",)
REQUIRED_FIELDS = ("question_id", "category", "official_en_label", "exact_question", "answer_type",
                   "number_of_slots", "allowed_candidates", "restrictions", "scoring_rule",
                   "scoring_unit", "settlement_scope", "time_window", "source", "source_tier",
                   "retrieved_at", "status")
# Questions the frozen group-stage track already answers. Listed so the fantasy track can prove it
# is not re-deriving them rather than merely happening not to.
FROZEN_TRACK_CATEGORY = "group_stage_team_prediction"
# A scoring coefficient may exist in the ruleset only with an attribution. Reading a number off a
# panel the operator supplied is legitimate evidence and is recorded as such; what is forbidden is a
# number with no stated origin, and promoting a second-hand reading to CONFIRMED.
POINT_FIELDS = ("points_per_unit", "starting_points", "maximum_points")
TIER1_POINTS_SOURCE = "client_ui"
POINTS_SOURCES = (TIER1_POINTS_SOURCE, "user_screenshot")
DISCOVERY_KEYS = (
    "A_group_stage_team_predictions",
    "B_fantasy_player_selection",
    "C_fantasy_stat_categories",
    "D_tournament_wide_player_predictions",
    "E_hero_predictions",
    "F_other_team_match_tournament_statistics",
    "G_item_gameplay_event_predictions",
    "H_other_compendium_predictions_or_challenges",
)


def _relpath(p):
    """Repo-relative path for display, tolerant of a file on a different drive or mount."""
    try:
        return os.path.relpath(p, REPO).replace("\\", "/")
    except ValueError:
        return p


def _read(path):
    if not os.path.exists(path):
        raise SystemExit(f"inventory file not found: {_relpath(path)}")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{_relpath(path)} is not valid JSON: {e}")


def load_questions(path=None):
    """Read and validate the question inventory. Returns the parsed document.

    Validates: every question carries the full field set; ids are unique; statuses are known;
    every cited source id exists in the document's own source table; and a question that is
    answerable now states a lock time.
    """
    path = path or QUESTIONS_JSON
    doc = _read(path)
    known_sources = set(s["id"] for s in doc.get("sources", {}).values() if "id" in s)
    if not known_sources:
        raise SystemExit(f"{_relpath(path)}: no sources declared; every claim must cite one")
    seen = set()
    for q in doc.get("questions", []):
        qid = q.get("question_id") or "<unnamed>"
        missing = [f for f in REQUIRED_FIELDS if f not in q]
        if missing:
            raise SystemExit(f"{_relpath(path)}: {qid} is missing " + ", ".join(missing))
        if qid in seen:
            raise SystemExit(f"{_relpath(path)}: duplicate question_id {qid}")
        seen.add(qid)
        if q["status"] not in STATUSES:
            raise SystemExit(f"{_relpath(path)}: {qid} has status {q['status']!r}; "
                             f"expected one of {', '.join(STATUSES)}")
        unknown = [s for s in q["source"] if s not in known_sources]
        if unknown:
            raise SystemExit(f"{_relpath(path)}: {qid} cites unknown source(s) "
                             + ", ".join(unknown))
        if q.get("answerable_now") and not (q.get("lock_time_utc") or q.get("lock_time_note")):
            raise SystemExit(f"{_relpath(path)}: {qid} is answerable now but states no lock time")
    if not seen:
        raise SystemExit(f"{_relpath(path)}: the inventory is empty")
    discovery = doc.get("discovery_checklist_result", {})
    missing_discovery = [key for key in DISCOVERY_KEYS if key not in discovery]
    if missing_discovery:
        raise SystemExit(f"{_relpath(path)}: discovery checklist is missing "
                         + ", ".join(missing_discovery))
    # Whether or not an image arrived, an unfinished reconciliation must name what it still needs.
    # Silence here would read as "nothing left to ask for", which is the one thing it never means.
    screenshot = doc.get("screenshot_reconciliation", {})
    if screenshot.get("status") != "CONFIRMED" and not screenshot.get("still_requires_live_client"):
        raise SystemExit(f"{_relpath(path)}: the screenshot reconciliation is not CONFIRMED but no "
                         "precise live-client requests are listed")
    if doc.get("phase_1_status") != "CONFIRMED" and not doc.get("phase_1_blockers"):
        raise SystemExit(f"{_relpath(path)}: PHASE 1 is not confirmed but no blockers are listed")
    return doc


def load_rules(path=None):
    """Read and validate the Fantasy ruleset. Returns the parsed document.

    Validates the one property that matters for honesty: a stat may not carry a points_per_unit
    unless the ruleset also declares that the value was confirmed. Nothing here may be back-filled
    from a previous year's scoring table.
    """
    path = path or RULES_JSON
    doc = _read(path)
    stats = doc.get("stats", {})
    listed = stats.get("list", [])
    if stats.get("count") != len(listed):
        raise SystemExit(f"{_relpath(path)}: stats.count is {stats.get('count')} but "
                         f"{len(listed)} stats are listed")
    ids = [s["stat_id"] for s in listed]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{_relpath(path)}: duplicate stat_id in the stat table")
    by_color = stats.get("by_color", {})
    grouped = [s for c in ("red", "blue", "green") for s in by_color.get(c, [])]
    if sorted(grouped) != sorted(ids):
        raise SystemExit(f"{_relpath(path)}: by_color does not partition the stat table")
    for s in listed:
        numeric = [f for f in POINT_FIELDS if isinstance(s.get(f), (int, float))]
        if not numeric:
            continue
        src, st = s.get("points_source_type"), s.get("points_status")
        if src not in POINTS_SOURCES:
            raise SystemExit(f"{_relpath(path)}: {s['stat_id']} carries {', '.join(numeric)} but "
                             f"points_source_type is {src!r}; a scoring coefficient must say where "
                             f"it came from (one of {', '.join(POINTS_SOURCES)})")
        if st not in STATUSES:
            raise SystemExit(f"{_relpath(path)}: {s['stat_id']} carries {', '.join(numeric)} but "
                             f"points_status is {st!r}")
        if src != TIER1_POINTS_SOURCE and st == "CONFIRMED":
            raise SystemExit(f"{_relpath(path)}: {s['stat_id']} is CONFIRMED on a {src} reading; "
                             "only a direct client read may confirm a scoring coefficient")
    if "blocking_unknowns" in doc:
        raise SystemExit(f"{_relpath(path)}: blocking_unknowns is a second, hand-written copy of "
                         "readiness. Readiness is derived from `unknowns`; delete the list.")
    unknowns = doc.get("unknowns")
    if not unknowns:
        raise SystemExit(f"{_relpath(path)}: no `unknowns` register; readiness has nothing to "
                         "derive from")
    seen = set()
    for u in unknowns:
        uid = u.get("id", "<unnamed>")
        for f in ("id", "scope", "question", "fact_status", "decision_status", "blocking_for"):
            if f not in u:
                raise SystemExit(f"{_relpath(path)}: unknown {uid} is missing {f}")
        if uid in seen:
            raise SystemExit(f"{_relpath(path)}: duplicate unknown id {uid}")
        seen.add(uid)
        if u["scope"] not in ("generic", "account"):
            raise SystemExit(f"{_relpath(path)}: unknown {uid} has scope {u['scope']!r}")
        if u["fact_status"] not in STATUSES:
            raise SystemExit(f"{_relpath(path)}: unknown {uid} has fact_status "
                             f"{u['fact_status']!r}")
        if u["decision_status"] not in DECISION_STATUSES:
            raise SystemExit(f"{_relpath(path)}: unknown {uid} has decision_status "
                             f"{u['decision_status']!r}; every unknown must be MEASURED against "
                             f"the decision, not left unscored (one of {', '.join(DECISION_STATUSES)})")
        if u["decision_status"] == "CONDITIONAL" and not u.get("condition"):
            raise SystemExit(f"{_relpath(path)}: unknown {uid} is CONDITIONAL but states no "
                             "condition, so nobody can tell when it applies")
        if u["decision_status"] in ("BLOCKING", "CONDITIONAL") and not u["blocking_for"]:
            raise SystemExit(f"{_relpath(path)}: unknown {uid} blocks but names nothing in "
                             "blocking_for")
    return doc


def blockers(rules=None, account_state_known=False):
    """The unknowns that actually stop a decision, derived from the register and nothing else.

    A CONDITIONAL unknown blocks only once the account state that triggers it is known to hold.
    Before that it is reported separately: declaring a decision permanently blocked on a condition
    nobody has evaluated is how a track stays frozen for no reason.
    """
    rules = rules or load_rules()
    hard, conditional = [], []
    for u in rules["unknowns"]:
        if u["decision_status"] == "BLOCKING":
            hard.append(u)
        elif u["decision_status"] == "CONDITIONAL":
            (hard if account_state_known else conditional).append(u)
    return {"blocking": hard, "conditional_pending_account_state": conditional,
            "blocking_ids": [u["id"] for u in hard],
            "conditional_ids": [u["id"] for u in conditional]}


def load_generic_evidence(path=None):
    """Read and validate the generic-evidence register.

    Its job is to keep the generic / account-specific line honest, so the one thing worth enforcing
    is that every source declares a tier and that the register still states which facts are
    account-specific. A register that quietly lost that distinction would justify asking the
    operator for things the internet can answer, which is exactly what it exists to prevent.
    """
    path = path or GENERIC_EVIDENCE_JSON
    doc = _read(path)
    split = doc.get("generic_vs_account_specific", {})
    if not split.get("account_specific_examples") or not split.get("generic_examples"):
        raise SystemExit(f"{_relpath(path)}: the generic / account-specific split must name "
                         "examples on both sides")
    srcs = doc.get("sources", [])
    if not srcs:
        raise SystemExit(f"{_relpath(path)}: no sources registered")
    seen = set()
    for s in srcs:
        for f in ("id", "tier", "kind", "what"):
            if f not in s:
                raise SystemExit(f"{_relpath(path)}: source {s.get('id', '<unnamed>')} "
                                 f"is missing {f}")
        if s["tier"] not in (1, 2, 3):
            raise SystemExit(f"{_relpath(path)}: source {s['id']} has tier {s['tier']!r}")
        if s["id"] in seen:
            raise SystemExit(f"{_relpath(path)}: duplicate source id {s['id']}")
        seen.add(s["id"])
    hist = doc.get("historical_valve_official", {})
    if hist and hist.get("grade") != "OFFICIAL-HISTORICAL":
        raise SystemExit(f"{_relpath(path)}: historical Valve material must carry the grade "
                         "OFFICIAL-HISTORICAL so it can never be read as a current confirmation")
    return doc


def readiness(questions_path=None, rules_path=None):
    """Per question: may a submission-grade candidate be produced for it right now, and if not why.

    A question is candidate-ready when its own rules are CONFIRMED, it is answerable now, and -- for
    anything scored by the Fantasy ruleset -- that ruleset carries no blocking unknowns.
    """
    doc = load_questions(questions_path)
    rules = load_rules(rules_path)
    blk = blockers(rules)
    blocking = blk["blocking_ids"]
    out = []
    for q in doc["questions"]:
        reasons = []
        if q["status"] != "CONFIRMED":
            reasons.append(f"question status is {q['status']}")
        if not q.get("answerable_now"):
            reasons.append(q.get("answerable_reason") or "the client has not opened this question")
        if q["category"].startswith("fantasy") and blocking:
            reasons.append("blocked by " + ", ".join(blocking))
        out.append({"question_id": q["question_id"], "category": q["category"],
                    "number_of_slots": q["number_of_slots"], "status": q["status"],
                    "handled_by": q.get("handled_by"),
                    "candidate_ready": not reasons, "blocked_by": reasons})
    return {"questions": out, "blocking_unknowns": blocking,
            "conditional_unknowns": blk["conditional_ids"],
            "candidate_ready": [r["question_id"] for r in out if r["candidate_ready"]],
            "candidate_ready_new_track": [r["question_id"] for r in out
                                          if r["candidate_ready"]
                                          and r["category"] != FROZEN_TRACK_CATEGORY],
            "blocked": [r["question_id"] for r in out if not r["candidate_ready"]]}


def inventory(questions_path=None):
    """Manifest-ready summary of the inventory: activities, slot counts and lock times."""
    doc = load_questions(questions_path)
    qs = doc["questions"]
    slots = sum(q["number_of_slots"] or 0 for q in qs)
    locks = sorted({q["lock_time_utc"] for q in qs if q.get("lock_time_utc")})
    return {"event": doc["event"], "league_id": doc["league_id"],
            "compiled_at": doc["compiled_at"], "source_file": _relpath(questions_path
                                                                      or QUESTIONS_JSON),
            "phase_1_status": doc["phase_1_status"],
            "screenshot_status": doc["screenshot_reconciliation"]["status"],
            "activities": [{"activity_id": a["activity_id"], "label": a["official_en_label"],
                            "slots": a.get("total_slots"), "status": a["status"]}
                           for a in doc["activities"]],
            "questions": len(qs), "slots": slots, "lock_times_utc": locks,
            "by_status": {s: sum(1 for q in qs if q["status"] == s) for s in STATUSES},
            "frozen_track_questions": [q["question_id"] for q in qs
                                       if q["category"] == FROZEN_TRACK_CATEGORY]}


def to_markdown(questions_path=None, rules_path=None):
    """Render the inventory and its readiness verdict. The JSON stays the fact source."""
    doc = load_questions(questions_path)
    inv = inventory(questions_path)
    rd = readiness(questions_path, rules_path)
    ready = {r["question_id"]: r for r in rd["questions"]}
    lines = [f"# TI2026 prediction inventory ({inv['event']})", "",
             f"Compiled {inv['compiled_at']} from league {inv['league_id']}. "
             f"{inv['questions']} questions, {inv['slots']} fixed-count answer slots, plus "
             "the unresolved Fantasy emblem configuration slots.", "",
             f"PHASE 1 status: **{inv['phase_1_status']}**. "
             f"Screenshot reconciliation: **{inv['screenshot_status']}**.", "",
             "## Activities", "",
             "| Activity | Slots | Status |", "| --- | --- | --- |"]
    lines += [f"| {a['label']} | {a['slots']} | {a['status']} |" for a in inv["activities"]]
    lines += ["", "## Questions", "",
              "| Question | Slots | Lock (UTC) | Status | Candidate ready |",
              "| --- | --- | --- | --- | --- |"]
    for q in doc["questions"]:
        r = ready[q["question_id"]]
        if q.get("handled_by"):
            verdict = "handled by frozen track"
        else:
            verdict = "yes" if r["candidate_ready"] else "no - " + "; ".join(r["blocked_by"])
        lines.append(f"| {q['question_id']} | {q['number_of_slots']} | "
                     f"{q.get('lock_time_utc') or 'unresolved'} | {q['status']} | {verdict} |")
    lines += ["", "## Discovery checklist", ""]
    for key in DISCOVERY_KEYS:
        lines.append(f"- {key[0]}: {doc['discovery_checklist_result'][key]}")
    if rd["blocking_unknowns"]:
        lines += ["", "## Blocking unknowns in the Fantasy ruleset", ""]
        lines += [f"- {b}" for b in rd["blocking_unknowns"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    inv = inventory()
    rd = readiness()
    print(f"{inv['event']}: {inv['questions']} questions, {inv['slots']} fixed-count slots, "
          + ", ".join(f"{n} {s.lower()}" for s, n in inv["by_status"].items() if n))
    print(f"  PHASE 1: {inv['phase_1_status']}; screenshot: {inv['screenshot_status']}")
    for a in inv["activities"]:
        print(f"  {a['label']:<28} slots={a['slots']!s:<4} {a['status']}")
    print(f"  lock times (UTC): {', '.join(inv['lock_times_utc'])}")
    print(f"  new-track candidate-ready questions: {len(rd['candidate_ready_new_track'])} "
          f"of {len(rd['questions'])} (the 6 frozen group-stage questions are excluded)")
    for r in rd["questions"]:
        if not r["candidate_ready"]:
            print(f"    BLOCKED {r['question_id']}: {'; '.join(r['blocked_by'])}")
    if rd["blocking_unknowns"]:
        print(f"  {len(rd['blocking_unknowns'])} unresolved Fantasy scoring values")
