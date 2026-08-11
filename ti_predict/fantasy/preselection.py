"""PHASE 4A: which three teams to pick BEFORE the War Banner is revealed.

The decision this module makes is not "which team scores most". It is a two-stage decision with a
real switching cost:

    stage A (now)      choose one team per role, before seeing anything
    stage B (reveal)   the account's banner appears; keep the team, or pay a roll token to change

So the value of an initial pick is not its expected score. It is the value of the POLICY that starts
from it: keep it when it is good enough, pay to move when it is not. A team that is slightly weaker
on average but rarely needs replacing can beat a team that is nominally the best and often does.

    V(T0) = E_B[ max( score_T0(B),  max_T score_T(B) - lambda ) ]

where lambda is the shadow price of a roll token in fantasy points. Setting lambda to zero recovers
the naive "pick the best on average", which is exactly the mistake this module exists to avoid.

Three things are integrated over rather than assumed:
  - the banner, because its draw weights are not published. Every legal banner is enumerated and the
    result is reported both under a uniform prior and as a distribution-free minimax regret;
  - the quality and trait multipliers, sampled across the full legal envelope;
  - the token price, carried as low / central / high scenarios.

Banner generation is independent of the team (see fantasy_rules.banner_generation_independence,
Tier 1), so the banner distribution is integrated once per role and reused for every candidate.
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np

from ti_predict.fantasy import baseline as bl

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED = 20260813
ROLES = ("core", "mid", "support")

# Per-slot multiplier envelope: quality tiers 0.10..1.50 times the trait band. Sampled, not assumed,
# because neither the quality roll weights nor the trait roll weights are published.
QUALITY_TIERS = (0.10, 0.30, 0.60, 1.00, 1.50)
TRAIT_BAND = (0.90, 2.10)

# Roll-token shadow price, as a fraction of a role's median banner score. The token budget for the
# group stage is about 40 across three banners, so a token buys a fraction of one slot upgrade.
# Carried as three scenarios because the operation roll weights are unknown.
TOKEN_PRICE_SCENARIOS = {"low": 0.005, "central": 0.02, "high": 0.05}

# The coach suffixes whose trigger condition can be evaluated from the columns this project fetches.
# The other eight titles are not computable here and are handled as team-independent; see
# `coach_assumption` in the output.
COMPUTABLE_SUFFIXES = {
    "the Underdog": 0.06, "the Decisive": 0.24, "the Clutch": 0.16, "the Lucky": 0.21,
}


def _series_geometry(rows):
    """(match -> position in its series, series -> number of maps), from the joined rows."""
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
        # "in games where the player loses"
        "the Underdog": not won,
        # "in games that last less than 25 minutes"
        "the Decisive": dur < 25 * 60,
        # "when playing the last possible match of a series": only a series that went the distance
        # has one, and it is its final map
        "the Clutch": n >= 3 and order.get(row["match_id"], -1) == n - 1,
        # "if the match time ends with an 8" -- the displayed clock's final digit
        "the Lucky": int(dur) % 10 == 8,
    }


def role_stat_series(rows, accounts, rules, order, length, suffix=None, min_series_maps=2):
    """{stat: {series_key: value}} for one role, with a coach suffix applied per game.

    Same four-level shape as the baseline -- complete pair only, top two maps, per series -- but the
    coach multiplier has to be applied at the GAME level, before the top-two selection, because that
    is where the client applies it.
    """
    stats = [s for s in bl.STAT_COLUMNS if s not in bl.UNAVAILABLE]
    need = len(accounts)
    bonus = COMPUTABLE_SUFFIXES.get(suffix, 0.0)
    per = defaultdict(lambda: defaultdict(dict))          # series -> match -> account -> {stat: v}
    for r in rows:
        acct = int(r["account_id"])
        if acct not in accounts:
            continue
        mult = 1.0 + (bonus if (suffix and suffix_triggers(r, order, length)[suffix]) else 0.0)
        scored = {}
        for stat in stats:
            v = bl.map_score(r, stat, rules, False, "linear")
            if v is not None:
                scored[stat] = v * mult
        if scored:
            per[r["_series"]][r["match_id"]][acct] = scored
    out = defaultdict(dict)
    for sid, by_match in per.items():
        complete = [b for b in by_match.values() if len(b) == need]
        if len(complete) < min_series_maps:
            continue
        for stat in stats:
            vals = [sum(a[stat] for a in b.values()) / need
                    for b in complete if all(stat in a for a in b.values())]
            if vals:
                out[stat][sid] = sum(sorted(vals, reverse=True)[:2])
    return {k: dict(v) for k, v in out.items()}


def legal_banners(role, rules):
    """Every legal stat assignment for a role's period-0 colour layout."""
    return bl._combinations(rules["layout"][role], rules["pools"])


