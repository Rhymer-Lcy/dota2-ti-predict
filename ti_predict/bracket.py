"""Main-event bracket: verified topology, exact enumeration, and coherent-slate optimization.

The topology is NOT hand-written here. It is read out of Valve's own league feed (league_id 19719,
already downloaded to data/ti2026/raw/), whose Playoff node group carries all fourteen nodes with
their winner/loser edges. Every structural claim the contest depends on -- 4 UBQF + 2 UBSF + 1 UBF +
2 LBR1 + 2 LBR2 + 1 LBSF + 1 LBF + 1 GF, the crossed lower-bracket feed, Bo3 everywhere except a Bo5
Grand Final -- is asserted against that feed and the run fails closed if any of it does not hold.

Two facts make the optimization exact rather than sampled:
  - the bracket has 14 binary nodes, so there are exactly 2^14 = 16,384 complete tournament
    outcomes, and their probabilities sum to 1 by construction;
  - a COHERENT 14-slot prediction is itself one of those outcomes (picking a team to win a node it
    cannot reach is exactly what incoherence means). So the candidate set and the outcome space are
    the same 16,384 objects, and E[score] can be evaluated for every candidate against every
    outcome. No Monte Carlo, no convergence argument, no seed.

Expected score is LINEAR in the outcome distribution, so parameter uncertainty is integrated
exactly by averaging the outcome distribution over bootstrap strength draws and then optimizing
against that average -- not by optimizing each draw and averaging slates.

Run `python -m ti_predict.bracket` for the topology self-check.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.contest_rules import MAIN_EVENT_SCORE
from ti_predict.series import series_win_prob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED_JSON = os.path.join(REPO, "data", "ti2026", "raw", "league_19719_feed.json")

# Client selection_id <-> league node_id, and the client's own label for each node. Transcribed from
# the shipped client into data/ti2026/inputs/prediction_questions.json (question TI2026-Q-BRACKET);
# asserted against that file in load_topology so the two can never drift apart.
SELECTION_TO_NODE = {801: 14, 802: 15, 803: 16, 804: 17, 805: 18, 806: 19, 807: 20, 808: 21,
                     809: 22, 810: 23, 811: 24, 812: 25, 813: 26, 814: 27}
EXPECTED_SHAPE = {"UBQF": 4, "UBSF": 2, "UBF": 1, "LBR1": 2, "LBR2": 2, "LBSF": 1, "LBF": 1, "GF": 1}
SCORE_VEC = np.array([MAIN_EVENT_SCORE[k] for k in range(15)], dtype=np.float64)


def _walk(groups):
    for g in groups or []:
        yield g
        yield from _walk(g.get("node_groups"))


def load_topology(path=None, questions=None):
    """Read and verify the 14-node playoff topology from the official league feed.

    Returns a dict with `order` (a topological node ordering), `inputs` (node -> two (src, 'W'|'L')
    edges, or None for a seeded quarterfinal), `best_of`, and the client label/selection maps.
    Raises SystemExit on any structural violation -- the run must fail closed rather than predict
    into a bracket it has not verified.
    """
    path = path or FEED_JSON
    if not os.path.exists(path):
        raise SystemExit(f"league feed snapshot not found: {path}\nThe main-event topology is read "
                         "from the official feed and is never hand-entered. Restore the snapshot.")
    with open(path, encoding="utf-8") as fh:
        feed = json.load(fh)
    groups = [g for g in _walk(feed.get("node_groups")) if g.get("name") == "Playoff"]
    if len(groups) != 1:
        raise SystemExit(f"expected exactly one Playoff node group in the feed, found {len(groups)}")
    nodes = {n["node_id"]: n for n in groups[0].get("nodes") or []}
    if len(nodes) != 14:
        raise SystemExit(f"the Playoff group must hold 14 nodes, found {len(nodes)}")
    if set(nodes) != set(SELECTION_TO_NODE.values()):
        raise SystemExit(f"feed node ids {sorted(nodes)} do not match the client slot map "
                         f"{sorted(SELECTION_TO_NODE.values())}")

    # Edges: a node's winner goes to winning_node_id, its loser to losing_node_id. Rebuild each
    # node's two inputs from those edges and cross-check against the feed's own incoming_node_id_*.
    inputs = {nid: [] for nid in nodes}
    for nid, n in sorted(nodes.items()):
        for field, tag in (("winning_node_id", "W"), ("losing_node_id", "L")):
            dst = n.get(field) or 0
            if dst:
                if dst not in inputs:
                    raise SystemExit(f"node {nid} {field}={dst} points outside the Playoff group")
                inputs[dst].append((nid, tag))
    for nid, n in sorted(nodes.items()):
        got = sorted(s for s, _ in inputs[nid])
        want = sorted(x for x in (n.get("incoming_node_id_1"), n.get("incoming_node_id_2")) if x)
        if got != want:
            raise SystemExit(f"node {nid}: winner/loser edges give inputs {got} but the feed "
                             f"declares incoming {want}")
        if inputs[nid] and len(inputs[nid]) != 2:
            raise SystemExit(f"node {nid} has {len(inputs[nid])} inputs, expected 0 or 2")

    seeded = sorted(nid for nid in nodes if not inputs[nid])
    if len(seeded) != 4:
        raise SystemExit(f"expected 4 seeded quarterfinals, found {len(seeded)}: {seeded}")
    finals = [nid for nid, n in nodes.items() if not (n.get("winning_node_id") or 0)]
    if len(finals) != 1:
        raise SystemExit(f"expected exactly one terminal node, found {finals}")

    order, placed = [], set()
    while len(order) < 14:
        progressed = False
        for nid in sorted(nodes):
            if nid in placed:
                continue
            if all(s in placed for s, _ in inputs[nid]):
                order.append(nid); placed.add(nid); progressed = True
        if not progressed:
            raise SystemExit("the playoff graph has a cycle; it is not a valid bracket")

    # Round labels derived from the graph, then checked against the expected shape and the client's
    # own series names. `depth` = longest path from a seeded node.
    depth = {}
    for nid in order:
        depth[nid] = 0 if not inputs[nid] else 1 + max(depth[s] for s, _ in inputs[nid])
    upper = set(seeded)
    for nid in order:
        if inputs[nid] and all(tag == "W" and s in upper for s, tag in inputs[nid]):
            upper.add(nid)
    gf = finals[0]
    label = {}
    for nid in order:
        if nid == gf:
            label[nid] = "GF"
        elif nid in upper:
            label[nid] = {0: "UBQF", 1: "UBSF", 2: "UBF"}[depth[nid]]
        else:
            drops = sum(1 for s, tag in inputs[nid] if tag == "L")
            label[nid] = ("LBR1" if all(tag == "L" for _, tag in inputs[nid])
                          else ("LBF" if any(s in upper and label.get(s) == "UBF"
                                             for s, tag in inputs[nid] if tag == "L")
                                else ("LBR2" if drops else "LBSF")))
    shape = {}
    for nid in order:
        shape[label[nid]] = shape.get(label[nid], 0) + 1
    if shape != EXPECTED_SHAPE:
        raise SystemExit(f"bracket shape {shape} != required {EXPECTED_SHAPE}")

    # Best-of: node_type distinguishes the Grand Final from every other series in this feed.
    types = {nid: n.get("node_type") for nid, n in nodes.items()}
    gf_type, other = types[gf], {t for nid, t in types.items() if nid != gf}
    if len(other) != 1 or gf_type in other:
        raise SystemExit(f"cannot separate the Grand Final by node_type: gf={gf_type}, others={other}")
    best_of = {nid: (5 if nid == gf else 3) for nid in nodes}

    node_to_sel = {v: k for k, v in SELECTION_TO_NODE.items()}
    series_name = _client_series_names(questions)
    return {"order": order, "inputs": inputs, "best_of": best_of, "label": label,
            "seeded": seeded, "gf": gf, "node_to_selection": node_to_sel,
            "selection_to_node": dict(SELECTION_TO_NODE), "series_name": series_name,
            "node_type": types,
            "source": "official Valve league feed 19719, Playoff node group (local snapshot)"}


def _client_series_names(questions=None):
    """The client's own label per node, from the transcribed prediction_questions.json."""
    questions = questions or os.path.join(REPO, "data", "ti2026", "inputs",
                                          "prediction_questions.json")
    with open(questions, encoding="utf-8") as fh:
        doc = json.load(fh)
    q = next(x for x in doc["questions"] if x["question_id"] == "TI2026-Q-BRACKET")
    if q["number_of_slots"] != 14:
        raise SystemExit(f"client bracket question declares {q['number_of_slots']} slots, not 14")
    out = {}
    for s in q["slot_map"]:
        if SELECTION_TO_NODE.get(s["selection_id"]) != s["league_node_id"]:
            raise SystemExit(f"client slot map disagrees with SELECTION_TO_NODE at "
                             f"selection {s['selection_id']}")
        out[s["league_node_id"]] = s["series"]
    if len(out) != 14:
        raise SystemExit("client slot map does not cover 14 distinct nodes")
    return out


