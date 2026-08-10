"""Rules-based TI15 group-stage simulator: Swiss (up to 5 rounds) + extra elimination round.

Implements the PUBLIC official rules and passes structural / property tests; it does NOT claim to
exactly replicate the organizer's UNPUBLISHED pairing decisions (see the C5 / D4 / duration-tiebreak
assumptions below). Implements (docs/contest-official-ti15.md sec 9):
  - 16 teams, every series Bo3 (simulated map-by-map so game-level tiebreakers exist).
  - Up to 5 Swiss rounds; a team STOPS at its 4th series win (advances) or 4th series loss (out).
  - Pod structure (`pods`): either TWO 8-team initial pods -- rounds 1-3 pair only within a team's
    pod, round 4 pairs across pods, round 5 pairs the remaining record groups -- or a single OPEN
    16-team pool in which every round pairs by record with no pod constraint. Both structures force
    the same final record distribution; they differ only in WHICH opponent a team meets in rounds
    2-4. The in-client rules text describes two pods; Valve's league feed exposes one undivided
    16-team Swiss node group, so the structure is carried as an explicit hypothesis (see
    docs/contest-official-ti15.md sec 9).
  - Pairing principles: same record first (hard); avoid rematch (soft); minimize rank gap (soft).
    Round-5 EXCEPTION: only matches whose loser is eliminated (the 1-3 group) maximize the rank gap.
  - After Swiss the record distribution is structurally exact: 4-0 x1, 4-1 x2, 3-2 x5, 2-3 x5,
    1-4 x2, 0-4 x1. The 3 top-ranked advance directly; 1-4 x2 and 0-4 x1 are out; the five 3-2 and
    five 2-3 teams play an extra Bo3 elimination round.
  - Extra round PICK ORDER (D2): the highest-ranked 3-2 team picks any 2-3 opponent, next 3-2 team
    picks from those remaining, etc. Winners fill "decider_win"; losers fill "decider_loss". A 2-3
    team can win and a 3-2 team can lose, so these buckets are NOT the 3-2 / 2-3 record groups.
  - Ranking tiebreakers, in order: series_wins, series_losses (fewer better), opponents_series_wins
    (SoS), game_win_pct, opponents_avg_game_win_pct, [avg_game_duration -- unmodelable, folded into]
    coin_toss.

Modeling assumptions where the official text is silent (docs sec 9):
  - C5 pairing tie-break: among rule-legal pairings the algorithm minimizes rematches first, then
    optimizes the gap objective, then breaks remaining ties at RANDOM (samples the unspecified choice).
    Ranking ties (undeveloped SoS in early rounds) also break at random -> this is the modeled
    pairing uncertainty.
  - D4 opponent choice: each 3-2 team, in pick order, takes the remaining 2-3 opponent it is
    STRONGEST against (lowest opponent strength). `elim_choice='random'` gives the sensitivity check.

The six prediction buckets. No TI2026 numbers are emitted here; __main__ is a structure/mechanics
self-test on synthetic strengths.
"""
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.contest_rules import BUCKETS, CAPACITY


def map_p(sa, sb):
    """Raw single-map win probability for a vs b from log-strengths, sigmoid(sa - sb)."""
    return 1.0 / (1.0 + math.exp(-(sa - sb)))


def map_pn(sa, sb, c=0.0):
    """Production side-neutral map win prob: 0.5*(sigmoid(d+c)+sigmoid(d-c)), d=sa-sb.

    Matches the frozen spec (calibration-sideaware.md / production_platt.json): sides are unknown at
    TI, so the radiant coefficient c (estimated on pre-cutoff training data) is averaged out. c=0
    reduces exactly to raw sigmoid(d).
    """
    d = sa - sb
    return 0.5 * (1.0 / (1.0 + math.exp(-(d + c))) + 1.0 / (1.0 + math.exp(-(d - c))))


def _new_state(teams, c=0.0):
    return {"w": {t: 0 for t in teams}, "l": {t: 0 for t in teams},
            "mw": {t: 0 for t in teams}, "ml": {t: 0 for t in teams},
            "opp": {t: [] for t in teams}, "played": set(), "c": c}