def team_matrix(tables, banner, series_index):
    """(teams x series) matrix of per-stat values for one banner, as a 3-d array."""
    n_stat = len(banner)
    orgs = sorted(tables)
    m = np.zeros((len(orgs), len(series_index), n_stat))
    mask = np.zeros((len(orgs), len(series_index)), dtype=bool)
    for i, org in enumerate(orgs):
        t = tables[org]
        for j, sid in enumerate(series_index):
            if all(sid in t.get(s, {}) for s in banner):
                mask[i, j] = True
                for k, s in enumerate(banner):
                    m[i, j, k] = t[s][sid]
    return orgs, m, mask


def role_analysis(role, rows, rules, order, length, roles_map, suffix=None,
                  weight_draws=200, seed=SEED):
    """For one role: P(team is the post-reveal optimum) over banners and weights, plus the values.

    Returns per team: the mean score across banner-weight draws, the fraction of draws in which it
    is the argmax, and the mean shortfall against the draw's best team (its regret).
    """
    rng = np.random.default_rng(seed)
    tables = {}
    for org, assign in roles_map.items():
        t = role_stat_series(rows, set(assign[role]), rules, order, length, suffix)
        if t:
            tables[org] = t
    if len(tables) < 2:
        return None
    series_index = sorted({sid for t in tables.values() for d in t.values() for sid in d})
    banners = legal_banners(role, rules)
    orgs = sorted(tables)
    n = len(orgs)
    scores, bests = [], []
    for banner in banners:
        _o, m, mask = team_matrix(tables, banner, series_index)
        usable = mask.any(axis=1)
        if usable.sum() < 2:
            continue
        # per-slot multiplier: a quality tier times a trait factor, drawn over the legal envelope
        q = rng.choice(QUALITY_TIERS, size=(weight_draws, len(banner)))
        tr = rng.uniform(TRAIT_BAND[0], TRAIT_BAND[1], size=(weight_draws, len(banner)))
        w = q * tr                                                    # (draws, slots)
        vals = np.einsum("ijk,dk->dij", m, w)                         # (draws, orgs, series)
        vals = np.where(mask[None, :, :], vals, -np.inf)
        period = vals.max(axis=2)                                     # best series per team
        period = np.where(usable[None, :], period, np.nan)
        scores.append(period)
        bests.append(np.nanmax(period, axis=1))
    if not scores:
        return None
    # (draws, teams) stacked over banners -- the regret DISTRIBUTION, not just its mean. The keep-
    # or-pay policy takes a maximum inside the expectation, so collapsing to a mean first would make
    # every candidate look identical: score + regret is the same number for everyone by definition.
    score = np.vstack(scores)
    best = np.concatenate(bests)
    regret = best[:, None] - score
    draws_total = score.shape[0]
    valid = ~np.isnan(score)
    wins = np.nansum(regret <= 1e-9, axis=0)
    with np.errstate(invalid="ignore"):
        mean_score = np.where(valid.sum(axis=0) > 0,
                              np.nansum(np.where(valid, score, 0.0), axis=0)
                              / np.maximum(valid.sum(axis=0), 1), np.nan)
    return {"role": role, "teams": orgs, "banners": len(scores), "draws": int(draws_total),
            "p_optimal": (wins / draws_total).tolist(),
            "mean_score": mean_score.tolist(),
            "usable_fraction": (valid.sum(axis=0) / draws_total).tolist(),
            "_score": score, "_regret": regret, "_best": best,
            "mean_best": float(np.nanmean(best)),
            "series_pool": len(series_index), "n_teams": n}


def policy_value(analysis, token_price_fraction):
    """V(T0) under the keep-or-pay policy, for every candidate initial team.

    lambda is expressed as a fraction of the role's mean best-banner score, so it scales with the
    role rather than being a raw number that means different things for a core and a support.
    """
    # Everything below is RELATIVE to the best team on that draw. A draw whose sampled multipliers
    # happen to be large inflates every score and every gap alike, so absolute regret would be
    # dominated by the weight scale rather than by the choice. Relative regret is scale-free, which
    # is also what makes one token price comparable across roles.
    lam = token_price_fraction
    best = analysis["_best"]
    score = analysis["_score"] / best[:, None]
    regret = 1.0 - score
    # V = E[ max(score_T0, best - lambda) ] = E[ score_T0 + max(0, regret_T0 - lambda) ]
    # The max stays INSIDE the expectation. Switching happens only on the draws where the gain is
    # worth the token, which is what separates candidates that are usually fine from candidates that
    # are occasionally excellent and often need replacing.
    gain = np.maximum(0.0, regret - lam)
    switch = (regret - lam) > 0
    with np.errstate(invalid="ignore"):
        v = np.nanmean(score + gain, axis=0)
        p_switch = np.nanmean(np.where(np.isnan(score), np.nan, switch.astype(float)), axis=0)
        mean_regret = np.nanmean(regret, axis=0)
        p90 = np.nanpercentile(np.where(np.isnan(score), np.nan, score + gain), 90, axis=0)
        p10 = np.nanpercentile(np.where(np.isnan(score), np.nan, score + gain), 10, axis=0)
        worst = np.nanmax(regret, axis=0)
    out = []
    for i, org in enumerate(analysis["teams"]):
        if not np.isfinite(v[i]):
            continue
        out.append({"organization": org,
                    "p_optimal": round(analysis["p_optimal"][i], 4),
                    "p_switch": round(float(p_switch[i]), 4),
                    "mean_score_absolute": round(float(analysis["mean_score"][i]), 1),
                    "mean_relative_score": round(float(np.nanmean(score[:, i])), 4),
                    "mean_relative_regret": round(float(mean_regret[i]), 4),
                    "worst_case_relative_regret": round(float(worst[i]), 4),
                    "p10": round(float(p10[i]), 4), "p90": round(float(p90[i]), 4),
                    "policy_value": round(float(v[i]), 5),
                    "usable_fraction": round(analysis["usable_fraction"][i], 3),
                    "token_price_relative": lam})
    out.sort(key=lambda e: -e["policy_value"])
    return out


