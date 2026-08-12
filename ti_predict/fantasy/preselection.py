"""PHASE 4A: which three teams to pick BEFORE the War Banner exists.

Two-stage decision with a real switching cost:

    stage A (now)      choose one team per role, blind
    stage B (reveal)   the banner appears; re-pick the coach for free, keep the team, or pay a
                       roll token to change it

    V(T0) = E_B[ max( score_T0(B),  max_T score_T(B) - lambda ) ]

Four corrections against the previous version of this module, each of which moves numbers:

1. EVENT-LEVEL AGGREGATION. A fantasy period keeps the best series *within that period*. The old
   code pooled every series from all five historical events and took one global maximum, which
   rewarded teams simply for having attended more events. Each historical event is now its own
   period-like observation.

2. TI EXPOSURE, NOT HISTORICAL EXPOSURE. How many series a team gets at TI comes from the frozen
   group-stage track's record-bucket probabilities, not from how many series it happened to play in
   the training window. History supplies the per-series score distribution; TI supplies the number
   of draws.

3. EXACT BANNER. Traits and quality tiers are evaluated by banner_model, with adjacency and
   banner-level conditions. The old Uniform(0.9, 2.1) scalar per slot is withdrawn.

4. ALL SIXTEEN TEAMS IN EVERY DRAW. A role with no joint sample gets a cold-start posterior drawn
   from the role-level pool with inflated spread, and it competes in every argmax rather than being
   dropped and mentioned in a footnote.
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np

from ti_predict.fantasy import banner_model as bm
from ti_predict.fantasy import baseline as bl
from ti_predict.fantasy import exposure as ex

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED = 20260813
ROLES = ("core", "mid", "support")
# A cold-start role has no joint observation of its current pair; see add_cold_start for how that
# is represented without inventing an advantage.
TOKEN_LAMBDAS = tuple(round(x, 4) for x in np.arange(0.0, 0.201, 0.005))


# The coach suffixes whose trigger condition can be evaluated from the columns this project fetches.
# The eight prefixes need hero identity AND Valve's hero-category lists, and the other four suffixes
# need first-blood timing, fountain kills or Tormentor deaths. None of those is available, which is
# why the coach cannot be closed and the gate reports HOLD rather than a pick.
COMPUTABLE_SUFFIXES = {
    "the Underdog": 0.06, "the Decisive": 0.24, "the Clutch": 0.16, "the Lucky": 0.21,
}


def _series_geometry(rows):
    """(match -> position in its series, series -> number of maps)."""
    per = defaultdict(set)
    times = {}
    for r in rows:
        per[r["_series"]].add(r["match_id"])
        times[r["match_id"]] = int(r["start_time"])
    order, length = {}, {}
    for sid, matches in per.items():
        ordered = sorted(matches, key=lambda m: times[m])
        length[sid] = len(ordered)
        for i, m in enumerate(ordered):
            order[m] = i
    return order, length


def suffix_triggers(row, order, length):
    """Which computable suffix conditions this player-map satisfies."""
    dur = bl._f(row, "duration") or 0.0
    won = (row.get("win") == "1")
    n = length.get(row["_series"], 0)
    return {
        "the Underdog": not won,
        "the Decisive": dur < 25 * 60,
        # only a series that went the distance has a last-possible game, and it is its final map
        "the Clutch": n >= 3 and order.get(row["match_id"], -1) == n - 1,
        "the Lucky": int(dur) % 10 == 8,
    }


def _series_by_event(rows, accounts, rules, min_series_maps=2):
    """{event: {series: {stat: role score}}} -- kept per event, never pooled across events."""
    stats = [s for s in bl.STAT_COLUMNS if s not in bl.UNAVAILABLE]
    need = len(accounts)
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        acct = int(r["account_id"])
        if acct not in accounts:
            continue
        scored = {}
        for stat in stats:
            v = bl.map_score(r, stat, rules, False, "linear")
            if v is not None:
                scored[stat] = v
        if scored:
            per[r["_league"]][r["_series"]][r["match_id"]][acct] = scored
    out = defaultdict(dict)
    for event, ser in per.items():
        for sid, by_match in ser.items():
            complete = [b for b in by_match.values() if len(b) == need]
            if len(complete) < min_series_maps:
                continue
            row = {}
            for stat in stats:
                vals = [sum(a[stat] for a in b.values()) / need
                        for b in complete if all(stat in a for a in b.values())]
                if vals:
                    row[stat] = sum(sorted(vals, reverse=True)[:2])
            if row:
                out[event][sid] = row
    return {k: dict(v) for k, v in out.items()}


def series_pool(rows, roles_map, rules):
    """Per role and organisation: the per-series stat matrix, plus the event structure.

    The matrix is the per-SERIES layer. Event membership is carried alongside so that a projection
    can respect the fact that a period keeps one series, and so that duplicating an event cannot
    inflate anything: the projection samples series, and the number of draws comes from TI.
    """
    stats = [s for s in bl.STAT_COLUMNS if s not in bl.UNAVAILABLE]
    out = {}
    for role in ROLES:
        out[role] = {}
        for org, assign in roles_map.items():
            by_event = _series_by_event(rows, set(assign[role]), rules)
            rowsx, events = [], []
            for event, ser in sorted(by_event.items()):
                for sid, vec in sorted(ser.items()):
                    if all(s in vec for s in stats):
                        rowsx.append([vec[s] for s in stats])
                        events.append(event)
            if rowsx:
                out[role][org] = {"matrix": np.array(rowsx), "events": events,
                                  "n_events": len(set(events)), "n_series": len(rowsx),
                                  "cold_start": False}
    return out, stats


def add_cold_start(pools, roles_map, _rng=None):
    """Give every organisation a distribution for every role, honest where there is no observation.

    How NOT to do this: pool every team's series together and widen the spread. The period score is
    a MAXIMUM over series, so a wider per-series distribution wins more maxima; widening for
    ignorance hands the unobserved team a manufactured advantage, and in a first attempt it put all
    three cold-start roles at the top of their tables. Uncertainty about a team is not extra
    volatility within that team.

    What is done instead: a cold-start role is marked as a DONOR sampler. On every simulation draw
    it borrows one randomly chosen observed team's series distribution for that role. Its mean is
    the field mean, its per-series spread is a real team's spread, and the uncertainty lives across
    draws -- which is where "we do not know which team this behaves like" actually belongs.
    """
    for role in ROLES:
        have = {o: v for o, v in pools[role].items() if not v.get("cold_start")}
        if not have:
            continue
        donors = sorted(have)
        for org in roles_map:
            if org in have:
                continue
            pools[role][org] = {"matrix": None, "donors": donors, "events": ["cold-start"],
                                "n_events": 0, "n_series": 0, "cold_start": True}
    return pools


def exposure_draws(rng, probs, org, n):
    """Number of TI series for this organisation, drawn from the frozen track's bucket mix."""
    dist = ex.exposure_distribution(probs)[org]["dist"]
    counts = np.array(sorted(dist))
    p = np.array([dist[c] for c in counts], dtype=float)
    p = p / p.sum()
    return rng.choice(counts, size=n, p=p)