def _play(a, b, strength, st, rng, best_of=3):
    """Simulate a Bo3 map-by-map; update series + map records and opponent lists."""
    need = best_of // 2 + 1
    pa = map_pn(strength[a], strength[b], st["c"])
    aw = bw = 0
    while aw < need and bw < need:
        if rng.random() < pa:
            aw += 1
        else:
            bw += 1
    win, lose = (a, b) if aw > bw else (b, a)
    st["w"][win] += 1
    st["l"][lose] += 1
    st["mw"][a] += aw; st["ml"][a] += bw
    st["mw"][b] += bw; st["ml"][b] += aw
    st["opp"][a].append(b); st["opp"][b].append(a)
    st["played"].add(frozenset((a, b)))
    return win, lose


def _gwp(t, st):
    n = st["mw"][t] + st["ml"][t]
    return st["mw"][t] / n if n else 0.0


def _real_key(t, st):
    """The official tiebreaker key WITHOUT the coin toss (higher = better under reverse sort).

    Order: series_wins, -series_losses, opponents_series_wins, game_win_pct,
    opponents_avg_game_win_pct. The 6th criterion (avg_game_duration) is unmodelable and is folded
    into the coin toss; floats are rounded so FP noise never fabricates a distinct rank.
    """
    opps = st["opp"][t]
    osw = sum(st["w"][o] for o in opps)
    oagwp = sum(_gwp(o, st) for o in opps) / len(opps) if opps else 0.0
    return (st["w"][t], -st["l"][t], osw, round(_gwp(t, st), 12), round(oagwp, 12))


def standings(teams, st, rng):
    """Rank teams best->worst by the official tiebreakers; remaining ties broken at random."""
    rand = {t: rng.random() for t in teams}
    return sorted(teams, key=lambda t: _real_key(t, st) + (rand[t],), reverse=True)


def _matchings(lst):
    """Yield every perfect pairing of an even-length list (as lists of (a, b) tuples)."""
    if not lst:
        yield []
        return
    a = lst[0]
    for i in range(1, len(lst)):
        rest = lst[1:i] + lst[i + 1:]
        for m in _matchings(rest):
            yield [(a, lst[i])] + m


def pair_group(group, st, rng, gap="min", cross_pod=None):
    """Pair one record group under the rules. Returns a list of (a, b) pairs.

    Enumerates legal perfect matchings (groups are small, <=8). Selection order:
      1. fewest rematches (avoid-rematch is soft but strongly preferred),
      2. gap objective: minimize (default) or maximize the summed rank gap,
      3. random among the remaining ties (C5).
    `cross_pod` (dict team->pod) forces every pair to be across the two pods.
    """
    assert len(group) % 2 == 0, ("odd group", group)
    order = standings(group, st, rng)
    idx = {t: i for i, t in enumerate(order)}
    best_key = None
    cands = []
    for m in _matchings(order):
        if cross_pod is not None and any(cross_pod[a] == cross_pod[b] for a, b in m):
            continue
        rematch = sum(1 for a, b in m if frozenset((a, b)) in st["played"])
        gapsum = sum(abs(idx[a] - idx[b]) for a, b in m)
        gobj = gapsum if gap == "min" else -gapsum
        k = (rematch, gobj)
        if best_key is None or k < best_key:
            best_key, cands = k, [m]
        elif k == best_key:
            cands.append(m)
    return cands[rng.randrange(len(cands))]


def _by_record(teams, st):
    g = defaultdict(list)
    for t in teams:
        g[(st["w"][t], st["l"][t])].append(t)
    return g


def _series_winner(a, b, strength, c, rng, best_of=3):
    """Simulate a Bo3 map-by-map WITHOUT mutating state; return (winner, loser)."""
    need = best_of // 2 + 1
    pa = map_pn(strength[a], strength[b], c)
    aw = bw = 0
    while aw < need and bw < need:
        if rng.random() < pa:
            aw += 1
        else:
            bw += 1
    return (a, b) if aw > bw else (b, a)


