"""TI Swiss + playoff Monte-Carlo simulation pipeline (downstream diagnostic).

Turns team strengths (e.g. B-bt log-strengths) into tournament outcome probabilities:
map win prob -> series win prob (series.py) -> 5-round Swiss (Bo3) -> special elimination ->
8-team double-elimination playoff (Bo3, Grand Final Bo5) -> champion / advancement probabilities.

This module is the PIPELINE only. It emits NO TI2026 numbers here: `__main__` runs a mechanics
self-test on synthetic strengths (monotonicity + normalization). Producing real TI2026 probabilities
is the model-only Track-1 step (see backtest-protocol.md Addendum C) and is done separately, clearly
labeled, once invoked with the real B-bt strengths and the posted Swiss draw.

Simplifications (documented; refine when the official draw/format post): Swiss pairing is
record-grouped with random within-group pairing (no Buchholz tiebreak); the special-elimination and
playoff seeding use Swiss rank order. Format: Swiss/elim/playoff Bo3, Grand Final Bo5.
"""
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.series import series_win_prob


def map_p(sa, sb):
    return 1.0 / (1.0 + math.exp(-(sa - sb)))


def series_p(sa, sb, best_of):
    return series_win_prob(map_p(sa, sb), best_of)


def _play(a, b, strength, best_of, rng):
    return a if rng.random() < series_p(strength[a], strength[b], best_of) else b


def swiss(teams, strength, rng, rounds=5, bo=3):
    """5-round Swiss (Bo3). Returns teams ranked best->worst by (wins, -losses, random)."""
    wins = {t: 0 for t in teams}; losses = {t: 0 for t in teams}
    played = set()
    for _ in range(rounds):
        groups = defaultdict(list)
        for t in teams:
            groups[(wins[t], losses[t])].append(t)
        carry = []
        for rec in sorted(groups, key=lambda r: (-r[0], r[1])):
            grp = carry + groups[rec]; carry = []
            rng.shuffle(grp)
            if len(grp) % 2:                       # odd -> float one down to next group
                carry = [grp.pop()]
            for i in range(0, len(grp) - 1, 2):
                a, b = grp[i], grp[i + 1]
                w = _play(a, b, strength, bo, rng)
                l = b if w == a else a
                wins[w] += 1; losses[l] += 1; played.add(frozenset((a, b)))
    return sorted(teams, key=lambda t: (-wins[t], losses[t], rng.random()))


def double_elim(seeds, strength, rng, bo=3, gf_bo=5):
    """8-team double elimination (seeds[0]=1 .. seeds[7]=8). Returns the champion."""
    s = seeds
    # Upper bracket (standard seeding)
    ubq = [(s[0], s[7]), (s[3], s[4]), (s[1], s[6]), (s[2], s[5])]
    uw, ul = [], []
    for a, b in ubq:
        w = _play(a, b, strength, bo, rng); uw.append(w); ul.append(b if w == a else a)
    us1 = _play(uw[0], uw[1], strength, bo, rng); us1l = uw[1] if us1 == uw[0] else uw[0]
    us2 = _play(uw[2], uw[3], strength, bo, rng); us2l = uw[3] if us2 == uw[2] else uw[2]
    ub_win = _play(us1, us2, strength, bo, rng); ubf_l = us2 if ub_win == us1 else us1
    # Lower bracket
    l1a = _play(ul[0], ul[1], strength, bo, rng)
    l1b = _play(ul[2], ul[3], strength, bo, rng)
    l2a = _play(l1a, us2l, strength, bo, rng)
    l2b = _play(l1b, us1l, strength, bo, rng)
    l3 = _play(l2a, l2b, strength, bo, rng)
    lb_win = _play(l3, ubf_l, strength, bo, rng)
    # Grand final (Bo5)
    return _play(ub_win, lb_win, strength, gf_bo, rng)


def monte_carlo(teams, strength, n=5000, seed=20260801):
    rng = random.Random(seed)
    champ = defaultdict(int); main = defaultdict(int); direct = defaultdict(int)
    for _ in range(n):
        ranked = swiss(teams, strength, rng)
        top3, mid10 = ranked[:3], ranked[3:13]
        for t in top3:
            direct[t] += 1
        # special elimination: 10 teams -> 5 winners (seeded pairs)
        elim_pairs = [(mid10[i], mid10[9 - i]) for i in range(5)]
        elim_win = [_play(a, b, strength, 3, rng) for a, b in elim_pairs]
        me = top3 + elim_win                         # 8 main-event teams, in seed order
        for t in me:
            main[t] += 1
        champ[double_elim(me, strength, rng)] += 1
    return ({t: champ[t] / n for t in teams},
            {t: main[t] / n for t in teams},
            {t: direct[t] / n for t in teams})


if __name__ == "__main__":
    # mechanics self-test on synthetic strengths (NOT TI2026): 16 teams, strictly increasing strength
    teams = [f"T{i:02d}" for i in range(16)]
    strength = {t: 0.30 * i for i, t in enumerate(teams)}   # T15 strongest
    champ, main, direct = monte_carlo(teams, strength, n=4000)
    assert abs(sum(champ.values()) - 1.0) < 1e-9, sum(champ.values())
    assert champ["T15"] == max(champ.values()), "strongest team should have top champion prob"
    assert champ["T15"] > champ["T00"], "monotonicity violated"
    assert main["T15"] > main["T00"] and direct["T15"] > direct["T00"]
    top = sorted(champ, key=champ.get, reverse=True)[:4]
    print("series sanity: Bo3 p=0.65 ->", round(series_p(0.30*10, 0.30*8, 3), 3),
          "| Bo5 ->", round(series_p(0.30*10, 0.30*8, 5), 3))
    print("champion prob (synthetic, strongest first):",
          ", ".join(f"{t}={champ[t]:.3f}" for t in top))
    print("normalization + monotonicity checks passed; pipeline ready (no TI2026 output emitted)")