def simulate(role, pools, stat_names, rules, probs, draws=4000, family="uniform", seed=SEED,
             banner="exact", exposure="ti"):
    """One TI period per draw per organisation, under a sampled banner. Returns the score matrix."""
    rng = np.random.default_rng(seed)
    orgs = sorted(pools[role])
    combos = bl._combinations(rules["layout"][role], rules["pools"])
    idx_of = {s: i for i, s in enumerate(stat_names)}
    combos = [c for c in combos if all(s in idx_of for s in c)]
    n_series = {o: exposure_draws(rng, probs, o, draws) if o in ex.exposure_distribution(probs)
                else np.full(draws, 5) for o in orgs}
    score = np.zeros((draws, len(orgs)))
    for d in range(draws):
        combo = combos[rng.integers(len(combos))]
        if banner == "exact":
            q, t = bm.sample_banner_state(rng, family)
            w = np.array(bm.slot_weights(q, t))
        else:
            # the withdrawn stand-in, kept only so the attribution can measure what it cost
            w = rng.uniform(0.9, 2.1, size=3) * rng.choice(bm.QUALITY, size=3)
        
        cols = [idx_of[s] for s in combo]
        for j, org in enumerate(orgs):
            src = pools[role][org]
            if src["cold_start"]:
                # borrow one observed team's distribution for this draw; the uncertainty is which
                # team it behaves like, not extra volatility inside it
                src = pools[role][src["donors"][rng.integers(len(src["donors"]))]]
            m = src["matrix"][:, cols]
            vals = m @ w
            k = int(n_series[org][d]) if exposure == "ti" else vals.shape[0]
            pick = rng.integers(0, vals.shape[0], size=k)
            score[d, j] = vals[pick].max()
    return orgs, score