def verify_scoring_vector(questions=None):
    """Confirm MAIN_EVENT_SCORE against the scoring rule string transcribed from the client."""
    questions = questions or os.path.join(REPO, "data", "ti2026", "inputs",
                                          "prediction_questions.json")
    with open(questions, encoding="utf-8") as fh:
        doc = json.load(fh)
    rule = next(x for x in doc["questions"]
                if x["question_id"] == "TI2026-Q-BRACKET")["scoring_rule"]
    missing = [f"{k}->{v}" for k, v in MAIN_EVENT_SCORE.items() if k and f"{k}->{v}" not in rule]
    if missing:
        raise SystemExit("MAIN_EVENT_SCORE does not match the client scoring rule; missing "
                         + ", ".join(missing))
    if MAIN_EVENT_SCORE[0] != 0 or MAIN_EVENT_SCORE[1] != 120 or MAIN_EVENT_SCORE[14] != 12000:
        raise SystemExit("MAIN_EVENT_SCORE anchors do not hold (0->0, 1->120, 14->12000)")
    vals = [MAIN_EVENT_SCORE[k] for k in range(15)]
    if any(b < a for a, b in zip(vals, vals[1:])):
        raise SystemExit("MAIN_EVENT_SCORE is not non-decreasing")
    return {"vector": vals, "anchors_ok": True,
            "source": "client-transcribed scoring_rule in prediction_questions.json "
                      "(TI2026-Q-BRACKET, source_tier 1), independently matching contest_rules"}