def teams_of(pods):
    """Flatten a pod structure to its team list. Works for two-pod and open-16 structures."""
    return [t for pod in pods for t in pod]


def is_two_pod(pods):
    """True for the two-8-team-pod structure, False for the open 16-team pool `(teams,)`."""
    return len(pods) == 2


def _swiss(pods, strength, rng, r1_pairings, c):
    """Run the Swiss stage (up to 5 rounds). Returns (st, bucket_partial, threes, twos).

    `pods` is either (podA, podB) with 8 teams each, or a 1-tuple (teams,) of all 16 for the open
    structure with no pod constraint on any round.

    bucket_partial holds only the record-decided buckets (4-0/4-1/1-4/0-4); the decider round is run
    separately (see _deciders) so D4 scenarios can share one Swiss outcome under common random numbers.
    """
    teams = teams_of(pods)
    assert len(teams) == 16 and len(set(teams)) == 16, "pods must hold 16 distinct teams"
    two_pod = is_two_pod(pods)
    if two_pod:
        podA, podB = pods
        assert len(podA) == 8 and len(podB) == 8, "each pod must have 8 teams"
        pod_of = {t: "A" for t in podA}; pod_of.update({t: "B" for t in podB})
    else:
        pod_of = None
    st = _new_state(teams, c)

    # Round 1: preset draw, or random within each pod (two-pod) / across the pool (open)
    if r1_pairings is not None:
        for a, b in r1_pairings:
            assert not two_pod or pod_of[a] == pod_of[b], "round-1 pairing crosses pods"
            _play(a, b, strength, st, rng)
    else:
        for pod in ([list(podA), list(podB)] if two_pod else [list(teams)]):
            rng.shuffle(pod)
            for i in range(0, len(pod), 2):
                _play(pod[i], pod[i + 1], strength, st, rng)

    # Rounds 2-3: same record, min gap -- within pod when the pod structure applies
    for _ in range(2):
        for pool in ((podA, podB) if two_pod else (teams,)):
            for rec, grp in _by_record(pool, st).items():
                for a, b in pair_group(grp, st, rng, gap="min"):
                    _play(a, b, strength, st, rng)

    # Round 4: same record; forced across pods when the pod structure applies
    for rec, grp in _by_record(teams, st).items():
        for a, b in pair_group(grp, st, rng, gap="min", cross_pod=pod_of):
            _play(a, b, strength, st, rng)

    active = [t for t in teams if st["w"][t] < 4 and st["l"][t] < 4]

    # Round 5: only 1-3 matches are elimination (loser out) -> max gap; others min gap
    for rec, grp in _by_record(active, st).items():
        gap = "max" if rec == (1, 3) else "min"
        for a, b in pair_group(grp, st, rng, gap=gap):
            _play(a, b, strength, st, rng)

    rec_of = {t: (st["w"][t], st["l"][t]) for t in teams}
    threes = [t for t in teams if rec_of[t] == (3, 2)]
    twos = [t for t in teams if rec_of[t] == (2, 3)]
    assert len(threes) == 5 and len(twos) == 5, (len(threes), len(twos))
    bucket = {}
    for t in teams:
        r = rec_of[t]
        if r == (4, 0):
            bucket[t] = "4-0"
        elif r == (4, 1):
            bucket[t] = "4-1"
        elif r == (1, 4):
            bucket[t] = "1-4"
        elif r == (0, 4):
            bucket[t] = "0-4"
    return st, bucket, threes, twos