def policy_table(orgs, score, lam):
    """Relative policy value, P(optimal), P(switch) and regret for one token price."""
    best = score.max(axis=1)
    rel = score / best[:, None]
    regret = 1.0 - rel
    v = np.maximum(rel, 1.0 - lam).mean(axis=0)
    out = []
    for i, org in enumerate(orgs):
        out.append({"organization": org,
                    "policy_value": round(float(v[i]), 5),
                    "p_optimal": round(float((regret[:, i] <= 1e-9).mean()), 4),
                    "p_switch": round(float(((regret[:, i] - lam) > 0).mean()), 4),
                    "mean_relative_score": round(float(rel[:, i].mean()), 4),
                    "worst_case_relative_regret": round(float(regret[:, i].max()), 4),
                    "p10": round(float(np.percentile(rel[:, i], 10)), 4),
                    "p90": round(float(np.percentile(rel[:, i], 90)), 4)})
    out.sort(key=lambda e: -e["policy_value"])
    return out


def lambda_breakpoints(orgs, score):
    """Where the argmax changes as the token price sweeps from zero upward."""
    prev, points = None, []
    for lam in TOKEN_LAMBDAS:
        top = policy_table(orgs, score, lam)[0]["organization"]
        if top != prev:
            points.append({"lambda": float(lam), "argmax": top})
            prev = top
    return points


def minimax_regret(orgs, score):
    """argmin over candidates of the worst regret they suffer on any simulated state."""
    best = score.max(axis=1)
    regret = 1.0 - score / best[:, None]
    worst = regret.max(axis=0)
    order = np.argsort(worst)
    return {"ranking": [{"organization": orgs[i], "worst_case_relative_regret": round(float(worst[i]), 4)}
                        for i in order],
            "argmin": orgs[int(order[0])]}


# The coach is chosen freely in stage B and applies to every player, so it cannot be optimised per
# role in stage A. Its eight prefixes are hero-conditional, and Valve's hero-category lists are
# rendered by a client tooltip that does not exist before the first team selection: the per-team
# trigger rates are STRUCTURALLY unobtainable now, not merely missing.
#
# What can still be done is bound it. A title multiplies a team's game score by (1 + b * p_T), with
# b at most 0.24 among the offered titles. Two teams differ only through (p_A - p_B), so the entire
# coach effect on a comparison is a per-team multiplicative perturbation of at most b. Sampling that
# perturbation and asking whether the decision survives is strictly more useful than refusing to
# decide on a fact that cannot be obtained.
MAX_COACH_BONUS = 0.24


def coach_perturbation(rng, n_teams, spread):
    """A per-team multiplicative factor standing in for an unknown coach trigger-rate differential.

    spread is the fraction of MAX_COACH_BONUS that the differential could reach. spread=1.0 is the
    pathological case where one team triggers the best title on every game and another on none.
    """
    return 1.0 + rng.uniform(0.0, MAX_COACH_BONUS * spread, size=n_teams)


def expected_regret(score):
    """Mean relative shortfall against the best team on the same draw."""
    best = score.max(axis=1)
    return (1.0 - score / best[:, None]).mean(axis=0)


