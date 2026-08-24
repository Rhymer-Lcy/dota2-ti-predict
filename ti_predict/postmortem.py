"""Post-event evaluation of the frozen TI2026 Main Event bracket prediction.

This module reads two things and invents neither:

  the SUBMITTED slate   from the committed pre-event artifact
                        predictions/ti2026/playoffs/ti15_main_event_prediction.json;
  the REALIZED bracket  from the post-event archive data/ti2026/outcomes/main_event_results.json.

Everything else is derived. In particular the official result is recomputed - node by node, against
the committed scoring vector - rather than copied from the client. The first-party in-client
settlement is then used as an independent cross-check, and a disagreement is a hard failure. A
number that is simultaneously derived from the record and confirmed by the client is worth far more
than either alone, and hard-coding the client's figure would have thrown that away.

Two distinctions are load-bearing and are kept apart everywhere below.

OFFICIAL CORRECTNESS vs PATH CORRECTNESS. The client credits a node when the team you selected there
actually won that node's real series. It does not require the two participants to be the ones you
predicted. So a pick can earn credit at a node whose matchup you got wrong, and a pick can fail at a
node its team never even reached. The official count is authoritative; the path taxonomy is a
diagnostic that explains it and can never override it.

POINT ESTIMATE vs UNCERTAINTY-INTEGRATED. The production optimiser scored slates against a bootstrap
average over parameter draws. The probabilities recomputed here for actually-played matchups are
point estimates from the single frozen serve state. They are labelled as such and are never
presented as the bootstrap-averaged object.

No network. Deterministic. Run `python -m ti_predict.postmortem`.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ti_predict import bracket as bk
from ti_predict import chronology as ch
from ti_predict import ti15_results as tr
from ti_predict.series import series_win_prob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTION = os.path.join(REPO, "predictions", "ti2026", "playoffs",
                          "ti15_main_event_prediction.json")
OUTCOMES = os.path.join(REPO, "data", "ti2026", "outcomes", "main_event_results.json")
SETTLEMENT = os.path.join(REPO, "data", "ti2026", "evidence", "private_evidence_index.json")
POSTMORTEM_DIR = os.path.join(REPO, "predictions", "ti2026", "postmortem")
FROZEN_STATE = os.path.join(POSTMORTEM_DIR, "frozen_serve_state.json")
EVALUATION = os.path.join(POSTMORTEM_DIR, "bracket_evaluation.json")

SCHEMA_VERSION = 1
CREATED_AT = "2026-08-24T02:42:00Z"

# Mutually exclusive and exhaustive: every node lands in exactly one bucket.
TAXONOMY = {
    "OFFICIAL_CORRECT_PATH_EXACT":
        "credited, and the realized participants were exactly the ones predicted",
    "OFFICIAL_CORRECT_PATH_DIVERGED":
        "credited even though the realized participants were not the ones predicted - the selected "
        "team reached this node by a different route than forecast, and still won it",
    "OFFICIAL_WRONG_LOCAL_PATH_EXACT":
        "not credited, the participants were exactly as predicted, and the selected team lost. A "
        "genuine local winner error with no upstream excuse - a root miss",
    "OFFICIAL_WRONG_LOCAL_PATH_DIVERGED":
        "not credited, but the selected team did play this node - it lost to an opponent that an "
        "upstream miss had substituted. Part local, part inherited",
    "OFFICIAL_WRONG_PROPAGATED":
        "not credited, and the selected team was not one of the two teams that actually played this "
        "node. The error is entirely inherited from an upstream path miss",
}
CORRECT_TAGS = ("OFFICIAL_CORRECT_PATH_EXACT", "OFFICIAL_CORRECT_PATH_DIVERGED")


# --------------------------------------------------------------------------- loading
def load_prediction(path=None):
    """The frozen pre-event artifact. Read-only; this module never writes to it."""
    with open(path or PREDICTION, encoding="utf-8") as fh:
        return json.load(fh)


def load_outcomes(path=None):
    """The post-event archive, with its own marker verified."""
    path = path or OUTCOMES
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not ch.is_post_event_document(doc):
        raise SystemExit(f"{path} does not declare itself post-event; refusing to use it as "
                         "outcome truth, because an unmarked outcome file is exactly the kind of "
                         "document that later leaks into a fit")
    if len(doc["series"]) != 14:
        raise SystemExit(f"the Main Event archive must hold 14 series, found {len(doc['series'])}")
    return doc


def submitted_slate(art):
    """{selection_id: canonical pick} straight from the committed artifact."""
    return {int(s["selection_id"]): s["pick"] for s in art["primary_slate"]}


def predicted_matchups(art):
    """{selection_id: frozenset(predicted participants)} from the committed artifact."""
    return {int(s["selection_id"]): frozenset(s["predicted_matchup"]) for s in art["primary_slate"]}


# --------------------------------------------------------------------------- reconciliation
def reconcile(doc, topo=None, seats=None):
    """Re-derive the node assignment from the bracket graph and assert the archive matches.

    The archive's per-series node labels are not trusted on sight: the 14 records are re-placed by
    propagating the verified topology from the archived opening seating, and the result must agree
    with what the file says. This turns the archive into a self-checking document.
    """
    topo = topo or bk.load_topology()
    seats = seats or {nid: tuple(tr.canon(x) for x in d) for nid, d in tr.UBQF.items()}
    bag = {i: s for i, s in enumerate(doc["series"])}

    participants, winner, loser, used, placed = dict(seats), {}, {}, set(), {}
    for nid in topo["order"]:
        if nid not in participants:
            participants[nid] = tuple(winner[s] if t == "W" else loser[s]
                                      for s, t in topo["inputs"][nid])
        want, clinch = frozenset(participants[nid]), (topo["best_of"][nid] + 1) // 2
        hits = [i for i, s in bag.items()
                if i not in used and frozenset(s["participants_canonical"]) == want
                and s["series_score"]["winner_maps"] == clinch]
        if len(hits) != 1:
            raise SystemExit(f"node {nid}: {len(hits)} archived series match participants "
                             f"{sorted(want)} with a best-of-{topo['best_of'][nid]} clinch; the "
                             "archive is not a coherent bracket")
        i = hits[0]
        used.add(i)
        s = bag[i]
        if s["winner"] not in want or s["loser"] not in want or s["winner"] == s["loser"]:
            raise SystemExit(f"node {nid}: archived winner/loser are not its two participants")
        for src, _ in topo["inputs"][nid]:
            if s["start_time_epoch"] < placed[src]["start_time_epoch"]:
                raise SystemExit(f"node {nid} starts before its input node {src}")
        winner[nid], loser[nid], placed[nid] = s["winner"], s["loser"], s
        if s["node_id"] != nid or s["selection_id"] != topo["node_to_selection"][nid]:
            raise SystemExit(f"archived series {s['selection_id']} claims node {s['node_id']} but "
                             f"the bracket places it at node {nid}")
    if len(used) != 14:
        raise SystemExit(f"only {len(used)} of 14 archived series could be placed")
    if doc["champion"] != winner[topo["gf"]]:
        raise SystemExit(f"archive declares champion {doc['champion']} but the bracket resolves to "
                         f"{winner[topo['gf']]}")
    return {"topo": topo, "seats": seats, "winner": winner, "loser": loser,
            "participants": participants, "series": placed}


# --------------------------------------------------------------------------- official evaluation
def evaluate_official(art, rec):
    """Node-by-node official evaluation. Correctness is computed, never read off the client."""
    topo, vec = rec["topo"], bk.verify_scoring_vector()["vector"]
    picks, pred = submitted_slate(art), predicted_matchups(art)
    nodes = []
    for nid in sorted(topo["order"], key=lambda n: topo["node_to_selection"][n]):
        sel = topo["node_to_selection"][nid]
        pick, w = picks[sel], rec["winner"][nid]
        actual = frozenset((w, rec["loser"][nid]))
        correct = pick == w
        path_exact = pred[sel] == actual
        present = pick in actual
        if correct:
            tag = "OFFICIAL_CORRECT_PATH_EXACT" if path_exact else "OFFICIAL_CORRECT_PATH_DIVERGED"
        elif not present:
            tag = "OFFICIAL_WRONG_PROPAGATED"
        elif path_exact:
            tag = "OFFICIAL_WRONG_LOCAL_PATH_EXACT"
        else:
            tag = "OFFICIAL_WRONG_LOCAL_PATH_DIVERGED"
        s = rec["series"][nid]
        nodes.append({
            "selection_id": sel, "node_id": nid, "round": topo["label"][nid],
            "client_series": topo["series_name"][nid], "best_of": topo["best_of"][nid],
            "submitted_pick": pick,
            "predicted_matchup": sorted(pred[sel]),
            "realized_matchup": sorted(actual),
            "realized_winner": w, "realized_loser": rec["loser"][nid],
            "realized_score": f"{s['series_score']['winner_maps']}-{s['series_score']['loser_maps']}",
            "start_time_utc": s["start_time_utc"],
            "official_credit": correct,
            "pick_was_a_participant": present,
            "matchup_as_predicted": path_exact,
            "classification": tag,
        })
    n_correct = sum(1 for n in nodes if n["official_credit"])
    return {
        "nodes": nodes,
        "official_correct": n_correct,
        "official_incorrect": len(nodes) - n_correct,
        "total_nodes": len(nodes),
        "official_score": int(vec[n_correct]),
        "scoring_vector": vec,
        "scoring_semantics": ("the client credits a selection when the team selected at that node "
                              "won that node's realized series; it does not require the realized "
                              "participants to equal the predicted participants"),
        "taxonomy_counts": {k: sum(1 for n in nodes if n["classification"] == k) for k in TAXONOMY},
        "taxonomy_definitions": TAXONOMY,
    }


def exact_matchup_diagnostic(ev):
    """A hypothetical stricter rule, retained only to quantify path error. NOT the official rule."""
    n = sum(1 for x in ev["nodes"] if x["official_credit"] and x["matchup_as_predicted"])
    return {
        "hypothetical_correct": n,
        "definition": "nodes where the predicted participant pair AND the winner were both right",
        "status": "DIAGNOSTIC ONLY",
        "is_the_official_rule": False,
        "must_not_be_called": ["official accuracy", "evidence of a specification mismatch"],
        "why_it_is_kept": ("it separates 'the model called the winner' from 'the model called the "
                           "whole path', which is the quantity the bracket propagation destroys"),
    }


# --------------------------------------------------------------------------- frozen probabilities
def load_frozen_state(path=None):
    """The frozen pre-event serve state at full precision, as a tracked reproduction side-car."""
    with open(path or FROZEN_STATE, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["strength"], float(doc["radiant_c"]), doc


def frozen_series_prob(a, b, best_of, strength, c):
    """P(a beats b) over `best_of` maps under the frozen side-neutral form. POINT ESTIMATE."""
    d = strength[a] - strength[b]
    mp = 0.5 * (1.0 / (1.0 + math.exp(-(d + c))) + 1.0 / (1.0 + math.exp(-(d - c))))
    return series_win_prob(mp, best_of)


def probabilistic_review(art, rec, strength, c):
    """Score the frozen pre-event model on the series that were ACTUALLY played.

    Conditioning is on the realized participants, so this asks 'given these two teams met, how well
    did the pre-event model call it' - a question the bracket path cannot contaminate. No Main Event
    result updates the strengths: one frozen state scores all 14 series.
    """
    topo = rec["topo"]
    stored = {int(s["selection_id"]): s for s in art["primary_slate"]}
    rows = []
    for nid in sorted(topo["order"], key=lambda n: topo["node_to_selection"][n]):
        sel = topo["node_to_selection"][nid]
        w, l, bo = rec["winner"][nid], rec["loser"][nid], topo["best_of"][nid]
        p = frozen_series_prob(w, l, bo, strength, c)
        s = stored[sel]
        same = frozenset((s["pick"], s["opponent"])) == frozenset((w, l))
        rows.append({
            "selection_id": sel, "node_id": nid, "round": topo["label"][nid], "best_of": bo,
            "realized_matchup": [w, l], "realized_winner": w,
            "p_pre_event_actual_winner": p,
            "model_favourite": w if p >= 0.5 else l,
            "favourite_won": p >= 0.5,
            "matchup_was_in_the_submitted_slate": same,
            "artifact_stored_probability_for_this_pair": (
                s["conditional_win_prob"] if same and s["pick"] == w
                else (1.0 - s["conditional_win_prob"] if same else None)),
        })
    p = np.array([r["p_pre_event_actual_winner"] for r in rows])
    tp = art["tournament_probabilities"]
    champ = rec["winner"][topo["gf"]]
    fav = max(tp, key=lambda t: tp[t]["champion"])
    return {
        "estimator": "POINT ESTIMATE from the single frozen serve state",
        "not_the_same_as": ("the bootstrap-averaged, uncertainty-integrated probabilities the "
                            "production optimiser maximised against. Those integrate 1000 "
                            "series-blocked parameter draws; these do not, and the two must not be "
                            "quoted as if interchangeable"),
        "conditioning": "each series is scored given the participants that actually played it",
        "sequential_updating_used": False,
        "n_series": len(rows),
        "mean_brier": float(np.mean((p - 1.0) ** 2)),
        "mean_log_loss": float(np.mean(-np.log(p))),
        "favourite_accuracy": float(np.mean(p >= 0.5)),
        "mean_probability_on_actual_winner": float(np.mean(p)),
        "uninformed_baseline": {
            "rule": "p = 0.5 for every series",
            "mean_brier": 0.25,
            "mean_log_loss": float(-math.log(0.5)),
            "why_it_is_here": ("a proper score is only readable against a reference. This is the "
                               "weakest honest one. Beating it on 14 series is not a significant "
                               "result and is not claimed as one"),
        },
        "outcomes_below_threshold": {f"p_lt_{t}": int(np.sum(p < t)) for t in (0.5, 0.45, 0.4, 0.35)},
        "min_probability_on_an_actual_winner": float(p.min()),
        "max_probability_on_an_actual_winner": float(p.max()),
        "champion_pre_event_probability": {
            "actual_champion": champ,
            "probability": tp[champ]["champion"],
            "bootstrap_90ci": tp[champ]["champion_bootstrap_90ci"],
            "pre_event_favourite": fav,
            "favourite_probability": tp[fav]["champion"],
            "favourite_finished": ("runner-up" if fav == rec["loser"][topo["gf"]] else "see nodes"),
        },
        "sample_size_caveat": ("14 series. This supports descriptive statements only. It cannot "
                              "support a calibration claim, a comparison against another model, or "
                              "any parameter change."),
        "series": rows,
    }


# --------------------------------------------------------------------------- optimiser review
def optimiser_review(art, rec):
    """Realized score of the pre-existing comparators, plus where the submitted slate ranked.

    Only comparators the production run already recorded are evaluated. No new strategy is searched
    for after the fact - that would be choosing a rule using the outcome it is scored on.
    """
    topo, seats = rec["topo"], rec["seats"]
    teams, W, _PR = bk.enumerate_structure(topo, seats)
    idx = {t: i for i, t in enumerate(teams)}
    vec = np.array(bk.verify_scoring_vector()["vector"], dtype=np.int64)

    realized_vec = np.array([idx[rec["winner"][nid]] for nid in topo["order"]], dtype=np.int8)
    realized_row = bk.slate_row(W, realized_vec)
    if realized_row < 0:
        raise SystemExit("the realized bracket is not one of the enumerated coherent outcomes; "
                         "the outcome archive and the topology disagree")

    agree = (W == W[realized_row][None, :]).sum(axis=1)
    scores = vec[agree]

    def entry(name, row, pre_score, pre_correct, note=None):
        row = int(row)
        e = {"comparator": name, "slate_row": row,
             "pre_event_expected_score": pre_score, "pre_event_expected_correct": pre_correct,
             "realized_correct": int(agree[row]), "realized_official_score": int(scores[row])}
        if note:
            e["note"] = note
        return e

    o = art["optimization"]
    primary = int(o["max_expected_official_score"]["row"])
    comparators = [
        entry("production primary: max E[official score] (SUBMITTED)", primary,
              o["max_expected_official_score"]["expected_score"],
              o["max_expected_official_score"]["expected_correct"],
              "this is the slate that was actually submitted"),
        entry("max E[correct]", o["max_expected_correct"]["row"],
              o["max_expected_correct"]["expected_score"],
              o["max_expected_correct"]["expected_correct"],
              "also the recorded second-best-overall slate; differs from the primary only at "
              "selection 810"),
        entry("greedy coherent favourite", o["greedy_coherent_favourite"]["row"],
              o["greedy_coherent_favourite"]["expected_score"],
              o["greedy_coherent_favourite"]["expected_correct"],
              "take the model favourite at every node in bracket order"),
        entry("best slate with a different champion",
              art["runner_up"]["best_with_a_different_champion"]["row"],
              art["runner_up"]["best_with_a_different_champion"]["expected_score"],
              art["runner_up"]["best_with_a_different_champion"]["expected_correct"],
              "champion " + art["runner_up"]["best_with_a_different_champion"]["champion"]),
    ]
    pe = o["point_estimate_check"]["argmax_row_under_point_estimate"]
    comparators.append(entry("point-estimate optimum", pe, None, None,
                             "identical slate to the primary" if pe == primary else "differs"))
    comparators.append(entry("oracle: the realized bracket itself", realized_row, None, None,
                             "ex-post upper bound, not an available strategy"))

    ps = int(scores[primary])
    above = int((scores > ps).sum())
    tied = int((scores == ps).sum())
    return {
        "objective_as_specified": o["objective"],
        "candidates": int(W.shape[0]),
        "realized_outcome_row": realized_row,
        "comparators": comparators,
        "submitted_slate_rank": {
            "realized_score": ps,
            "slates_scoring_strictly_higher": above,
            "slates_tied_at_this_score": tied,
            "rank_interval": [above + 1, above + tied],
            "percentile_interval": [round(100.0 * (1.0 - (above + tied) / len(scores)), 3),
                                    round(100.0 * (1.0 - above / len(scores)), 3)],
            "tie_handling": ("realized score is a coarse integer scale, so many slates tie. A "
                             "unique rank is not defined and is not invented: the interval and the "
                             "tie count are reported instead"),
        },
        "realized_score_distribution": {str(int(k)): int((agree == k).sum())
                                        for k in range(15)},
        "specification_check": {
            "production_scoring_functional": ("count the nodes at which the slate's winner equals "
                                              "the outcome's winner, then look that count up in the "
                                              "committed 15-entry scoring vector"),
            "client_settlement_semantics": ("the client credits a node when the selected team won "
                                            "that node's realized series"),
            "consistent": True,
            "evidence": ("the recomputation under the production functional reproduces the "
                         "first-party in-client settlement exactly, both in aggregate and node by "
                         "node"),
        },
        "no_ex_post_search": ("only comparators recorded by the pre-event production run are "
                             "scored here. No new strategy was searched for using the realized "
                             "outcome, and the 2027 objective is not changed on one realization"),
    }


# --------------------------------------------------------------------------- model-miss diagnosis
def model_miss_diagnosis(art, rec, strength, c):
    """What the frozen model actually believed about the eventual champion, and what it did not.

    FACT and HYPOTHESIS are kept in separate blocks on purpose. The facts are recomputable from the
    frozen state. The hypotheses are candidate explanations for one tournament and are explicitly
    NOT converted into parameter changes here - a single realization cannot identify which of them,
    if any, is real, and fitting a half-life or a form term to it would be hindsight tuning wearing
    a research hat.
    """
    topo = rec["topo"]
    tp, se = art["tournament_probabilities"], art["strength_evolution"]
    champ = rec["winner"][topo["gf"]]
    fav = max(tp, key=lambda t: tp[t]["champion"])
    path = []
    for nid in sorted(topo["order"], key=lambda n: rec["series"][n]["start_time_epoch"]):
        if champ not in (rec["winner"][nid], rec["loser"][nid]):
            continue
        opp = rec["loser"][nid] if rec["winner"][nid] == champ else rec["winner"][nid]
        path.append({
            "selection_id": topo["node_to_selection"][nid], "round": topo["label"][nid],
            "opponent": opp, "won": rec["winner"][nid] == champ,
            "p_pre_event_champion_wins": frozen_series_prob(champ, opp, topo["best_of"][nid],
                                                            strength, c),
        })
    survived = [s for s in path if s["won"]]
    joint = 1.0
    for s in survived:
        joint *= s["p_pre_event_champion_wins"]
    return {
        "fact": {
            "actual_champion": champ,
            "pre_event_title_probability": tp[champ]["champion"],
            "pre_event_title_probability_90ci": tp[champ]["champion_bootstrap_90ci"],
            "pre_event_rank_by_title_probability": 1 + sorted(
                tp, key=lambda t: -tp[t]["champion"]).index(champ),
            "pre_event_favourite": fav,
            "pre_event_favourite_title_probability": tp[fav]["champion"],
            "pre_event_favourite_actual_finish": "runner-up",
            "frozen_latent_strength": se[champ]["serve"],
            "strength_rank_of_champion_among_the_eight": 1 + sorted(
                se, key=lambda t: -se[t]["serve"]).index(champ),
            "strength_gap_to_the_strongest": se[fav]["serve"] - se[champ]["serve"],
            "movement_attributable_to_ti15_group_play": se[champ]["delta_attributable_to_ti15"],
            "champion_path": path,
            "series_won_on_the_title_run": len(survived),
            "product_of_pre_event_probabilities_along_the_winning_path": joint,
            "note_on_that_product": ("this is the pre-event probability of exactly this route, not "
                                     "of the title: the model gave the champion "
                                     f"{tp[champ]['champion']:.4f} across all routes. A route this "
                                     "long is improbable for anyone, including the favourite"),
        },
        "what_the_model_got_right_about_the_champion": (
            "it did not consider the champion a long shot in absolute terms - "
            f"{tp[champ]['champion']:.1%} over eight teams is above the uniform 12.5% floor only "
            "for the top four, and the champion ranked fifth. The model placed it mid-field, and a "
            "mid-field team won."),
        "what_the_model_got_wrong": (
            "it ranked the champion fifth of eight by latent strength at serve time, and gave the "
            "eventual runner-up more than four times the title probability. The single largest "
            "miss on the board is the Grand Final itself, where the model put "
            f"{frozen_series_prob(champ, rec['loser'][topo['gf']], 5, strength, c):.4f} on the "
            "team that won it - the lowest probability it assigned to any realized winner."),
        "hypothesis": [
            {"hypothesis": "recency: a 90-day half-life may discount late-window form too slowly",
             "status": "UNTESTED", "would_require": "multi-event out-of-sample evidence, not one TI",
             "explicitly_not_done": "no half-life change is proposed or made"},
            {"hypothesis": ("sequential assimilation: updating strengths as the Main Event unfolds "
                            "might have caught the champion's run"),
             "status": "EXPLORED POST HOC ONLY",
             "artifact": "predictions/ti2026/postmortem/sequential_posthoc.json (if generated)",
             "explicitly_not_done": "the production forecast is unchanged and is not re-issued"},
            {"hypothesis": "bracket-specific or best-of-5 form is not captured by a map-level rating",
             "status": "UNTESTED", "would_require": "a stage-labelled multi-year corpus"},
            {"hypothesis": "roster or patch adaptation inside the event window",
             "status": "UNTESTED", "would_require": "roster and patch metadata the project does not hold"},
        ],
        "prohibited_inference": (
            "None of the above may become a TI2027 parameter change on the strength of TI2026. "
            "One tournament identifies nothing: with 14 series, a model that is genuinely better "
            "and a model that is genuinely worse produce overlapping score distributions. The "
            "correct output of this section is a research question with a pre-registered test, not "
            "a coefficient."),
    }


# --------------------------------------------------------------------------- settlement check
BRACKET_VIEW_EVIDENCE = "ti2026-ev-003"      # per-node marks and the correct count
SUMMARY_VIEW_EVIDENCE = "ti2026-ev-006"      # correct, incorrect and the awarded points


def settlement_from_index(path=None):
    """The public-safe settlement transcriptions, keyed by evidence id.

    Two separate first-party client views carry settlement facts and they prove different things:
    the bracket view carries the per-node marks, the summary view carries the awarded points. Both
    are required, and picking whichever appears first would silently drop one.
    """
    with open(path or SETTLEMENT, encoding="utf-8") as fh:
        doc = json.load(fh)
    found = {}
    for e in doc["evidence"]:
        t = e.get("public_safe_transcription", {})
        if "main_event_prediction_settlement" in t:
            found[e["evidence_id"]] = t["main_event_prediction_settlement"]
    for eid in (BRACKET_VIEW_EVIDENCE, SUMMARY_VIEW_EVIDENCE):
        if eid not in found:
            raise SystemExit(f"the public evidence index carries no Main Event settlement "
                             f"transcription for {eid}; both the bracket view and the settlement "
                             "summary view are required")
    return found


def cross_check_settlement(ev, path=None):
    """The derived result must equal BOTH first-party client views. Any disagreement aborts.

    Three independent paths reach the same settlement and all three are gated here:
      A  the bracket view      - the correct count and a mark on each of the 14 nodes;
      B  the summary view      - the correct count, the incorrect count and the awarded points;
      C  this recomputation    - from the frozen slate, the realized winners and the committed
                                 scoring vector, using no image at all.
    """
    s = settlement_from_index(path)
    bracket, summary = s[BRACKET_VIEW_EVIDENCE], s[SUMMARY_VIEW_EVIDENCE]
    problems = []

    def cmp(label, got, want, src):
        if got != want:
            problems.append(f"{label}: {src} {got} vs derived {want}")

    cmp("correct", bracket["correct_predictions"], ev["official_correct"], "bracket view")
    cmp("incorrect", bracket["incorrect_predictions"], ev["official_incorrect"], "bracket view")
    cmp("total", bracket["total_predictions"], ev["total_nodes"], "bracket view")
    cmp("correct", summary["correct_predictions"], ev["official_correct"], "summary view")
    cmp("incorrect", summary["incorrect_predictions"], ev["official_incorrect"], "summary view")
    cmp("points", summary["official_points_earned"], ev["official_score"], "summary view")

    per = {int(k): v for k, v in bracket.get("per_node_credit", {}).items()}
    for n in ev["nodes"]:
        if n["selection_id"] in per and per[n["selection_id"]] != n["official_credit"]:
            problems.append(f"selection {n['selection_id']}: bracket view credit "
                            f"{per[n['selection_id']]} vs derived {n['official_credit']}")
    if problems:
        raise SystemExit("SETTLEMENT MISMATCH - the deterministic recomputation does not reproduce "
                         "the first-party client settlement:\n  " + "\n  ".join(problems))
    return {
        "evidence_ids": [BRACKET_VIEW_EVIDENCE, SUMMARY_VIEW_EVIDENCE],
        "evidence_id": SUMMARY_VIEW_EVIDENCE,
        "source_tier": 1,
        "paths": {
            "A_client_bracket_view": {
                "evidence_id": BRACKET_VIEW_EVIDENCE,
                "correct": bracket["correct_predictions"],
                "total": bracket["total_predictions"],
                "per_node_marks": len(per),
                "establishes_points": False,
            },
            "B_client_settlement_summary_view": {
                "evidence_id": SUMMARY_VIEW_EVIDENCE,
                "correct": summary["correct_predictions"],
                "incorrect": summary["incorrect_predictions"],
                "points": summary["official_points_earned"],
                "establishes_points": True,
            },
            "C_deterministic_recomputation": {
                "correct": ev["official_correct"],
                "incorrect": ev["official_incorrect"],
                "points": ev["official_score"],
                "inputs": ["frozen submitted slate", "realized node winners",
                           "committed official scoring vector"],
            },
        },
        "client_correct": summary["correct_predictions"],
        "client_incorrect": summary["incorrect_predictions"],
        "client_total": bracket["total_predictions"],
        "client_points": summary["official_points_earned"],
        "derived_correct": ev["official_correct"],
        "derived_incorrect": ev["official_incorrect"],
        "derived_official_score": ev["official_score"],
        "aggregate_agrees": True,
        "per_node_agrees": True,
        "per_node_marks_checked": len(per),
        "all_three_paths_agree": True,
        "provenance_status": "dual first-party plus deterministic",
    }


# --------------------------------------------------------- sequential assimilation (POST HOC ONLY)
MAIN_EVENT_SERIES_ID_BASE = 950_000_000
MAIN_EVENT_MATCH_ID_BASE = 9_950_000_000


def main_event_rows(doc):
    """Main Event results as map-level rows, STAMPED post-event so production must refuse them.

    The stamp is the point. These rows are the exact thing the chronology contract exists to keep
    out of a TI2026 fit, so they carry a marker that `chronology.assert_production_rows` rejects.
    The diagnostic below therefore cannot be run through the production `fit`; it calls the
    estimator directly, deliberately and visibly.

    Unlike the Swiss and Elimination rows, these carry OBSERVED start times from the outcome
    archive, not an imputed cadence.
    """
    rows = []
    for i, s in enumerate(sorted(doc["series"], key=lambda x: x["start_time_epoch"])):
        w, l = s["winner"], s["loser"]
        wm, lm = s["series_score"]["winner_maps"], s["series_score"]["loser_maps"]
        ts, sid = s["start_time_epoch"], MAIN_EVENT_SERIES_ID_BASE + i
        for j in range(wm + lm):
            rows.append({
                "match_id": str(MAIN_EVENT_MATCH_ID_BASE + 10 * i + j), "start_time": ts + j,
                "leagueid": tr.TI15_LEAGUE_ID, "league_name": "The International 2026",
                "series_id": sid, "team_a": w, "team_b": l, "a_won": 1 if j < wm else 0,
                "is_target": 0, "ti15_round": s["round"], "ti15_stage": "main_event",
                "side_provenance": tr.SIDE_NONE,
                "timestamp_provenance": "observed_series_start_time",
                "phase": "post_event",
                "observed_after_prediction": True,
            })
    return rows


def sequential_posthoc(art=None, doc=None):
    """Would updating the strengths DURING the Main Event have called it better? Diagnostic only.

    Three arms, all with the frozen estimator, half-life, lambda and side-neutral form unchanged.
    Only the training cutoff and the training set move:

      A  frozen        the production serve state. One fit, used for all 14 series.
      B  decay control the cutoff advances to each series' start, but no Main Event result is ever
                       added. This isolates the effect of merely moving the decay origin.
      C  assimilated   the cutoff advances AND every Main Event series that had already started is
                       in the training set.

    B exists because without it, any difference between A and C could be the decay shift rather
    than the new information, and the two would be indistinguishable.

    This is exploratory. It is scored on 14 series, it is not pre-registered, and it selects its own
    comparison after seeing the outcome. It cannot promote sequential assimilation into the 2027
    production method and is not used to.
    """
    from collections import Counter
    from ti_predict.calibrate import bt_strengths, est_c
    from ti_predict.contest_rules import PRODUCTION_HALF_LIFE_DAYS

    art = art or load_prediction()
    doc = doc or load_outcomes()
    rec = reconcile(doc)
    topo = rec["topo"]
    base, _prov = tr.augmented_universe()
    me = main_event_rows(doc)
    frozen_strength, frozen_c, _ = load_frozen_state()

    def fit_at(cutoff_ts, extra):
        """The frozen estimator, called directly. `extra` may contain post-event rows by design."""
        rows = list(base) + list(extra)
        rows.sort(key=lambda r: (r["start_time"], r["match_id"]))
        ssize = Counter(r["series_id"] for r in rows if r["series_id"])
        for r in rows:
            r["w"] = 1.0 / ssize[r["series_id"]] if r["series_id"] else 1.0
        train = [m for m in rows if m["start_time"] < cutoff_ts]
        s = bt_strengths(train, cutoff_ts, hl=float(PRODUCTION_HALF_LIFE_DAYS))
        return s, float(est_c(tr.side_labelled(train), s)), len(train)

    out = []
    for nid in sorted(topo["order"], key=lambda n: rec["series"][n]["start_time_epoch"]):
        s = rec["series"][nid]
        w, l, bo, t0 = rec["winner"][nid], rec["loser"][nid], topo["best_of"][nid], s["start_time_epoch"]
        prior = [r for r in me if r["start_time"] < t0]
        sb, cb, nb = fit_at(t0, [])
        sc, cc, nc = fit_at(t0, prior)
        out.append({
            "selection_id": topo["node_to_selection"][nid], "round": topo["label"][nid],
            "start_time_utc": s["start_time_utc"],
            "realized_matchup": [w, l],
            "main_event_series_already_completed": len({r["series_id"] for r in prior}),
            "p_A_frozen": frozen_series_prob(w, l, bo, frozen_strength, frozen_c),
            "p_B_decay_control": frozen_series_prob(w, l, bo, sb, cb),
            "p_C_assimilated": frozen_series_prob(w, l, bo, sc, cc),
            "train_maps_B": nb, "train_maps_C": nc,
        })

    def agg(key):
        p = np.array([r[key] for r in out])
        return {"mean_brier": float(np.mean((p - 1.0) ** 2)),
                "mean_log_loss": float(np.mean(-np.log(p))),
                "favourite_accuracy": float(np.mean(p >= 0.5)),
                "mean_probability_on_actual_winner": float(np.mean(p))}

    arms = {"A_frozen_production": agg("p_A_frozen"),
            "B_decay_origin_control": agg("p_B_decay_control"),
            "C_sequentially_assimilated": agg("p_C_assimilated")}
    return ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "event": "The International 2026 (TI15)",
        "record": "POST-HOC DIAGNOSTIC: would in-event sequential assimilation have scored better?",
        "status": "POST-HOC DIAGNOSTIC ONLY",
        "created_at": CREATED_AT,
        "preregistered": False,
        "changes_the_official_forecast": False,
        "promoted_to_production": False,
        "frozen_hyperparameters_unchanged": {
            "family": "B-bt", "half_life_days": 90, "lambda": 1.0, "calibration": "none",
            "map_prob": "side-neutral 0.5*(sigmoid(d+c)+sigmoid(d-c))",
            "note": "only the training cutoff and the training set differ between arms",
        },
        "arms": {
            "A_frozen_production": "the served state; one fit for all 14 series",
            "B_decay_origin_control": "cutoff advances to each series' start; NO Main Event results",
            "C_sequentially_assimilated": "cutoff advances AND completed Main Event results included",
        },
        "why_arm_B_exists": ("without it, an A-to-C difference could be the moving decay origin "
                             "rather than the new information"),
        "summary": arms,
        "series": out,
        "interpretation_limits": [
            "14 series, and the later ones share teams, so the observations are not independent",
            "the comparison was chosen after the outcome was known; it is not a test",
            "no confidence interval is quoted because none would be honest at this size",
            "cross-event evidence over several tournaments is what would settle this",
        ],
        "required_next_step_if_pursued": (
            "pre-register the arm, the metric and the decision rule, then evaluate it on a corpus "
            "of completed events that were never used to design it"),
    })


# --------------------------------------------------------------------------- state reproduction
def refit_frozen_state(out=None):
    """Recompute the frozen serve state at full precision and write the tracked side-car.

    Needs the local (git-ignored, regenerable) rating universe, so it is an explicit maintenance
    command rather than part of the normal run. Everything downstream reads the written file, which
    keeps the evaluation reproducible from tracked content alone.
    """
    from ti_predict import predict_main_event as pme
    art = load_prediction()
    st = pme.build_states()["C_serve"]
    strength, c = st["strength"], st["c"]
    checks = []
    worst = 0.0
    for s in art["primary_slate"]:
        p = frozen_series_prob(s["pick"], s["opponent"], s["best_of"], strength, c)
        d = abs(p - s["conditional_win_prob"])
        worst = max(worst, d)
        checks.append({"selection_id": s["selection_id"], "abs_difference": d})
    if worst > 1e-12:
        raise SystemExit(f"refit does not reproduce the artifact's stored probabilities "
                         f"(worst |d| = {worst:g}); the frozen state has drifted")
    seats = {nid: tuple(tr.canon(x) for x in d) for nid, d in tr.UBQF.items()}
    eight = sorted({t for pair_ in seats.values() for t in pair_})
    doc = ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "event": "The International 2026 (TI15)",
        "record": "frozen PRE-EVENT serve state, reproduced at full precision",
        "content_phase": "pre_event",
        "recorded_phase": "post_event",
        "created_at": CREATED_AT,
        "what_this_is": (
            "the exact strengths and radiant coefficient the production run served from. The "
            "committed prediction artifact stores them rounded to four decimals, which is not "
            "enough to reproduce a probability for a matchup the slate never contained. This "
            "side-car carries them at full precision so the post-event evaluation is reproducible "
            "from tracked files, without the git-ignored rating universe."),
        "why_it_is_in_the_post_event_namespace": (
            "the numbers are pre-event, but the file was written after the tournament. Filing it "
            "with the postmortem keeps the pre-event snapshot byte-identical to what was served, "
            "and the marker keeps it out of any production path."),
        "reproduction": {
            "command": "python -m ti_predict.postmortem --refit-frozen-state",
            "source": "ti_predict.predict_main_event.build_states()['C_serve']",
            "cutoff": st["cutoff"],
            "train_maps": st["train_maps"],
            "data": st["data"],
            "requires": "data/ti2026/processed/universe_maps.csv (git-ignored, regenerable)",
        },
        "verification": {
            "claim": ("this state reproduces every conditional_win_prob stored in the committed "
                      "pre-event artifact"),
            "checked": len(checks),
            "worst_absolute_difference": worst,
            "tolerance": 1e-12,
            "passed": True,
        },
        "radiant_c": c,
        "strength": {t: strength[t] for t in eight},
        "strength_scope": ("the eight Main Event participants. The full fit covers every team in "
                           "the rating universe; only these eight can appear in this bracket."),
    })
    out = out or FROZEN_STATE
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return out, worst


# --------------------------------------------------------------------------- assembly
def build(art=None, doc=None):
    """The complete post-event evaluation as one deterministic dict."""
    art = art or load_prediction()
    doc = doc or load_outcomes()
    rec = reconcile(doc)
    ev = evaluate_official(art, rec)
    settlement = cross_check_settlement(ev)
    strength, c, state = load_frozen_state()
    prob = probabilistic_review(art, rec, strength, c)
    opt = optimiser_review(art, rec)

    m = art["manifest"]
    out = ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "event": "The International 2026 (TI15)",
        "record": "post-event evaluation of the frozen TI2026 Main Event bracket prediction",
        "created_at": CREATED_AT,
        "deterministic": True,
        "network_used_by_this_evaluation": False,
        "production_prediction_artifact": os.path.relpath(PREDICTION, REPO).replace("\\", "/"),
        "production_prediction_status": m["status"],
        "production_code_commit": m["code_commit"],
        "production_generated_at": m["generated_at"],
        "production_data_cutoff": m["data_cutoff"],
        "frozen_model": m["model"],
        "selections_source": ("read from the committed pre-event artifact; this module holds no "
                              "second copy of the slate"),
        "outcome_source": os.path.relpath(OUTCOMES, REPO).replace("\\", "/"),
        "frozen_state_source": os.path.relpath(FROZEN_STATE, REPO).replace("\\", "/"),
        "frozen_state_verification": state["verification"],
        "official_evaluation": ev,
        "exact_matchup_diagnostic": exact_matchup_diagnostic(ev),
        "first_party_settlement_cross_check": settlement,
        "expected_vs_realized": {
            "expected_correct_pre_event": art["optimization"]["max_expected_official_score"]
                                             ["expected_correct"],
            "realized_correct": ev["official_correct"],
            "expected_score_pre_event": art["optimization"]["max_expected_official_score"]
                                           ["expected_score"],
            "realized_score": ev["official_score"],
            "predicted_champion": next(n["submitted_pick"] for n in ev["nodes"]
                                       if n["round"] == "GF"),
            "actual_champion": doc["champion"],
            "pre_event_probability_of_realizing_at_least_this_score": sum(
                v for k, v in art["optimization"]["score_distribution_of_primary"].items()
                if int(k) >= ev["official_correct"]),
            "interpretation": ("realized above expectation is a descriptive fact about one "
                               "tournament. It is not evidence of calibration, of generalization, "
                               "or that the model is better than it forecast. N = 1"),
        },
        "probabilistic_review": prob,
        "optimiser_review": opt,
        "model_miss_diagnosis": model_miss_diagnosis(art, rec, strength, c),
    })
    return out


def build_postmortem(evaluation=None):
    """The single machine-readable closure record: computed evaluation plus the authored record."""
    from ti_predict import ti2026_record as rc

    ev_doc = evaluation or build()
    art = load_prediction()
    doc = load_outcomes()
    with open(os.path.join(POSTMORTEM_DIR, "fantasy_closure.json"), encoding="utf-8") as fh:
        fantasy = json.load(fh)

    ev = ev_doc["official_evaluation"]
    exp = ev_doc["expected_vs_realized"]
    prob = ev_doc["probabilistic_review"]
    tp = art["tournament_probabilities"]
    m = art["manifest"]
    seq_path = os.path.join(POSTMORTEM_DIR, "sequential_posthoc.json")

    return ch.stamp_post_event({
        "schema_version": SCHEMA_VERSION,
        "year": 2026,
        "event": "The International 2026 (TI15)",
        "record": "TI2026 project closure: what was predicted, what happened, and what it supports",
        "created_at": CREATED_AT,

        "production_prediction_artifact": os.path.relpath(PREDICTION, REPO).replace("\\", "/"),
        "production_commit": m["code_commit"],
        "cutoff": m["data_cutoff"],
        "frozen_model": m["model"],
        "production_leakage_declarations": {
            "network_used": m["network_used"],
            "odds_used": m["odds_used"],
            "future_main_event_results_used": m["future_main_event_results_used"],
            "status": "unmodified; these describe the production run and remain true",
        },

        "predicted_champion": exp["predicted_champion"],
        "actual_champion": exp["actual_champion"],
        "predicted_champion_probability": tp[exp["predicted_champion"]]["champion"],
        "actual_champion_pre_event_probability": tp[exp["actual_champion"]]["champion"],
        "actual_champion_pre_event_probability_90ci":
            tp[exp["actual_champion"]]["champion_bootstrap_90ci"],

        "total_nodes": ev["total_nodes"],
        "official_correct_nodes": ev["official_correct"],
        "official_incorrect_nodes": ev["official_incorrect"],
        "official_score": ev["official_score"],
        "expected_correct_pre_event": exp["expected_correct_pre_event"],
        "expected_score_pre_event": exp["expected_score_pre_event"],
        "realized_correct": exp["realized_correct"],
        "realized_score": exp["realized_score"],
        "pre_event_probability_of_at_least_this_many_correct":
            exp["pre_event_probability_of_realizing_at_least_this_score"],
        "one_event_caveat": exp["interpretation"],

        "client_settlement_evidence_id":
            ev_doc["first_party_settlement_cross_check"]["evidence_id"],
        "client_settlement_cross_check": ev_doc["first_party_settlement_cross_check"],

        "node_results": [
            {k: n[k] for k in ("selection_id", "node_id", "round", "submitted_pick",
                               "predicted_matchup", "realized_matchup", "realized_winner",
                               "realized_score", "official_credit", "classification")}
            for n in ev["nodes"]],

        "path_error_taxonomy": {
            "counts": ev["taxonomy_counts"],
            "definitions": ev["taxonomy_definitions"],
            "root_local_misses": [n["selection_id"] for n in ev["nodes"]
                                  if n["classification"] == "OFFICIAL_WRONG_LOCAL_PATH_EXACT"],
            "propagated_misses": [n["selection_id"] for n in ev["nodes"]
                                  if n["classification"] == "OFFICIAL_WRONG_PROPAGATED"],
            "credited_despite_path_divergence": [
                n["selection_id"] for n in ev["nodes"]
                if n["classification"] == "OFFICIAL_CORRECT_PATH_DIVERGED"],
            "authority": ("the official 8 of 14 stands regardless of this taxonomy. The taxonomy "
                          "explains the count; it can never revise it"),
        },
        "exact_matchup_diagnostic": ev_doc["exact_matchup_diagnostic"],

        "proper_scores": {
            "brier": prob["mean_brier"],
            "log_loss": prob["mean_log_loss"],
            "favourite_accuracy": prob["favourite_accuracy"],
            "mean_actual_winner_probability": prob["mean_probability_on_actual_winner"],
            "uninformed_baseline": prob["uninformed_baseline"],
            "estimator": prob["estimator"],
            "n": prob["n_series"],
            "caveat": prob["sample_size_caveat"],
        },

        "optimiser_comparators": ev_doc["optimiser_review"]["comparators"],
        "submitted_slate_rank": ev_doc["optimiser_review"]["submitted_slate_rank"],
        "scoring_specification_check": ev_doc["optimiser_review"]["specification_check"],
        "model_miss_diagnosis": ev_doc["model_miss_diagnosis"],
        "sequential_posthoc_diagnostic": {
            "artifact": "predictions/ti2026/postmortem/sequential_posthoc.json",
            "present": os.path.exists(seq_path),
            "status": "POST-HOC DIAGNOSTIC ONLY; not promoted to any production method",
        },

        "fantasy_closure": {
            "artifact": "predictions/ti2026/postmortem/fantasy_closure.json",
            "status": fantasy["status"],
            "verdict": fantasy["final_review_verdict"],
            "difference_b_minus_a": fantasy["observed_data_plug_in_estimate"]
                                           ["difference_b_minus_a"],
            "realized_outcome": fantasy["realized_fantasy_outcome"]["status"],
        },

        "incidents": rc.INCIDENTS,
        "known_limitations": rc.KNOWN_LIMITATIONS,
        "reusable_lessons": rc.REUSABLE_LESSONS,
        "what_worked": rc.WHAT_WORKED,
        "what_this_does_not_prove": rc.DOES_NOT_PROVE,
        "ti2027_actions": rc.TI2027_ACTIONS,

        "companion_artifacts": {
            "outcome_archive": "data/ti2026/outcomes/main_event_results.json",
            "outcome_sources": "data/ti2026/outcomes/sources.json",
            "bracket_evaluation": "predictions/ti2026/postmortem/bracket_evaluation.json",
            "frozen_serve_state": "predictions/ti2026/postmortem/frozen_serve_state.json",
            "fantasy_closure": "predictions/ti2026/postmortem/fantasy_closure.json",
            "evidence_index": "data/ti2026/evidence/private_evidence_index.json",
            "narrative": "docs/TI2026_POSTMORTEM.md",
            "reuse_protocol": "docs/TI2027_REUSE_PROTOCOL.md",
        },
    })


def main():
    ap = argparse.ArgumentParser(description="post-event evaluation of the TI2026 bracket")
    ap.add_argument("--refit-frozen-state", action="store_true",
                    help="recompute the frozen serve state side-car (needs the local universe)")
    ap.add_argument("--sequential-diagnostic", action="store_true",
                    help="post-hoc only: score in-event assimilation (needs the local universe)")
    ap.add_argument("--out", default=EVALUATION)
    a = ap.parse_args()
    if a.refit_frozen_state:
        path, worst = refit_frozen_state()
        print(f"wrote {path}\nreproduces all stored probabilities, worst |d| = {worst:g}")
        return
    if a.sequential_diagnostic:
        doc = sequential_posthoc()
        out = os.path.join(POSTMORTEM_DIR, "sequential_posthoc.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print(f"wrote {out}   POST-HOC DIAGNOSTIC ONLY")
        for arm, v in doc["summary"].items():
            print(f"  {arm:28s} brier {v['mean_brier']:.4f}  logloss {v['mean_log_loss']:.4f}  "
                  f"fav {v['favourite_accuracy']:.3f}")
        return
    out = build()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    pm = os.path.join(POSTMORTEM_DIR, "ti2026_postmortem.json")
    with open(pm, "w", encoding="utf-8") as fh:
        json.dump(build_postmortem(out), fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    ev = out["official_evaluation"]
    print(f"wrote {a.out}\nwrote {pm}")
    print(f"official: {ev['official_correct']} correct / {ev['official_incorrect']} incorrect "
          f"of {ev['total_nodes']}  ->  {ev['official_score']} points")
    print("first-party settlement cross-check: PASS "
          f"({out['first_party_settlement_cross_check']['per_node_marks_checked']} node marks)")
    for k, v in ev["taxonomy_counts"].items():
        print(f"  {k:34s} {v}")


if __name__ == "__main__":
    main()