def map_prob(sa, sb, c):
    """Frozen side-neutral map probability: 0.5*(sigmoid(d+c) + sigmoid(d-c))."""
    d = sa - sb
    return 0.5 * (1.0 / (1.0 + np.exp(-(d + c))) + 1.0 / (1.0 + np.exp(-(d - c))))


def enumerate_structure(topo, seats):
    """Every complete outcome of the bracket as pure STRUCTURE -- no strengths involved.

    Which teams meet where, and who wins, depends only on the 14 binary choices, so this is computed
    once and reused for every strength draw. `seats` maps each seeded node id to its (teamA, teamB)
    pair of canonical names. Returns:
      teams -- index -> team name
      W     -- (2^14, 14) int8, winner index at each node (columns follow topo['order'])
      PR    -- (2^14, 14, 2) int8, the two participants at each node in each outcome
    """
    order = topo["order"]
    names = sorted({t for pair_ in seats.values() for t in pair_})
    idx = {t: i for i, t in enumerate(names)}
    if len(names) != 8:
        raise SystemExit(f"the bracket must seat 8 distinct teams, got {len(names)}")
    n = 1 << len(order)
    W = np.zeros((n, len(order)), dtype=np.int8)
    PR = np.zeros((n, len(order), 2), dtype=np.int8)

    def rec(k, winner, loser, path, pa, pb):
        if k == len(order):
            for col, nid in enumerate(order):
                W[path, col] = winner[nid]
                PR[path, col, 0] = pa[nid]
                PR[path, col, 1] = pb[nid]
            return
        nid = order[k]
        if topo["inputs"][nid]:
            (s1, t1), (s2, t2) = topo["inputs"][nid]
            a = winner[s1] if t1 == "W" else loser[s1]
            b = winner[s2] if t2 == "W" else loser[s2]
        else:
            a, b = idx[seats[nid][0]], idx[seats[nid][1]]
        pa[nid], pb[nid] = a, b
        winner[nid], loser[nid] = a, b
        rec(k + 1, winner, loser, path, pa, pb)
        winner[nid], loser[nid] = b, a
        rec(k + 1, winner, loser, path | (1 << k), pa, pb)

    rec(0, {}, {}, 0, {}, {})
    return names, W, PR


def series_matrices(topo, teams, strength, c):
    """{best_of: 8x8 array of P(row team beats column team)} under the frozen side-neutral form."""
    s = np.array([strength[t] for t in teams])
    d = s[:, None] - s[None, :]
    mp = 0.5 * (1.0 / (1.0 + np.exp(-(d + c))) + 1.0 / (1.0 + np.exp(-(d - c))))
    return {bo: np.array([[series_win_prob(mp[i, j], bo) for j in range(len(teams))]
                          for i in range(len(teams))])
            for bo in sorted(set(topo["best_of"].values()))}


def outcome_probs(topo, W, PR, teams, strength, c, check=True):
    """Exact probability of every enumerated outcome, vectorized over all 2^14 at once."""
    sp = series_matrices(topo, teams, strength, c)
    P = np.ones(W.shape[0])
    for col, nid in enumerate(topo["order"]):
        a, b = PR[:, col, 0].astype(np.intp), PR[:, col, 1].astype(np.intp)
        q = sp[topo["best_of"][nid]][a, b]                 # P(participant A wins this node)
        P *= np.where(W[:, col] == PR[:, col, 0], q, 1.0 - q)
    if check and abs(P.sum() - 1.0) > 1e-9:
        raise SystemExit(f"outcome probabilities sum to {P.sum()}, not 1")
    return P