def minimax_expected_regret(role, pools, stat_names, rules, probs, draws, families,
                            coach_spread=0.0, seed=SEED):
    """argmin over candidates of the WORST expected regret across the declared prior families.

    This is the criterion to use once the expected-value differences are smaller than the model
    error, which is where this problem ended up: the top candidates sit within about 0.1 percent of
    each other, so the argmax of expected value is not identifiable, while the team that is never
    badly wrong across the whole prior family is.
    """
    per_family = {}
    orgs = None
    for fam in families:
        o, score = simulate(role, pools, stat_names, rules, probs, draws, fam, seed)
        orgs = o
        if coach_spread:
            rng = np.random.default_rng(seed + 977)
            score = score * coach_perturbation(rng, score.shape[1], coach_spread)[None, :]
        per_family[fam] = expected_regret(score)
    worst = np.max(np.vstack([per_family[f] for f in families]), axis=0)
    order = np.argsort(worst)
    return {"teams": orgs,
            "by_family": {f: [round(float(x), 5) for x in per_family[f]] for f in families},
            "worst_expected_regret": [round(float(x), 5) for x in worst],
            "ranking": [{"organization": orgs[i],
                         "worst_expected_regret": round(float(worst[i]), 5)} for i in order],
            "argmin": orgs[int(order[0])],
            "runner_up": orgs[int(order[1])] if len(order) > 1 else None,
            "margin": round(float(worst[order[1]] - worst[order[0]]), 5) if len(order) > 1 else None}


def build(draws=4000, seed=SEED, families=("uniform",), banner="exact", exposure="ti"):
    rules = bl.load_rules()
    rows, _dropped, _inactive = bl.load_stats()
    roles_map = bl.roles_from_roster()
    probs, src = ex.frozen_bucket_probabilities()
    rng = np.random.default_rng(seed)
    pools, stat_names = series_pool(rows, roles_map, rules)
    cold = {role: sorted(set(roles_map) - set(pools[role])) for role in ROLES}
    pools = add_cold_start(pools, roles_map, rng)
    out = {"seed": seed, "draws_per_role": draws, "frozen_exposure_source": src,
           "cold_start_roles": cold, "prior_families": list(families),
           "banner_model": "exact three-slot evaluator (banner_model.slot_weights)",
           "roles": {}}
    for role in ROLES:
        orgs, score = simulate(role, pools, stat_names, rules, probs, draws, families[0], seed,
                               banner, exposure)
        out["roles"][role] = {
            "teams": orgs,
            "n_teams": len(orgs),
            "sample": {o: {"series": pools[role][o]["n_series"],
                           "events": pools[role][o]["n_events"],
                           "cold_start": pools[role][o]["cold_start"]} for o in orgs},
            "by_lambda": {str(l): policy_table(orgs, score, l) for l in (0.005, 0.02, 0.05)},
            "lambda_breakpoints": lambda_breakpoints(orgs, score),
            "minimax_regret": minimax_regret(orgs, score),
            "prior_family_check": {}}
        for fam in families[1:]:
            o2, s2 = simulate(role, pools, stat_names, rules, probs, max(1000, draws // 4),
                              fam, seed)
            out["roles"][role]["prior_family_check"][fam] = policy_table(o2, s2, 0.02)[0][
                "organization"]
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--out", default="")
    a.add_argument("--draws", type=int, default=4000)
    a.add_argument("--top", type=int, default=5)
    a.add_argument("--families", default=",".join(bm.PRIOR_FAMILIES))
    a = a.parse_args(argv)
    fams = tuple(x for x in a.families.split(",") if x)
    r = build(a.draws, families=fams)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    print(f"PRE-BANNER INITIAL SELECTION (corrected) seed={r['seed']} draws={r['draws_per_role']}")
    print(f"exposure from {r['frozen_exposure_source']}; cold-start {r['cold_start_roles']}")
    for role, v in r["roles"].items():
        print(f"\n{role}: {v['n_teams']} teams")
        for e in v["by_lambda"]["0.02"][:a.top]:
            s = v["sample"][e["organization"]]
            tag = " COLD-START" if s["cold_start"] else ""
            print(f"  V={e['policy_value']:.4f} P*={e['p_optimal']:.2f} "
                  f"Pswitch={e['p_switch']:.2f} rel={e['mean_relative_score']:.3f} "
                  f"{e['organization']}{tag} (series {s['series']}, events {s['events']})")
        print(f"  minimax-regret argmin: {v['minimax_regret']['argmin']}")
        print(f"  lambda breakpoints: {v['lambda_breakpoints']}")
        if v["prior_family_check"]:
            print(f"  prior families: {v['prior_family_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
