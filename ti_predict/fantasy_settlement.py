"""Post-seal addendum: the official TI2026 Fantasy settlement, read from four first-party frames.

At seal time the Fantasy track closed with an explicit hole in it:

    realized_fantasy_outcome.status = OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED

That was true when it was written. No client capture of a settled Fantasy period existed, and the
archive refused to substitute anything for one - not the account sidebar total, not the bracket
settlement, and above all not a reconstruction, because reconstructing an official Fantasy score
needs exactly the three statistics that were unobservable from every source this project holds.

Four client frames later became available: two accounts x two Fantasy periods, each showing the
settled period score, the Fantasy percentile, the three role scores and every scored emblem row.
This module archives them. It supersedes the CURRENT knowledge state and rewrites nothing: the
sealed closure keeps its historical status verbatim, and the transition is recorded here instead.

Three separations are load-bearing and are kept apart in every artifact this module writes.

  DIRECT FIRST-PARTY FACT   what the client displays. Transcribed at native resolution, per frame,
                            and never averaged, rounded or re-derived.
  DERIVED ARITHMETIC        differences and sums computed here from those facts. Exact, and labelled
                            as derived - in particular the two-period sums, which the client never
                            displays as a total and which are NOT an official overall score.
  FROZEN PRE-EVENT ESTIMATE the sealed observed-data plug-in. It is read from fantasy_closure.json,
                            never re-run and never re-fitted, and it is NOT a complete expected-value
                            forecast: three official statistics were excluded from it by construction.

The last point is the one that is easy to get wrong. A statistic excluded from the estimator
contributes zero TO THAT ESTIMATOR BY EXCLUSION; its true contribution was UNKNOWN, not zero. The
settlement now makes those four excluded emblems visible, so the sealed uncertainty equation can be
evaluated - retrospectively, as a diagnostic. It does not become a corrected forecast, it does not
license a re-fit, and N = 2 accounts x 2 periods proves nothing about a decision rule.

No network. Deterministic. Run `python -m ti_predict.fantasy_settlement`.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ti_predict import chronology as ch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOSURE = os.path.join(REPO, "predictions", "ti2026", "postmortem", "fantasy_closure.json")
INDEX = os.path.join(REPO, "data", "ti2026", "evidence", "private_evidence_index.json")
RESULTS = os.path.join(REPO, "data", "ti2026", "outcomes", "fantasy_results.json")
ADDENDUM = os.path.join(REPO, "predictions", "ti2026", "postmortem",
                        "fantasy_settlement_addendum.json")

SCHEMA_VERSION = 1
CREATED_AT = "2026-08-24T07:40:00Z"

ACCOUNTS = ("operator", "target")
PERIODS = ("group_stage", "main_event")
ROLES = ("core", "mid", "support")

# The client renders each figure to two decimals. A displayed sum is the rounded true sum, while the
# parts are each independently rounded, so the parts can disagree with the whole by up to half a
# unit in the last place per term plus half a unit on the total itself. That is the ONLY tolerance
# this module allows anywhere; nothing here is permitted to "reconcile" by a wider margin.
DISPLAY_ULP = 0.01


def tolerance(n_terms):
    """Largest defensible |sum(displayed parts) - displayed total| for `n_terms` parts."""
    return DISPLAY_ULP * (n_terms + 1) / 2.0 + 1e-9


# --------------------------------------------------------------------------- the four frames
# One record per (account, period). `pixels`, `bytes` and `sha256` commit to the exact private
# original that was read; the private archive is re-hashed against these on every test run that can
# reach it. `account_role` is the ONLY account label this repository publishes.
EVIDENCE = {
    ("operator", "group_stage"): {
        "evidence_id": "ti2026-ev-007",
        "sha256": "abbfd8393a87a534e72f2dab5e86d950223ecf862b81bd70f5063487d8a4fe4d",
        "bytes": 2277719,
        "pixels": [2048, 1152],
    },
    ("operator", "main_event"): {
        "evidence_id": "ti2026-ev-008",
        "sha256": "a4584434c186c8f92821e756c695815c0f8e98faca7c267ebce1220d54ff5c8c",
        "bytes": 2319007,
        "pixels": [2048, 1152],
    },
    ("target", "group_stage"): {
        "evidence_id": "ti2026-ev-009",
        "sha256": "3fc0abd804beb04501c65f32c3ce17789cccfc4538d1982da417c53ea4278ee3",
        "bytes": 2330127,
        "pixels": [2048, 1152],
    },
    ("target", "main_event"): {
        "evidence_id": "ti2026-ev-010",
        "sha256": "5cfb43273e518d6c988cef0ffb80fe385359c27069c4ba475f90c9684ae9eebf",
        "bytes": 2358904,
        "pixels": [2048, 1152],
    },
}

CANONICAL_FILENAME = {
    ("operator", "group_stage"): "ti2026_fantasy_operator_group_stage_client.png",
    ("operator", "main_event"): "ti2026_fantasy_operator_main_event_client.png",
    ("target", "group_stage"): "ti2026_fantasy_target_group_stage_client.png",
    ("target", "main_event"): "ti2026_fantasy_target_main_event_client.png",
}

# TRANSCRIPTION. Read directly from the frames at native resolution, one frame at a time. Emblem
# rows are recorded in the client's own top-to-bottom order, with the client's stat key spelling as
# used by this repository's frozen state files. Nothing here is inferred from another frame, from
# the frozen estimate, or from any realized-score reasoning.
#
# The client labels stats in Chinese; the English keys below are this repository's canonical keys and
# are the ones the frozen artifacts use, which is what makes the configuration pin below checkable.
FRAMES = {
    ("operator", "group_stage"): {
        "client_tab": "group stage",
        "displayed_total": 37217.47,
        "displayed_percentile_pct": 44.28,
        "coach": {"prefix": "Elemental", "suffix": "the Tormented"},
        "roles": {
            "core": {
                "team": "Xtreme Gaming", "players": ["Ame", "Xxs"],
                "displayed_score": 12793.80,
                "emblems": [
                    {"stat": "tower_kills", "multiplier": 1.6, "points": 2996.22},
                    {"stat": "teamfight_participation", "multiplier": 2.1, "points": 6622.97},
                    {"stat": "deaths", "multiplier": 1.1, "points": 3174.60},
                ]},
            "mid": {
                "team": "Team Falcons", "players": ["Malr1ne"],
                "displayed_score": 14148.98,
                "emblems": [
                    {"stat": "madstone", "multiplier": 1.7, "points": 2446.91},
                    {"stat": "runes_grabbed", "multiplier": 1.8, "points": 7370.35},
                    {"stat": "tormentor_kills", "multiplier": 1.6, "points": 4331.71},
                ]},
            "support": {
                "team": "Xtreme Gaming", "players": ["fy", "xNova"],
                "displayed_score": 10274.70,
                "emblems": [
                    {"stat": "lotuses_gained", "multiplier": 2.1, "points": 3511.20},
                    {"stat": "tormentor_kills", "multiplier": 3.0, "points": 3955.50},
                    {"stat": "wards_placed", "multiplier": 1.2, "points": 2808.00},
                ]},
        },
    },
    ("operator", "main_event"): {
        "client_tab": "main event",
        "displayed_total": 82839.01,
        "displayed_percentile_pct": 88.50,
        "coach": {"prefix": "Otherworldly", "suffix": "the Clutch"},
        "roles": {
            "core": {
                "team": "PARIVISION", "players": ["Satanic", "No[t]iced"],
                "displayed_score": 39415.52,
                "emblems": [
                    {"stat": "tower_kills", "multiplier": 1.1, "points": 3120.83},
                    {"stat": "teamfight_participation", "multiplier": 2.7, "points": 8280.96},
                    {"stat": "deaths", "multiplier": 3.0, "points": 10448.10},
                    {"stat": "roshan_kills", "multiplier": 2.3, "points": 7170.30},
                    {"stat": "gpm", "multiplier": 3.0, "points": 10395.32},
                ]},
            "mid": {
                "team": "Team Falcons", "players": ["Malr1ne"],
                "displayed_score": 25733.90,
                "emblems": [
                    {"stat": "madstone", "multiplier": 1.8, "points": 1931.90},
                    {"stat": "runes_grabbed", "multiplier": 2.5, "points": 11139.00},
                    {"stat": "tormentor_kills", "multiplier": 2.5, "points": 4395.00},
                    {"stat": "deaths", "multiplier": 2.5, "points": 8268.00},
                    {"stat": "roshan_kills", "multiplier": 1.6, "points": 0.00},
                ]},
            "support": {
                "team": "Team Falcons", "players": ["Cr1t-", "Sneyking"],
                "displayed_score": 17689.59,
                "emblems": [
                    {"stat": "lotuses_grabbed", "multiplier": 1.0, "points": 1611.28},
                    {"stat": "first_blood", "multiplier": 3.0, "points": 0.00},
                    {"stat": "wards_placed", "multiplier": 1.7, "points": 4759.68},
                    {"stat": "teamfight_participation", "multiplier": 1.8, "points": 5612.46},
                    {"stat": "smokes_used", "multiplier": 2.5, "points": 5706.17},
                ]},
        },
    },
    ("target", "group_stage"): {
        "client_tab": "group stage",
        "displayed_total": 39692.11,
        "displayed_percentile_pct": 53.36,
        "coach": {"prefix": "Elemental", "suffix": "the Tormented"},
        "roles": {
            "core": {
                "team": "Xtreme Gaming", "players": ["Xxs", "Ame"],
                "displayed_score": 21393.54,
                "emblems": [
                    {"stat": "gpm", "multiplier": 1.5, "points": 4388.99},
                    {"stat": "roshan_kills", "multiplier": 2.1, "points": 3987.14},
                    {"stat": "creep_score", "multiplier": 3.2, "points": 13017.41},
                ]},
            "mid": {
                "team": "Team Yandex", "players": ["CHIRA_JUNIOR"],
                "displayed_score": 8229.52,
                "emblems": [
                    {"stat": "deaths", "multiplier": 1.8, "points": 6598.80},
                    {"stat": "wards_placed", "multiplier": 2.1, "points": 1022.11},
                    {"stat": "stuns", "multiplier": 1.7, "points": 608.60},
                ]},
            "support": {
                "team": "Xtreme Gaming", "players": ["xNova", "fy"],
                "displayed_score": 10069.05,
                "emblems": [
                    {"stat": "runes_grabbed", "multiplier": 2.9, "points": 3066.75},
                    {"stat": "first_blood", "multiplier": 1.5, "points": 2901.00},
                    {"stat": "watchers_taken", "multiplier": 1.8, "points": 4101.30},
                ]},
        },
    },
    ("target", "main_event"): {
        "client_tab": "main event",
        "displayed_total": 93454.67,
        "displayed_percentile_pct": 96.41,
        "coach": {"prefix": "Crimson", "suffix": "the Clutch"},
        "roles": {
            "core": {
                "team": "PARIVISION", "players": ["No[t]iced", "Satanic"],
                "displayed_score": 36051.03,
                "emblems": [
                    {"stat": "gpm", "multiplier": 1.8, "points": 5806.88},
                    {"stat": "roshan_kills", "multiplier": 1.7, "points": 996.20},
                    {"stat": "creep_score", "multiplier": 3.4, "points": 20282.70},
                    {"stat": "teamfight_participation", "multiplier": 1.5, "points": 4051.25},
                    {"stat": "madstone", "multiplier": 1.8, "points": 4914.00},
                ]},
            "mid": {
                "team": "Team Falcons", "players": ["Malr1ne"],
                "displayed_score": 30729.27,
                "emblems": [
                    {"stat": "deaths", "multiplier": 2.4, "points": 7160.40},
                    {"stat": "runes_grabbed", "multiplier": 2.7, "points": 10438.79},
                    {"stat": "courier_kills", "multiplier": 1.2, "points": 843.60},
                    {"stat": "creep_score", "multiplier": 3.0, "points": 8186.40},
                    {"stat": "first_blood", "multiplier": 2.0, "points": 4100.08},
                ]},
            "support": {
                "team": "Team Yandex", "players": ["Maladych", "Saksa"],
                "displayed_score": 26674.37,
                "emblems": [
                    {"stat": "runes_grabbed", "multiplier": 2.9, "points": 5266.63},
                    {"stat": "first_blood", "multiplier": 1.7, "points": 1643.90},
                    {"stat": "watchers_taken", "multiplier": 1.1, "points": 3318.08},
                    {"stat": "teamfight_participation", "multiplier": 3.0, "points": 10127.75},
                    {"stat": "wards_placed", "multiplier": 1.8, "points": 6318.00},
                ]},
        },
    },
}

# Which frozen artifact each frame's DEPLOYED CONFIGURATION must reproduce. This is what pins a frame
# to an account: the pin compares coach title, team, player set and the ordered (stat, multiplier)
# list of every emblem. It uses no score. The two group-stage counterparts are tracked in this
# repository; the two Main Event counterparts are the privately archived final banner states, which
# are the artifacts the sealed comparison was computed on.
FROZEN_PINS = {
    ("operator", "group_stage"): {
        "kind": "tracked",
        "path": "predictions/ti2026/fantasy/account_state_operator_20260812b.json",
    },
    ("target", "group_stage"): {
        "kind": "tracked",
        "path": "predictions/ti2026/fantasy/account_state_target_20260812d.json",
    },
    ("operator", "main_event"): {
        "kind": "private", "evidence_id": "ti2026-ev-004", "review_label": "account_a",
    },
    ("target", "main_event"): {
        "kind": "private", "evidence_id": "ti2026-ev-005", "review_label": "account_b",
    },
}

# The client and this repository spell the lotus statistic two ways across periods. They are the same
# official statistic; the alias exists so the unobservable-term lookup cannot miss one of them.
STAT_ALIASES = {"lotuses_gained": "lotuses_grabbed"}

# The two group-stage pins re-run from tracked files on any clone, so the artifacts carry the LIVE
# result. The two Main Event counterparts live in the private archive, which most clones cannot
# reach, so their result is RECORDED here instead - the same commitment the evidence sha256s make.
# `verify_pin` still runs the real comparison wherever the archive is mounted, and the test suite
# fails if a live run ever disagrees with what is recorded below. That keeps the committed artifacts
# byte-identical on every machine without letting the recorded claim drift from the archive.
PRIVATE_PIN_RECORDED = {
    ("operator", "main_event"): {"fields_compared": 23, "match": True},
    ("target", "main_event"): {"fields_compared": 23, "match": True},
}


def canonical_stat(stat):
    return STAT_ALIASES.get(stat, stat)


# --------------------------------------------------------------------------- sealed inputs
def load_closure(path=None):
    """The sealed Fantasy closure. Read, never written: it is the historical knowledge state."""
    with open(path or CLOSURE, encoding="utf-8") as fh:
        return json.load(fh)


def load_index(path=None):
    with open(path or INDEX, encoding="utf-8") as fh:
        return json.load(fh)


def private_manifest():
    """The private manifest, if this machine can reach it. Returns None when it cannot."""
    p = os.environ.get("TI_PREDICT_PRIVATE_EVIDENCE")
    if not p:
        p = os.path.join(os.path.dirname(REPO), os.path.basename(REPO) + "-evidence-private",
                         "ti2026", "manifest.private.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- 1. internal consistency
def reconcile(key):
    """Check a frame against itself: emblem rows -> role score -> displayed total.

    This is the only corroboration available for a Fantasy settlement. The bracket settlement could
    be recomputed from the committed slate and cross-checked against two client views; an official
    Fantasy score cannot be recomputed at all, because three of its statistics are unobservable from
    every source this project holds. So the frame is checked for internal consistency and the
    single-path provenance is stated plainly rather than dressed up as agreement.
    """
    fr = FRAMES[key]
    roles = {}
    for role in ROLES:
        r = fr["roles"][role]
        s = round(sum(e["points"] for e in r["emblems"]), 2)
        d = abs(s - r["displayed_score"])
        roles[role] = {
            "emblem_count": len(r["emblems"]),
            "sum_of_emblem_points": s,
            "displayed_score": r["displayed_score"],
            "abs_difference": round(d, 6),
            "tolerance": round(tolerance(len(r["emblems"])), 6),
            "within_tolerance": d <= tolerance(len(r["emblems"])),
        }
    total = round(sum(fr["roles"][r]["displayed_score"] for r in ROLES), 2)
    dt = abs(total - fr["displayed_total"])
    return {
        "per_role": roles,
        "sum_of_role_scores": total,
        "displayed_total": fr["displayed_total"],
        "abs_difference": round(dt, 6),
        "tolerance": round(tolerance(len(ROLES)), 6),
        "within_tolerance": dt <= tolerance(len(ROLES)),
        "all_within_tolerance": all(v["within_tolerance"] for v in roles.values())
                                and dt <= tolerance(len(ROLES)),
    }


def assert_reconciled():
    out = {}
    for key in FRAMES:
        rec = reconcile(key)
        if not rec["all_within_tolerance"]:
            raise SystemExit(
                f"settlement frame {key} does not reconcile within display rounding: {rec}")
        out["%s/%s" % key] = rec
    return out


# --------------------------------------------------------------------------- 2. the configuration pin
def _norm_team(t):
    return (t or "").strip().casefold()


def _norm_players(ps):
    return sorted(p.strip().casefold() for p in (ps or []))


def _counterpart(key):
    """Load the frozen state a frame must reproduce, plus where it came from."""
    pin = FROZEN_PINS[key]
    if pin["kind"] == "tracked":
        with open(os.path.join(REPO, pin["path"]), encoding="utf-8") as fh:
            return json.load(fh), pin["path"], "tracked"
    man = private_manifest()
    if not man:
        return None, pin["evidence_id"], "private_not_mounted"
    rec = next((e for e in man["evidence"] if e["evidence_id"] == pin["evidence_id"]), None)
    if not rec or not os.path.exists(rec.get("canonical_path", "")):
        return None, pin["evidence_id"], "private_not_mounted"
    with open(rec["canonical_path"], encoding="utf-8") as fh:
        return json.load(fh), pin["evidence_id"], "private"


def verify_pin(key):
    """Compare a frame's deployed configuration against its frozen counterpart, field by field.

    Deliberately score-free. Nothing in this comparison can be satisfied by a realized total being
    close to a projected one, which is exactly the inference the brief forbids for the A/B mapping.
    """
    doc, ref, source = _counterpart(key)
    out = {"frozen_artifact": ref, "source": source, "fields_compared": 0, "mismatches": []}
    if doc is None:
        out["checked"] = False
        out["note"] = ("the frozen counterpart is the private archive, which is not mounted here; "
                       "the recorded result of the check is carried instead")
        return out

    fr = FRAMES[key]
    out["checked"] = True
    for field in ("prefix", "suffix"):
        out["fields_compared"] += 1
        if (doc.get("coach") or {}).get(field) != fr["coach"][field]:
            out["mismatches"].append(f"coach.{field}")
    for role in ROLES:
        got, want = doc["banners"][role], fr["roles"][role]
        out["fields_compared"] += 1
        if _norm_team(got.get("client_team")) != _norm_team(want["team"]):
            out["mismatches"].append(f"{role}.team")
        # some frozen states record the team but not the player list; compare only what exists
        if got.get("players"):
            out["fields_compared"] += 1
            if _norm_players(got["players"]) != _norm_players(want["players"]):
                out["mismatches"].append(f"{role}.players")
        else:
            out.setdefault("players_not_recorded_in_frozen_state", []).append(role)
        a = [(canonical_stat(s["stat"]), round(float(s["displayed_multiplier"]), 3))
             for s in got.get("slots", [])]
        b = [(canonical_stat(e["stat"]), round(float(e["multiplier"]), 3))
             for e in want["emblems"]]
        out["fields_compared"] += len(b)
        if a != b:
            out["mismatches"].append(f"{role}.emblems {a} != {b}")
    out["match"] = not out["mismatches"]
    return out


def pin_record(key):
    """The pin result that goes into a committed artifact: live where reproducible, recorded where not."""
    if FROZEN_PINS[key]["kind"] == "tracked":
        return verify_pin(key)
    pin = FROZEN_PINS[key]
    rec = PRIVATE_PIN_RECORDED[key]
    return {
        "frozen_artifact": pin["evidence_id"],
        "source": "private",
        "result": "RECORDED",
        "checked_at": CREATED_AT,
        "fields_compared": rec["fields_compared"],
        "match": rec["match"],
        "method": ("coach title prefix and suffix, three teams, three player sets and fifteen "
                   "ordered (stat, multiplier) emblem pairs, compared against the privately "
                   "archived final banner state. No score information is used."),
        "reproducible_without_the_private_archive": False,
        "re_verified_by": ("tests/test_fantasy_settlement.py, which re-runs the live comparison "
                           "whenever the private archive is mounted and fails on any disagreement"),
    }


def account_mapping(pins=None):
    """Prove which sealed review label (account_a / account_b) is which anonymous account role.

    Two independent supports, neither of which uses a realized score:

      1. the privately archived final banner states each STATE their own review label, and the public
         evidence index already publishes that label per evidence id (ti2026-ev-004 -> account_a,
         ti2026-ev-005 -> account_b) together with the reroll-token count that distinguishes them;
      2. each Main Event frame reproduces its counterpart's full deployed configuration - coach title
         pair, three teams, three player sets and fifteen ordered (stat, multiplier) emblem pairs.

    The pseudonym-to-person mapping stays operator-held and unpublished, as the sealed closure
    committed. What is published here is a correspondence between two label systems this repository
    already publishes, which attaches no identity to any number.
    """
    pins = pins if pins is not None else {"%s/%s" % k: pin_record(k) for k in FRAMES}
    idx = {e["evidence_id"]: e for e in load_index()["evidence"]}
    supports, unresolved = [], []
    for key in (("operator", "main_event"), ("target", "main_event")):
        pin = FROZEN_PINS[key]
        label, eid = pin["review_label"], pin["evidence_id"]
        published = idx.get(eid, {}).get("public_account_label")
        if published != label:
            unresolved.append(f"{eid}: index publishes {published!r}, pin claims {label!r}")
        p = pins["%s/%s" % key]
        supports.append({
            "review_label": label,
            "account_role": key[0],
            "evidence_id_of_frozen_state": eid,
            "label_published_in_evidence_index": published,
            "settlement_frame": EVIDENCE[key]["evidence_id"],
            "configuration_fields_compared": p.get("fields_compared"),
            "configuration_match": p.get("match"),
            "configuration_evidence": p.get("result", "LIVE"),
        })
        if not p.get("match"):
            unresolved.append(f"{eid}: configuration mismatch {p.get('mismatches')}")
    return {
        "status": "ACCOUNT_MAPPING_PROVEN" if not unresolved else "ACCOUNT_MAPPING_UNRESOLVED",
        "mapping": {"account_a": "operator", "account_b": "target"},
        "supports": supports,
        "unresolved": unresolved,
        "score_information_used": False,
        "why_score_information_is_not_used": (
            "mapping accounts by which realized total is closer to which projection would assume the "
            "conclusion the comparison is supposed to test"),
        "what_stays_unpublished": (
            "which real person holds which account. That mapping is operator-held; nothing here "
            "publishes a display name, avatar or account identifier."),
    }


# --------------------------------------------------------------------------- 3. derived arithmetic
def period_differences(period):
    """target - operator, overall and per role, for one period. Exact at display precision."""
    o, t = FRAMES[("operator", period)], FRAMES[("target", period)]
    per_role = {r: round(t["roles"][r]["displayed_score"] - o["roles"][r]["displayed_score"], 2)
                for r in ROLES}
    overall = round(t["displayed_total"] - o["displayed_total"], 2)
    role_sum = round(sum(per_role.values()), 2)
    return {
        "operator_total": o["displayed_total"],
        "target_total": t["displayed_total"],
        "target_minus_operator": overall,
        "per_role_target_minus_operator": per_role,
        "sum_of_per_role_differences": role_sum,
        "sum_matches_overall_within_display_rounding":
            abs(role_sum - overall) <= tolerance(2 * len(ROLES)),
        "role_winner": {r: ("target" if per_role[r] > 0 else "operator") for r in ROLES},
        "period_winner": "target" if overall > 0 else "operator",
    }


def two_period_sums():
    """Arithmetic sums of the two archived period totals. NOT an official overall Fantasy total."""
    tot = {a: round(sum(FRAMES[(a, p)]["displayed_total"] for p in PERIODS), 2) for a in ACCOUNTS}
    return {
        "operator": tot["operator"],
        "target": tot["target"],
        "target_minus_operator": round(tot["target"] - tot["operator"], 2),
        "label": "arithmetic sum of the two archived Fantasy period totals",
        "is_official_overall_total": False,
        "why_not": (
            "no rule text this project verified, and no client view it holds, establishes that the "
            "two period scores add to a published overall Fantasy total. The client's own sidebar "
            "figure is an account-level event point total, which is a different quantity and is not "
            "transcribed. Until an official equivalence is evidenced, this is arithmetic performed "
            "here, not a score the client awarded."),
        "percentiles_are_not_combined": (
            "percentiles are not additive and are never summed, averaged or interpolated across "
            "periods. Each period's percentile is reported only against its own period."),
    }


# --------------------------------------------------------------------------- 4. frozen vs realized
def unobservable_terms(closure):
    """The emblems the sealed estimator excluded by construction, now visible with their points.

    The closure carried these symbolically:

        delta_full(B - A) = +3254.3 + U_B_madstone + U_B_watchers - U_A_madstone - U_A_lotuses

    Each U term is one emblem on one banner. The settlement displays those rows, so the equation can
    now be evaluated. This is a retrospective diagnostic: the terms were genuinely unknown when the
    decision was made, and nothing here converts them into a pre-event quantity.
    """
    unobs = set(closure["uncertainty_semantics"]["unobservable_statistics"])
    out = {}
    for account in ACCOUNTS:
        rows, total = [], 0.0
        fr = FRAMES[(account, "main_event")]
        for role in ROLES:
            for e in fr["roles"][role]["emblems"]:
                if canonical_stat(e["stat"]) in unobs:
                    rows.append({"role": role, "stat": canonical_stat(e["stat"]),
                                 "multiplier": e["multiplier"], "points": e["points"]})
                    total += e["points"]
        out[account] = {"emblems": rows, "points_total": round(total, 2)}
    delta = round(out["target"]["points_total"] - out["operator"]["points_total"], 2)
    a_terms = round(out["operator"]["points_total"], 2)
    return {
        "unobservable_statistics": sorted(unobs),
        "per_account": out,
        "target_minus_operator": delta,
        "equation_from_the_sealed_closure":
            closure["uncertainty_semantics"]["full_difference_equation"],
        "necessary_condition_check": {
            "condition": closure["uncertainty_semantics"]["necessary_condition_for_a_to_overturn_b"],
            "realized_left_hand_side": a_terms,
            "threshold": closure["observed_data_plug_in_estimate"]["difference_b_minus_a"],
            "condition_met": a_terms > closure["observed_data_plug_in_estimate"][
                "difference_b_minus_a"],
            "outcome": (
                "the NECESSARY condition was met and account_a still did not overturn account_b, "
                "which is exactly what the sealed record said the condition could not settle: it was "
                "necessary, not sufficient, because account_b's unobserved terms were unbounded too "
                "and turned out to be the larger pair."),
        },
        "status_change_for_observability": (
            "these statistics remain unobservable from public match data. The settlement view makes "
            "their SCORED CONTRIBUTION visible after the fact for these four banners only; it does "
            "not make the underlying per-player counts retrievable, and it arrives long after any "
            "decision it could have informed."),
    }


def frozen_comparison(closure):
    """The sealed Main Event estimate against the realized Main Event settlement."""
    plug = closure["observed_data_plug_in_estimate"]
    mapping = {"account_a": "operator", "account_b": "target"}
    pred = {mapping["account_a"]: plug["account_a_total"], mapping["account_b"]: plug["account_b_total"]}
    diff = period_differences("main_event")
    u = unobservable_terms(closure)

    predicted_gap = plug["difference_b_minus_a"]
    realized_gap = diff["target_minus_operator"]
    residual = round(realized_gap - predicted_gap - u["target_minus_operator"], 2)

    pred_role_winner = {r: mapping[w] for r, w in plug["per_role_winner"].items()}
    role_directions = {
        r: {"predicted_winner": pred_role_winner[r], "realized_winner": diff["role_winner"][r],
            "realized_difference_target_minus_operator": diff["per_role_target_minus_operator"][r],
            "direction_correct": pred_role_winner[r] == diff["role_winner"][r]}
        for r in ROLES}

    return {
        "period": "main_event",
        "frozen_estimate": {
            "source": "predictions/ti2026/postmortem/fantasy_closure.json",
            "estimator": plug["estimator"],
            "unit": plug["unit"],
            "read_not_recomputed": True,
            "per_account": pred,
            "difference_target_minus_operator": predicted_gap,
            "semantics": (
                "an observed-data plug-in on the deployed configuration, NOT a complete "
                "expected-value forecast: three official statistics were excluded from it by "
                "construction and contribute zero to it by exclusion, not by evidence."),
        },
        "realized": {"per_account": {a: FRAMES[(a, "main_event")]["displayed_total"]
                                     for a in ACCOUNTS},
                     "difference_target_minus_operator": realized_gap},
        "account_ordering": {
            "predicted": "target > operator" if predicted_gap > 0 else "operator > target",
            "realized": "target > operator" if realized_gap > 0 else "operator > target",
            "direction_correct": (predicted_gap > 0) == (realized_gap > 0),
        },
        "role_directions": role_directions,
        "role_directions_correct": sum(1 for v in role_directions.values() if v["direction_correct"]),
        "role_directions_total": len(ROLES),
        "gap_decomposition": {
            "identity": "realized_gap = frozen_estimate_gap + excluded_term_gap + residual",
            "frozen_estimate_gap": predicted_gap,
            "excluded_term_gap": u["target_minus_operator"],
            "residual": residual,
            "realized_gap": realized_gap,
            "exact_by_construction": True,
            "residual_meaning": (
                "projection error on the terms the estimator DID score, plus any difference in which "
                "series ended up being each role's best. It is not separable further from a "
                "settlement view, and it is not a calibration statistic."),
            "rounding_note": (
                "the sealed gap is recorded to one decimal, so the residual inherits that precision"),
        },
        "level_difference": {
            "operator_realized_minus_frozen": round(
                FRAMES[("operator", "main_event")]["displayed_total"] - pred["operator"], 2),
            "target_realized_minus_frozen": round(
                FRAMES[("target", "main_event")]["displayed_total"] - pred["target"], 2),
            "is_model_error": False,
            "why_not": (
                "the estimator omitted three official statistics by construction, so its level is a "
                "projection of a strict subset of the score. Calling the gap between it and the full "
                "official total 'error' would charge the estimator for terms it never claimed to "
                "include. No calibration claim is made, and none is supportable from two accounts."),
        },
        "excluded_terms": u,
    }


def group_stage_comparison():
    """There is no frozen two-account group-stage forecast. Say so rather than manufacture one."""
    return {
        "period": "group_stage",
        "status": "NO_FROZEN_PRE_EVENT_FORECAST",
        "what_was_searched": [
            "predictions/ti2026/postmortem/fantasy_closure.json",
            "predictions/ti2026/fantasy/preselection_20260810.json",
            "predictions/ti2026/fantasy/preselection_20260811_go.json",
            "predictions/ti2026/fantasy/preselection_20260811_hold.json",
            "predictions/ti2026/fantasy/team_change_experiment_20260812.json",
            "predictions/ti2026/fantasy/coach_pricing_20260812.json",
        ],
        "finding": (
            "no sealed artifact records a projected two-account group-stage total or gap. The sealed "
            "plug-in comparison is the Main Event one, and its per-role winners are the Main Event "
            "ones."),
        "consequence": (
            "the group-stage settlement is archived as fact and is NOT scored against a forecast. "
            "Constructing a group-stage projection now would be a post-hoc fit to a known answer."),
    }


def structural_attribution():
    """What the realized differences CAN and CANNOT be attributed to, from the frames alone.

    The strongest thing in the settlement is not a number, it is a coincidence of deployment: in the
    Main Event both accounts fielded the SAME core pair and the SAME mid player, and in the group
    stage the same core pair and the same support pair. Where the player set is identical, the raw
    per-player statistics feeding both accounts are identical, so the realized role difference cannot
    be a player-selection effect at all. That is a structural fact about the deployment, not a causal
    model, and it is the only causal-looking statement here that is actually supported.
    """
    out = {}
    for period in PERIODS:
        diff = period_differences(period)
        same_coach = FRAMES[("operator", period)]["coach"] == FRAMES[("target", period)]["coach"]
        roles = {}
        for role in ROLES:
            o = FRAMES[("operator", period)]["roles"][role]
            t = FRAMES[("target", period)]["roles"][role]
            same_players = _norm_players(o["players"]) == _norm_players(t["players"])
            same_team = _norm_team(o["team"]) == _norm_team(t["team"])
            if same_players and same_coach:
                attribution = (
                    "emblem construction only - the two accounts fielded the same players in this "
                    "role AND carried the same coach title, so the underlying per-player statistics "
                    "and the title amplification are identical and the entire difference is the "
                    "banner built on them")
            elif same_players:
                attribution = (
                    "emblem construction and coach title jointly - the two accounts fielded the same "
                    "players in this role, so no part of this difference can be a player-selection "
                    "effect, but the coach titles differed and a settlement view cannot split the two")
            else:
                attribution = (
                    "confounded - the accounts differed in BOTH the players fielded and the banner "
                    "built on them, and a settlement view cannot separate the two")
            roles[role] = {
                "same_team": same_team,
                "same_player_set": same_players,
                "same_coach_title": same_coach,
                "operator_team": o["team"], "target_team": t["team"],
                "difference_target_minus_operator": diff["per_role_target_minus_operator"][role],
                "attribution": attribution,
                "identifiable": bool(same_players),
                "isolates_emblem_construction": bool(same_players and same_coach),
            }
        share = {}
        tot = diff["target_minus_operator"]
        for role in ROLES:
            d = diff["per_role_target_minus_operator"][role]
            share[role] = round(d / tot, 4) if tot else None
        out[period] = {
            "per_role": roles,
            "share_of_period_gap": share,
            "share_note": ("a descriptive decomposition of the realized difference. Shares can "
                           "exceed 1 or be negative when roles pull in opposite directions."),
            "coach_titles": {a: FRAMES[(a, period)]["coach"] for a in ACCOUNTS},
            "coach_titles_identical": (FRAMES[("operator", period)]["coach"]
                                       == FRAMES[("target", period)]["coach"]),
        }
    return out


def dead_slots():
    """Emblems that scored exactly zero. A displayed multiplier is worth nothing on a stat that
    never occurs, which the sealed closure already recorded as a reusable finding; this counts it."""
    out = {}
    for key, fr in FRAMES.items():
        zeros = [{"role": r, "stat": e["stat"], "multiplier": e["multiplier"]}
                 for r in ROLES for e in fr["roles"][r]["emblems"] if e["points"] == 0.0]
        n = sum(len(fr["roles"][r]["emblems"]) for r in ROLES)
        out["%s/%s" % key] = {"zero_scoring_emblems": zeros, "emblem_slots": n,
                              "zero_share": round(len(zeros) / n, 4)}
    return out


# --------------------------------------------------------------------------- 5. artifacts
def _frame_record(key):
    account, period = key
    fr = FRAMES[key]
    return {
        "account_role": account,
        "period": period,
        "client_tab": fr["client_tab"],
        "evidence_id": EVIDENCE[key]["evidence_id"],
        "direct_first_party_facts": {
            "displayed_total": fr["displayed_total"],
            "displayed_percentile_pct": fr["displayed_percentile_pct"],
            "percentile_scope": ("the Fantasy leaderboard percentile the client displays for THIS "
                                 "period. It is not an account-level percentile and is never "
                                 "combined across periods."),
            "roles": {r: {"team": fr["roles"][r]["team"], "players": fr["roles"][r]["players"],
                          "displayed_score": fr["roles"][r]["displayed_score"],
                          "emblems": fr["roles"][r]["emblems"]} for r in ROLES},
            "coach_title": fr["coach"],
        },
        "internal_reconciliation": reconcile(key),
        "frozen_configuration_pin": pin_record(key),
    }


def build_results():
    """data/ti2026/outcomes/fantasy_results.json - first-party fact plus its own consistency check."""
    assert_reconciled()
    doc = ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "event": "The International 2026 (TI15)",
        "record": "official in-client Fantasy settlement, two accounts x two Fantasy periods",
        "created_at": CREATED_AT,
        "status": "OFFICIAL_FANTASY_OUTCOME_ARCHIVED",
        "supersedes_knowledge_state_of": {
            "artifact": "predictions/ti2026/postmortem/fantasy_closure.json",
            "historical_status": "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED",
            "historical_status_is_preserved": True,
            "note": ("that status was true when it was written and is left exactly as written. This "
                     "file records the later knowledge state; it does not edit the earlier one."),
        },
        "provenance": {
            "source_type": "first-party in-client capture, operator-supplied",
            "source_tier": 1,
            "network_access_used": False,
            "raw_evidence_public": False,
            "evidence_ids": [EVIDENCE[k]["evidence_id"] for k in
                             sorted(EVIDENCE, key=lambda k: EVIDENCE[k]["evidence_id"])],
            "independent_paths": 1,
            "single_path_note": (
                "unlike the bracket settlement, which has two client views AND a deterministic "
                "recomputation, an official Fantasy score cannot be recomputed by this project at "
                "all: three of its statistics are unobservable from every source held. Provenance "
                "here is one first-party path, corroborated only by each frame's own internal "
                "consistency. That is stated rather than dressed up as agreement."),
            "transcription_basis": (
                "read at native resolution from each frame: the period tab, the three role scores, "
                "every scored emblem row with its multiplier and points, the period total and the "
                "period percentile"),
        },
        "accounts": {
            "labels": ["operator", "target"],
            "convention": ("`operator` is the account this repository is operated from; `target` is "
                           "the second, comparison account. No display name, avatar, account "
                           "identifier or leaderboard entry is published anywhere in this archive."),
        },
        "periods": {p: {a: _frame_record((a, p)) for a in ACCOUNTS} for p in PERIODS},
        "derived_arithmetic": {
            "per_period_differences": {p: period_differences(p) for p in PERIODS},
            "two_period_arithmetic_sums": two_period_sums(),
        },
        "not_transcribed": [
            "the account-level event point total and account percentile in the client sidebar",
            "the friend leaderboard and the global top-100 leaderboard",
            "display names and avatars",
        ],
        "not_evidence_for": [
            "any bracket prediction result",
            "an official overall Fantasy total across both periods",
            "the per-player raw statistics behind any emblem row",
        ],
    })
    return doc


def build_addendum():
    """predictions/ti2026/postmortem/fantasy_settlement_addendum.json - the retrospective."""
    closure = load_closure()
    pins = {"%s/%s" % k: pin_record(k) for k in FRAMES}
    mapping = account_mapping(pins)
    doc = ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "event": "The International 2026 (TI15)",
        "record": "post-seal Fantasy settlement addendum",
        "created_at": CREATED_AT,
        "update_type": "post_seal_first_party_evidence_addendum",
        "original_closure_status": "OFFICIAL_FANTASY_OUTCOME_NOT_ARCHIVED",
        "current_status": "OFFICIAL_FANTASY_OUTCOME_ARCHIVED",
        "what_this_is_not": [
            "not a reopening of Fantasy research, optimisation, rerolls or model selection",
            "not a re-fit: no coefficient, value table or decision rule was touched",
            "not a correction of the sealed closure, which remains valid as the knowledge state it "
            "recorded",
            "not a calibration claim: two accounts over two periods cannot support one",
        ],
        "sealed_artifacts_untouched": [
            "predictions/ti2026/postmortem/fantasy_closure.json",
            "predictions/ti2026/fantasy/",
            "predictions/ti2026/playoffs/ti15_main_event_prediction.json",
        ],
        "evidence": [
            {"evidence_id": EVIDENCE[k]["evidence_id"], "account_role": k[0], "period": k[1],
             "sha256": EVIDENCE[k]["sha256"], "raw_evidence_public": False}
            for k in sorted(EVIDENCE, key=lambda k: EVIDENCE[k]["evidence_id"])],
        "account_mapping": mapping,
        "configuration_pins": pins,
        "official_results": {
            p: {a: {"total": FRAMES[(a, p)]["displayed_total"],
                    "percentile_pct": FRAMES[(a, p)]["displayed_percentile_pct"],
                    "roles": {r: FRAMES[(a, p)]["roles"][r]["displayed_score"] for r in ROLES}}
                for a in ACCOUNTS} for p in PERIODS},
        "derived_differences": {p: period_differences(p) for p in PERIODS},
        "two_period_arithmetic_sums": two_period_sums(),
        "frozen_vs_realized": {
            "main_event": frozen_comparison(closure),
            "group_stage": group_stage_comparison(),
        },
        "structural_attribution": structural_attribution(),
        "zero_scoring_emblems": dead_slots(),
        "unknowns": {
            "per_player_raw_statistics": "UNKNOWN - the settlement shows scored points per emblem, "
                                         "not the underlying counts",
            "which_series_set_each_role_period_score": "UNKNOWN - the role-period score is the best "
                                                       "series, and the frames do not say which",
            "opportunity_from_number_of_games": "UNKNOWN where the teams differed; not separable "
                                                "from banner construction in the support role",
            "group_stage_forecast_accuracy": "NOT APPLICABLE - no frozen two-account group-stage "
                                             "forecast exists",
            "leaderboard_population": "UNCHANGED - the closure's refusal to model the Fantasy "
                                      "leaderboard population stands; the client's own percentile "
                                      "is archived as a displayed fact, not as an estimate",
        },
        "does_not_prove": [
            "that the Fantasy value model is calibrated - the level comparison is not an error "
            "measurement, because three statistics were excluded from the estimator by construction",
            "that the decision rule was right - two accounts, one event, one realization",
            "that any 2027 parameter should change - nothing here is a tuning signal",
            "that the group-stage outcome validates or refutes anything: it had no frozen forecast",
        ],
        "ti2027_implication": {
            "action": "capture the settlement view for every Fantasy period and every compared "
                      "account, immediately after each period settles",
            "why": "the settlement view is the only artifact that exposes the scored contribution of "
                   "statistics that are unobservable from public match data, and it exposes points "
                   "per emblem, which is a free exact check on the value model. TI2026 obtained it "
                   "only after the closure was sealed.",
            "not_a_parameter_change": True,
        },
    })
    return doc


# --------------------------------------------------------------------------- 6. public evidence index
def evidence_records():
    """Privacy-safe public records for the four new captures, in evidence-id order."""
    out = []
    for key in sorted(EVIDENCE, key=lambda k: EVIDENCE[k]["evidence_id"]):
        account, period = key
        e, fr = EVIDENCE[key], FRAMES[key]
        out.append({
            "evidence_id": e["evidence_id"],
            "media_type": "image/png",
            "sha256": e["sha256"],
            "bytes": e["bytes"],
            "pixels": e["pixels"],
            "evidence_phase": "post_event",
            "evidence_scope": "fantasy_settlement",
            "period": period,
            "account_role": account,
            "source_type": "first_party_in_client_capture",
            "source_tier": 1,
            "operator_supplied": True,
            "network_access_used": False,
            "raw_evidence_public": False,
            "raw_evidence_storage": "private_local_external",
            "reason_not_committed": (
                "the frame also shows the account's Steam persona, a friend leaderboard with other "
                "people's display names, avatars, and the account-level event point total and "
                "percentile. None of that is evidence for anything this repository claims."),
            "used_in_original_production": False,
            "valid_production_input": False,
            "production_use": "none. This is post-event truth and must never enter a TI2026 fit.",
            "observed_after_prediction": True,
            "capture_time_basis": (
                "not recorded in the image. Bounded below by the settlement of this Fantasy period, "
                "which the displayed period score presupposes."),
            "public_safe_transcription": {
                "view": "the client Fantasy panel for this period, settled",
                "period_tab": fr["client_tab"],
                "displayed_total": fr["displayed_total"],
                "displayed_percentile_pct": fr["displayed_percentile_pct"],
                "role_scores": {r: fr["roles"][r]["displayed_score"] for r in ROLES},
                "role_deployment": {r: {"team": fr["roles"][r]["team"],
                                        "players": fr["roles"][r]["players"]} for r in ROLES},
                "coach_title": fr["coach"],
                "emblems": {r: fr["roles"][r]["emblems"] for r in ROLES},
            },
            "scope_limits": {
                "one_account_one_period": (
                    "this frame is evidence for this account and this period only. It says nothing "
                    "about the other account, the other period, or any bracket prediction."),
                "percentile_is_period_scoped": (
                    "the percentile shown is the Fantasy leaderboard percentile for this period. It "
                    "is not the account-level percentile in the sidebar, which is a different "
                    "quantity and is deliberately not transcribed."),
                "not_evidence_for": ["bracket prediction settlement",
                                     "an official overall Fantasy total across periods",
                                     "per-player raw statistics behind any emblem row"],
                "no_recomputation_path": (
                    "an official Fantasy score cannot be recomputed by this project, so unlike the "
                    "bracket settlement this figure has one first-party path and no independent "
                    "derivation. Its only corroboration is the frame's internal consistency: emblem "
                    "rows sum to the role score and role scores sum to the displayed total, both "
                    "within display rounding."),
            },
            "deliberately_not_transcribed": (
                "the account-level event point total and percentile, the friend leaderboard, the "
                "global top-100 leaderboard, and all display names and avatars"),
        })
    return out


def update_index(path=None, write=True):
    """Append the four records to the public evidence index. Idempotent; never edits an old record."""
    path = path or INDEX
    idx = load_index(path)
    have = {e["evidence_id"] for e in idx["evidence"]}
    added = [r for r in evidence_records() if r["evidence_id"] not in have]
    idx["evidence"].extend(added)

    # the private archive gained a third subdirectory when the settlement frames were filed, and the
    # exclusion list has to distinguish the account-level sidebar figures it always meant from the
    # Fantasy period percentile this addendum publishes as a settlement fact
    idx["private_archive_layout"] = (
        "<private evidence root>/ti2026/{pre_event,post_event,fantasy}/ plus "
        "manifest.private.json. The absolute location is deliberately not recorded here; it is an "
        "operator-local path.")
    idx["excluded_from_this_file"] = [
        "absolute filesystem paths to the private archive",
        "account or friend display names",
        "avatars or any person identity",
        "Steam or account identifiers",
        "leaderboard entries",
        "the account-level event point total and account percentile shown in the client sidebar. "
        "This is NOT the Fantasy period score or its Fantasy-leaderboard percentile, which are "
        "archived as settlement facts under evidence ids ti2026-ev-007 to ti2026-ev-010.",
    ]
    idx["fantasy_settlement_provenance"] = {
        "claim": "the official Fantasy period settlement for two accounts across both TI2026 periods",
        "evidence_ids": [r["evidence_id"] for r in evidence_records()],
        "independent_paths": 1,
        "why_only_one": (
            "an official Fantasy score cannot be recomputed from any source this project holds: "
            "madstone, watchers_taken and lotuses_grabbed are unobservable in public match data. The "
            "bracket settlement's three-way agreement has no counterpart here."),
        "corroboration_available": (
            "within-frame only: each frame's emblem rows sum to its role score and its role scores "
            "sum to its displayed total, both within display rounding. Enforced in code."),
        "status": "single first-party path, internally consistent",
    }
    # The committed index is hand-formatted, with compact inline arrays a json.dump round-trip would
    # expand across the whole file. So when the file already says what it should say, leave its bytes
    # alone: a four-record append must not read as a six-hundred-line rewrite in review.
    if write and (added or load_index(path) != idx):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(idx, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    return idx, [r["evidence_id"] for r in added]


# --------------------------------------------------------------------------- entry point
def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return path


def main():
    ap = argparse.ArgumentParser(description="archive the official TI2026 Fantasy settlement")
    ap.add_argument("--no-index", action="store_true",
                    help="do not touch the public evidence index")
    a = ap.parse_args()

    assert_reconciled()
    mapping = account_mapping()
    if mapping["status"] != "ACCOUNT_MAPPING_PROVEN":
        raise SystemExit(f"ACCOUNT_MAPPING_UNRESOLVED: {mapping['unresolved']}")

    _write(RESULTS, build_results())
    _write(ADDENDUM, build_addendum())
    print(f"wrote {RESULTS}\nwrote {ADDENDUM}")
    if not a.no_index:
        _, added = update_index()
        print(f"evidence index: {'appended ' + ', '.join(added) if added else 'already current'}")

    for p in PERIODS:
        d = period_differences(p)
        print(f"  {p:12s} operator {d['operator_total']:>10.2f}   target {d['target_total']:>10.2f}"
              f"   target-operator {d['target_minus_operator']:+.2f}")
    fc = frozen_comparison(load_closure())
    print(f"  main-event ordering {'CORRECT' if fc['account_ordering']['direction_correct'] else 'WRONG'}"
          f", role directions {fc['role_directions_correct']}/{fc['role_directions_total']}")
    g = fc["gap_decomposition"]
    print(f"  gap {g['realized_gap']:+.2f} = frozen {g['frozen_estimate_gap']:+.2f} "
          f"+ excluded terms {g['excluded_term_gap']:+.2f} + residual {g['residual']:+.2f}")


if __name__ == "__main__":
    main()