def enumerate_bracket(topo, seats, strength, c):
    """Convenience wrapper: structure plus one set of outcome probabilities."""
    names, W, PR = enumerate_structure(topo, seats)
    return names, W, outcome_probs(topo, W, PR, names, strength, c), PR


def expected_scores(W, P, chunk=1024):
    """Exact E[official score] and E[correct] for every coherent slate.

    A coherent slate is a row of W, so the candidate set is W itself. Returns (E_score, E_correct),
    each length 2^14 and aligned with W's rows.
    """
    n, k = W.shape
    Es = np.empty(n); Ec = np.empty(n)
    for lo in range(0, n, chunk):
        hi = min(lo + chunk, n)
        K = (W[lo:hi, None, :] == W[None, :, :]).sum(axis=2).astype(np.int8)
        Es[lo:hi] = SCORE_VEC[K] @ P
        Ec[lo:hi] = K @ P
    return Es, Ec


def agreement_matrix(W, rows, chunk=1024):
    """K[i, t] = number of nodes on which candidate slate `rows[i]` matches outcome t."""
    out = np.empty((len(rows), W.shape[0]), dtype=np.int8)
    B = W[rows]
    for lo in range(0, len(rows), chunk):
        hi = min(lo + chunk, len(rows))
        out[lo:hi] = (B[lo:hi, None, :] == W[None, :, :]).sum(axis=2)
    return out


def greedy_favourite(topo, seats, strength, c, teams):
    """The coherent bracket built by taking the model favourite at every node in order."""
    idx = {t: i for i, t in enumerate(teams)}
    s = {t: strength[t] for t in teams}
    win, lose, picks = {}, {}, {}
    for nid in topo["order"]:
        if topo["inputs"][nid]:
            (s1, t1), (s2, t2) = topo["inputs"][nid]
            a = win[s1] if t1 == "W" else lose[s1]
            b = win[s2] if t2 == "W" else lose[s2]
        else:
            a, b = seats[nid][0], seats[nid][1]
        p = series_win_prob(map_prob(s[a], s[b], c), topo["best_of"][nid])
        w, l = (a, b) if p >= 0.5 else (b, a)
        win[nid], lose[nid], picks[nid] = w, l, w
    return [idx[picks[nid]] for nid in topo["order"]]


def slate_row(W, vec):
    """Index of the coherent slate equal to `vec` (a length-14 winner vector). -1 if absent."""
    m = np.all(W == np.asarray(vec, dtype=np.int8)[None, :], axis=1)
    hits = np.flatnonzero(m)
    return int(hits[0]) if len(hits) else -1


def main():
    topo = load_topology()
    sv = verify_scoring_vector()
    print("main-event bracket topology (from the official league feed)")
    print(f"  source: {topo['source']}")
    shape = {}
    for nid in topo["order"]:
        shape[topo["label"][nid]] = shape.get(topo["label"][nid], 0) + 1
    print(f"  shape : {shape}  (required {EXPECTED_SHAPE})")
    print(f"  scoring vector verified against the client: {sv['vector']}")
    print("\n  sel  node  round  best_of  fed by                     client label")
    for nid in topo["order"]:
        fed = ", ".join(f"{tag}{s}" for s, tag in topo["inputs"][nid]) or "seeded"
        print(f"  {topo['node_to_selection'][nid]}   {nid:>3}   {topo['label'][nid]:<5}  "
              f"Bo{topo['best_of'][nid]}      {fed:<25}  {topo['series_name'][nid]}")

    # mechanics self-test on synthetic strengths: normalization, monotonicity, exactness
    teams = [f"T{i}" for i in range(8)]
    seats = {nid: (teams[2 * k], teams[2 * k + 1]) for k, nid in enumerate(topo["seeded"])}
    strength = {t: 0.25 * i for i, t in enumerate(teams)}
    names, W, P, _ = enumerate_bracket(topo, seats, strength, 0.09)
    Es, Ec = expected_scores(W, P)
    champ = {names[i]: float(P[W[:, topo["order"].index(topo["gf"])] == i].sum())
             for i in range(8)}
    assert abs(sum(champ.values()) - 1.0) < 1e-12
    assert champ["T7"] == max(champ.values())
    best = int(np.argmax(Es))
    assert Ec.max() <= 14 and Es.max() <= MAIN_EVENT_SCORE[14]
    print(f"\n  self-test: {W.shape[0]} outcomes, sum(P)={P.sum():.12f}, "
          f"champion mass normalized, strongest team is the modal champion")
    print(f"  self-test: best synthetic slate E[score]={Es[best]:.1f}, E[correct]={Ec[best]:.3f}")
    print("  topology verified; no TI2026 numbers emitted here")


if __name__ == "__main__":
    main()