def _deciders(pick_order, twos, strength, c, rng_choice, rng_match, elim_choice):
    """Run the 5 extra-elimination matches. rng_choice picks opponents; rng_match plays the series.

    Separate streams let the D4 scenarios reuse identical MATCH randomness (common random numbers),
    isolating the opponent-choice effect. Returns {team: 'decider_win'|'decider_loss'}.
    """
    pool = list(twos)
    res = {}
    for a in pick_order:
        if elim_choice == "random":
            opp = pool[rng_choice.randrange(len(pool))]
        elif elim_choice == "noisy":                        # weight toward weaker opponents for `a`
            ws = [map_pn(strength[a], strength[o], c) for o in pool]
            r = rng_choice.random() * sum(ws)
            cum = 0.0
            for o, w in zip(pool, ws):
                cum += w
                if r <= cum:
                    opp = o
                    break
        else:                                               # strategic: strongest matchup for `a`
            opp = min(pool, key=lambda o: strength[o])
        pool.remove(opp)
        win, lose = _series_winner(a, opp, strength, c, rng_match)
        res[win] = "decider_win"
        res[lose] = "decider_loss"
    return res


def simulate_one(pods, strength, rng, r1_pairings=None, elim_choice="strategic", diag=False, c=0.0):
    """Run one full group stage (Swiss + decider).

    `pods` = (podA_list, podB_list) with 8 teams each, or (teams_list,) with all 16 for the open
    structure (no pod constraint on any round).

    c: production radiant coefficient for the side-neutral map prob (0 = raw sigmoid).
    r1_pairings: optional list of (a, b) for the actual posted round-1 draw (must respect pods);
                 if None, round 1 is paired randomly within each pod.
    elim_choice (D4 opponent-choice sensitivity scenarios):
      'strategic' -- each 3-2 team picks the remaining 2-3 opponent it is strongest against;
      'noisy'     -- picks probabilistically, weighted toward (not fixed on) weaker opponents;
      'random'    -- uniform random pick (boundary control).
    Returns {team: bucket}; if diag, returns ({team: bucket}, diagnostics). One shared rng is used
    for choice and match here, preserving the single-stream behaviour.
    """
    st, bucket, threes, twos = _swiss(pods, strength, rng, r1_pairings, c)
    teams = teams_of(pods)

    # tiebreak-depth diagnostic on the Swiss standings BEFORE the decider adds games. A tie means the
    # first five tiebreakers were equal, so the result falls to the UNMODELED avg-duration/coin-toss
    # tail. tie_16 = any two of the 16 tie; tie_32 = two 3-2 teams tie (decider pick order affected).
    d = None
    if diag:
        k16 = [_real_key(t, st) for t in teams]
        k32 = [_real_key(t, st) for t in threes]
        d = {"tie_16": len(set(k16)) < 16, "tie_32": len(set(k32)) < len(k32)}

    pick_order = standings(threes, st, rng)                 # highest-ranked 3-2 picks first
    bucket.update(_deciders(pick_order, twos, strength, c, rng, rng, elim_choice))
    assert len(bucket) == 16
    return (bucket, d) if diag else bucket


def d4_sensitivity_crn(pods, strength, n=20000, seed=20260813, r1_pairings=None, c=0.0,
                       choices=("strategic", "noisy", "random")):
    """Common-random-numbers D4 sensitivity: per sim, ONE shared Swiss outcome and a shared pick
    order + decider-match RNG across all choices; only the opponent-choice rule varies. This isolates
    the opponent-choice effect from Monte-Carlo path noise. Returns {choice: P[team][bucket]}.
    """
    teams = teams_of(pods)
    tally = {ch: {t: {b: 0 for b in BUCKETS} for t in teams} for ch in choices}
    for k in range(n):
        base = seed * 1_000_003 + k
        st, bucket0, threes, twos = _swiss(pods, strength, random.Random(base * 7 + 3), r1_pairings, c)
        pick_order = standings(threes, st, random.Random(base * 7 + 4))   # common across choices
        for ch in choices:
            rc, rm = random.Random(base * 7 + 5), random.Random(base * 7 + 6)  # reset -> common
            b = dict(bucket0)
            b.update(_deciders(pick_order, twos, strength, c, rc, rm, ch))
            for t, bb in b.items():
                tally[ch][t][bb] += 1
    return {ch: {t: {b: tally[ch][t][b] / n for b in BUCKETS} for t in teams} for ch in choices}


