"""Faithful TI15 group-stage simulator: Swiss (up to 5 rounds) + extra elimination round.

Implements the verified official rules (docs/contest-official-ti15.md sec 9):
  - 16 teams, every series Bo3 (simulated map-by-map so game-level tiebreakers exist).
  - Up to 5 Swiss rounds; a team STOPS at its 4th series win (advances) or 4th series loss (out).
  - Two 8-team initial pods: rounds 1-3 pair only within a team's pod; round 4 pairs across pods;
    round 5 pairs the remaining record groups.
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
  - C5 pairing tie-break: among rule-legal pairings we minimize rematches first, then optimize the
    gap objective, then break remaining ties at RANDOM (samples the organizer's unspecified choice).
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
from itertools import permutations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUCKETS = ("4-0", "4-1", "decider_win", "decider_loss", "1-4", "0-4")
CAPACITY = {"4-0": 1, "4-1": 2, "decider_win": 5, "decider_loss": 5, "1-4": 2, "0-4": 1}


def map_p(sa, sb):
    """Single-map win probability for a vs b from log-strengths (side-neutral)."""
    return 1.0 / (1.0 + math.exp(-(sa - sb)))


def _new_state(teams):
    return {"w": {t: 0 for t in teams}, "l": {t: 0 for t in teams},
            "mw": {t: 0 for t in teams}, "ml": {t: 0 for t in teams},
            "opp": {t: [] for t in teams}, "played": set()}


def _play(a, b, strength, st, rng, best_of=3):
    """Simulate a Bo3 map-by-map; update series + map records and opponent lists."""
    need = best_of // 2 + 1
    pa = map_p(strength[a], strength[b])
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


def standings(teams, st, rng):
    """Rank teams best->worst by the official tiebreakers; ties broken at random (coin toss)."""
    rand = {t: rng.random() for t in teams}

    def key(t):
        opps = st["opp"][t]
        osw = sum(st["w"][o] for o in opps)
        oagwp = sum(_gwp(o, st) for o in opps) / len(opps) if opps else 0.0
        # sort ascending on the negations so that reverse=True puts the best team first
        return (st["w"][t], -st["l"][t], osw, _gwp(t, st), oagwp, rand[t])

    return sorted(teams, key=key, reverse=True)


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
    best, best_key = None, None
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


def simulate_one(pods, strength, rng, r1_pairings=None, elim_choice="strategic"):
    """Run one full group stage. `pods` = (podA_list, podB_list), 8 teams each.

    r1_pairings: optional list of (a, b) for the actual posted round-1 draw (must respect pods);
                 if None, round 1 is paired randomly within each pod.
    Returns {team: bucket} for all 16 teams.
    """
    podA, podB = pods
    teams = list(podA) + list(podB)
    assert len(podA) == 8 and len(podB) == 8, "each pod must have 8 teams"
    pod_of = {t: "A" for t in podA}; pod_of.update({t: "B" for t in podB})
    st = _new_state(teams)

    # ---- Round 1: within pod, preset draw or random ----
    if r1_pairings is not None:
        for a, b in r1_pairings:
            assert pod_of[a] == pod_of[b], "round-1 pairing crosses pods"
            _play(a, b, strength, st, rng)
    else:
        for pod in (list(podA), list(podB)):
            rng.shuffle(pod)
            for i in range(0, 8, 2):
                _play(pod[i], pod[i + 1], strength, st, rng)

    # ---- Rounds 2-3: within pod, same record, min gap ----
    for _ in range(2):
        for pod in (podA, podB):
            for rec, grp in _by_record(pod, st).items():
                for a, b in pair_group(grp, st, rng, gap="min"):
                    _play(a, b, strength, st, rng)

    # ---- Round 4: cross pod, same record ----
    for rec, grp in _by_record(teams, st).items():
        for a, b in pair_group(grp, st, rng, gap="min", cross_pod=pod_of):
            _play(a, b, strength, st, rng)

    # after R4: 4-0 and 0-4 are done; 3-1 / 2-2 / 1-3 continue
    active = [t for t in teams if st["w"][t] < 4 and st["l"][t] < 4]

    # ---- Round 5: 1-3 group are elimination matches (max gap); others min gap ----
    for rec, grp in _by_record(active, st).items():
        gap = "max" if rec == (1, 3) else "min"          # loser of a 1-3 match is eliminated
        for a, b in pair_group(grp, st, rng, gap=gap):
            _play(a, b, strength, st, rng)

    # ---- classify records into buckets ----
    rec_of = {t: (st["w"][t], st["l"][t]) for t in teams}
    bucket = {}
    threes = [t for t in teams if rec_of[t] == (3, 2)]      # 3-2 teams
    twos = [t for t in teams if rec_of[t] == (2, 3)]        # 2-3 teams
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
    assert len(threes) == 5 and len(twos) == 5, (len(threes), len(twos))

    # ---- extra elimination round: 3-2 teams pick 2-3 opponents in rank order ----
    pick_order = standings(threes, st, rng)                 # highest-ranked 3-2 picks first
    pool = list(twos)
    for a in pick_order:
        if elim_choice == "random":
            opp = pool[rng.randrange(len(pool))]
        else:                                               # strategic: strongest matchup for `a`
            opp = min(pool, key=lambda o: strength[o])
        pool.remove(opp)
        win, lose = _play(a, opp, strength, st, rng)
        bucket[win] = "decider_win"
        bucket[lose] = "decider_loss"

    assert len(bucket) == 16
    return bucket


def monte_carlo(pods, strength, n=20000, seed=20260813, r1_pairings=None, elim_choice="strategic"):
    """Return P[team][bucket] over n simulations, plus the exact per-run bucket counts (invariant)."""
    rng = random.Random(seed)
    teams = list(pods[0]) + list(pods[1])
    tally = {t: {b: 0 for b in BUCKETS} for t in teams}
    for _ in range(n):
        bucket = simulate_one(pods, strength, rng, r1_pairings, elim_choice)
        counts = defaultdict(int)
        for t, b in bucket.items():
            tally[t][b] += 1
            counts[b] += 1
        assert dict(counts) == CAPACITY, dict(counts)        # structural invariant every run
    return {t: {b: tally[t][b] / n for b in BUCKETS} for t in teams}


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