def joint_coach_optimum(rows, rules, order, length, roles_map, suffixes, weight_draws=120):
    """The coach applies to all three banners, so the triple and the coach are chosen together.

    Because the three role scores ADD, for any fixed coach the best triple is simply the best team
    per role. The joint optimum is therefore a search over coaches, each evaluated at its own
    per-role argmax -- exact, not a heuristic, and far cheaper than 16^3.
    """
    results = {}
    for suffix in suffixes:
        total, picks = 0.0, {}
        for role in ROLES:
            a = role_analysis(role, rows, rules, order, length, roles_map, suffix,
                              weight_draws=weight_draws)
            if not a:
                continue
            pv = policy_value(a, TOKEN_PRICE_SCENARIOS["central"])
            picks[role] = pv[0]["organization"]
            total += pv[0]["policy_value"]
        results[suffix or "none"] = {"total_policy_value": round(total, 1), "picks": picks}
    return results


def build(weight_draws=200, seed=SEED):
    rules = bl.load_rules()
    rows, _dropped, _inactive = bl.load_stats()
    order, length = _series_geometry(rows)
    roles_map = bl.roles_from_roster()
    out = {"seed": seed, "weight_draws_per_banner": weight_draws,
           "token_price_scenarios": TOKEN_PRICE_SCENARIOS,
           "banner_independent_of_team": True,
           "coach_assumption": "Only the four suffixes whose condition is computable from the "
                               "fetched columns are applied per game (the Underdog, the Decisive, "
                               "the Clutch, the Lucky). The eight prefixes need hero identity and "
                               "the other four suffixes need first-blood timing, fountain kills or "
                               "Tormentor deaths, none of which this pipeline fetches; they are "
                               "treated as team-independent, which is stated rather than hidden.",
           "roles": {}}
    for role in ROLES:
        a = role_analysis(role, rows, rules, order, length, roles_map, None, weight_draws, seed)
        if not a:
            continue
        out["roles"][role] = {
            "mean_best": round(a["mean_best"], 1),
            "banners_enumerated": a["banners"], "draws": a["draws"],
            "series_pool": a["series_pool"],
            "by_token_price": {k: policy_value(a, v)
                               for k, v in TOKEN_PRICE_SCENARIOS.items()}}
    out["coach"] = joint_coach_optimum(rows, rules, order, length, roles_map,
                                       [None] + sorted(COMPUTABLE_SUFFIXES), weight_draws=80)
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--out", default="")
    a.add_argument("--draws", type=int, default=200)
    a.add_argument("--top", type=int, default=5)
    a = a.parse_args(argv)
    r = build(a.draws)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    print(f"PRE-BANNER INITIAL SELECTION (seed {r['seed']}, "
          f"{r['weight_draws_per_banner']} weight draws per banner)")
    for role, v in r["roles"].items():
        print(f"\n{role}: {v['banners_enumerated']} legal banners x {v['draws']} draws, "
              f"{v['series_pool']} series")
        for scen in ("low", "central", "high"):
            head = v["by_token_price"][scen][:a.top]
            names = ", ".join(f"{e['organization']} (V={e['policy_value']:.4f}, "
                              f"P*={e['p_optimal']:.2f}, Pswitch={e['p_switch']:.2f})"
                              for e in head)
            print(f"  token={scen:<8} {names}")
    print("\ncoach (computable suffixes only):")
    for suffix, v in sorted(r["coach"].items(), key=lambda kv: -kv[1]["total_policy_value"]):
        print(f"  {suffix:<16} total={v['total_policy_value']:>9.0f}  {v['picks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