def monte_carlo(pods, strength, n=20000, seed=20260813, r1_pairings=None, elim_choice="strategic",
                return_diag=False, c=0.0, return_archive=False):
    """Return P[team][bucket] over n simulations (per-run bucket counts are an asserted invariant).

    c: production radiant coefficient for the side-neutral map prob (0 = raw sigmoid).
    If return_diag, also return {'tie_16_rate', 'tie_32_rate', 'n'}: how often the first five
    tiebreakers all tie (result decided by the unmodeled avg-duration/coin-toss tail) overall, and
    how often that decides the bucket-relevant 3-2 pick order.
    If return_archive, also return {team: [bucket_index per simulation]} (indices into BUCKETS),
    enabling downstream expected-points optimization on the same simulation set.
    Return shape: P, then diag if requested, then archive if requested.
    """
    rng = random.Random(seed)
    teams = teams_of(pods)
    tally = {t: {b: 0 for b in BUCKETS} for t in teams}
    bidx = {b: i for i, b in enumerate(BUCKETS)}
    arch = {t: [] for t in teams} if return_archive else None
    tie16 = tie32 = 0
    for _ in range(n):
        out = simulate_one(pods, strength, rng, r1_pairings, elim_choice, diag=return_diag, c=c)
        bucket, d = out if return_diag else (out, None)
        counts = defaultdict(int)
        for t, b in bucket.items():
            tally[t][b] += 1
            counts[b] += 1
            if arch is not None:
                arch[t].append(bidx[b])
        assert dict(counts) == CAPACITY, dict(counts)        # structural invariant every run
        if d:
            tie16 += d["tie_16"]; tie32 += d["tie_32"]
    P = {t: {b: tally[t][b] / n for b in BUCKETS} for t in teams}
    ret = [P]
    if return_diag:
        ret.append({"tie_16_rate": tie16 / n, "tie_32_rate": tie32 / n, "n": n})
    if return_archive:
        ret.append(arch)
    return ret[0] if len(ret) == 1 else tuple(ret)


if __name__ == "__main__":
    # structure/mechanics self-test on synthetic strengths (NOT TI2026)
    teams = [f"T{i:02d}" for i in range(16)]
    strength = {t: 0.22 * i for i, t in enumerate(teams)}    # T15 strongest, T00 weakest
    pods = (teams[0::2], teams[1::2])                         # interleave so pods are balanced
    P = monte_carlo(pods, strength, n=6000)

    for t in teams:
        s = sum(P[t].values())
        assert abs(s - 1.0) < 1e-9, (t, s)                   # each team's buckets sum to 1
    for b in BUCKETS:
        col = sum(P[t][b] for t in teams)
        assert abs(col - CAPACITY[b]) < 1e-9, (b, col)       # column sums == capacity

    strongest, weakest = "T15", "T00"
    adv = lambda t: P[t]["4-0"] + P[t]["4-1"] + P[t]["decider_win"]
    assert P[strongest]["4-0"] == max(P[t]["4-0"] for t in teams), "strongest should top 4-0"
    assert P[weakest]["0-4"] == max(P[t]["0-4"] for t in teams), "weakest should top 0-4"
    assert adv(strongest) > adv(weakest), "monotonic advancement"
    # a mid team must be able to reach decider_win via a 2-3 upset (bucket is not the 3-2 group)
    assert any(0.0 < P[t]["decider_win"] < 1.0 for t in teams), "decider_win should be probabilistic"

    print("structural invariant 1/2/5/5/2/1 held every run; sums + monotonicity OK")
    print("advance prob (synthetic, strong->weak):",
          ", ".join(f"{t}={adv(t):.2f}" for t in ("T15", "T12", "T08", "T04", "T00")))
    print("T15 buckets:", {b: round(P['T15'][b], 3) for b in BUCKETS})
    print("T00 buckets:", {b: round(P['T00'][b], 3) for b in BUCKETS})
    print("mechanics self-test passed; no TI2026 output emitted")
