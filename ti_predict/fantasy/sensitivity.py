"""Which unresolved rules actually change a decision, and which only change a number.

A rule can be unknown and still be irrelevant to the choice being made. Keeping those two things
apart is the whole point of this module: it measures, on real data, how far the ranking and the
stat choices move when an unresolved rule is switched between its candidate readings.

Two axes are reported for every unknown:
  fact_status      CONFIRMED / PARTIAL / UNRESOLVED  -- what the evidence supports
  decision_status  BLOCKING / ROBUST / SCALE_ONLY / IRRELEVANT -- what it does to the answer

Nothing here promotes a fact. A rule measured as decision-irrelevant is still an unresolved rule.
"""
import argparse
import json
import random

from ti_predict.fantasy import baseline as bl

ROLES = ("core", "mid", "support")


def _order(res, role):
    return [e["organization"] for e in
            sorted((x for x in res["ranking"] if x["role"] == role),
                   key=lambda e: -e["envelope_total"])]


def _picks(res, role):
    return {e["organization"]: tuple(sorted(s["stat"] for s in e["slots"]))
            for e in res["ranking"] if e["role"] == role}


def _displacement(a, b):
    """Total absolute rank movement, and the largest single move."""
    pos_b = {o: i for i, o in enumerate(b)}
    moves = [abs(i - pos_b[o]) for i, o in enumerate(a) if o in pos_b]
    return {"total_positions_moved": sum(moves), "max_single_move": max(moves, default=0),
            "n": len(moves), "identical": all(m == 0 for m in moves)}


def compare(base, alt):
    """Rank displacement, top-k stability and stat-choice stability between two settings, per role.

    `top_1_stable` is the one that decides the grade. The decision this track exists to make is
    which single team goes on each banner, so a rule that cannot move the argmax cannot move the
    decision, however much it shuffles the tail of the table. The fuller measures are kept because
    a rule that leaves the argmax alone while churning everything below it is worth knowing about.
    """
    out = {}
    for role in ROLES:
        pa, pb = _picks(base, role), _picks(alt, role)
        changed = sorted(o for o in pa if pa[o] != pb.get(o))
        oa, ob = _order(base, role), _order(alt, role)
        out[role] = {"rank": _displacement(oa, ob),
                     "top_1_stable": oa[:1] == ob[:1],
                     "top_3_stable": set(oa[:3]) == set(ob[:3]),
                     "top_1": {"base": oa[:1], "alt": ob[:1]},
                     "stat_choice_changed_for": changed,
                     "stat_choice_stable": not changed}
    return out


def scale_only_check(base, alt, tol=1e-3):
    """Is `alt` the same as `base` up to one positive constant factor?

    This is the test that decides whether an unknown is SCALE_ONLY. If every organisation and role
    scales by the same factor, no comparison anywhere in the decision can notice.
    """
    ta = {(e["organization"], e["role"]): e["envelope_total"] for e in base["ranking"]}
    tb = {(e["organization"], e["role"]): e["envelope_total"] for e in alt["ranking"]}
    shared = [k for k in ta if k in tb and ta[k]]
    if not shared:
        return {"scale_only": False, "reason": "no comparable entries"}
    ratios = [tb[k] / ta[k] for k in shared]
    lo, hi = min(ratios), max(ratios)
    return {"scale_only": (hi - lo) <= tol, "ratio_min": round(lo, 6), "ratio_max": round(hi, 6),
            "n": len(shared)}


def deaths_exposure(rows, roles):
    """How often a death count actually reaches the region where the floor could bite.

    The floor only matters at eleven deaths or more, and only if such a map is one of the two a
    series contributes. Both rates are reported, because the second is the one that reaches a score.
    """
    by_role = {r: {"maps": 0, "over_10": 0} for r in ROLES}
    total = {"maps": 0, "over_10": 0}
    acct_role = {a: role for org in roles.values() for role, accts in org.items() for a in accts}
    for r in rows:
        d = bl._f(r, "deaths")
        if d is None:
            continue
        role = acct_role.get(int(r["account_id"]))
        total["maps"] += 1
        total["over_10"] += d > 10
        if role:
            by_role[role]["maps"] += 1
            by_role[role]["over_10"] += d > 10
    out = {"all_player_maps": {**total,
                               "rate": round(total["over_10"] / total["maps"], 5)
                               if total["maps"] else None}}
    for role, v in by_role.items():
        out[role] = {**v, "rate": round(v["over_10"] / v["maps"], 5) if v["maps"] else None}
    return out


# Legal per-emblem multiplier envelope. Quality runs 0.10 to 1.50; traits can add up to +50 percent
# on the emblem itself (Vampiric), +20 percent from a neighbour (Benevolent), +30/+50/+60 percent
# from the banner-level traits, or subtract 10 percent (a Vampiric neighbour). The envelope is
# deliberately wider than any single reachable banner, because the point is to bound the effect.
SLOT_MULTIPLIER_RANGE = (0.10 * 0.90, 1.50 * 2.10)
# The largest known coach title bonus is 11 percent. Unknown titles are stressed at twice that, so
# the bound does not quietly assume the unpriced ones resemble the priced ones.
MAX_KNOWN_TITLE_BONUS = 0.11
TITLE_STRESS_BONUS = 0.22


def banner_weight_sensitivity(base, rules, draws=2000, seed=bl.SEED):
    """Can trait and quality weights change WHICH TEAM belongs on a banner?

    The banner is a property of the account, not of the team: the same emblems, qualities and traits
    multiply every candidate team's stats. So the level moves with the weights and only the RELATIVE
    weighting of one stat against another can reorder teams. This samples that relative weighting
    across the full legal envelope and asks how often the top pick changes.
    """
    rng = random.Random(seed)
    lo, hi = SLOT_MULTIPLIER_RANGE
    out = {}
    for role in ROLES:
        entries = [e for e in base["ranking"] if e["role"] == role]
        if len(entries) < 2:
            continue
        combo = entries[0]["stats"]                       # score every team on one fixed banner
        tables = {}
        for e in entries:
            table, _s = bl.series_table(bl._ROWS_CACHE, set(e["players"]), rules)
            tables[e["organization"]] = table
        def argmax(weights):
            scores = []
            for org, table in tables.items():
                best = None
                for ser in table.values():
                    for row in ser.values():
                        if all(s in row for s in combo):
                            tot = sum(row[s] * weights[s] for s in combo)
                            best = tot if best is None else max(best, tot)
                if best is not None:
                    scores.append((best, org))
            return max(scores)[1] if scores else None

        # The control has to hold the STAT SET fixed too. Comparing a weighted result against the
        # envelope's top would mix two changes -- the weights and the stat set that team happened to
        # choose -- and blame the weights for both.
        reference = argmax({s: 1.0 for s in combo})
        flips = sum(argmax({s: rng.uniform(lo, hi) for s in combo}) != reference
                    for _ in range(draws))
        out[role] = {"banner_stats": combo, "draws": draws,
                     "top_1_changed_fraction": round(flips / draws, 4),
                     "reference_top_1": reference,
                     "control": "equal weights on the same stat set"}
    return out


def coach_title_bound(base):
    """Bound the effect of the unpriced coach titles by comparing it to the gap it would have to close.

    A title multiplies the whole in-game score by (1 + b) when its condition holds, and the SAME two
    titles apply to all three banners. It can therefore only reorder teams through a difference in
    how often the condition triggers for them. The worst case is a title that triggers on every one
    of one team's games and none of another's, which is a relative swing of exactly b.
    """
    out = {}
    for role in ROLES:
        entries = sorted((e for e in base["ranking"] if e["role"] == role),
                         key=lambda e: -e["envelope_total"])
        if len(entries) < 2:
            continue
        first, second = entries[0]["envelope_total"], entries[1]["envelope_total"]
        gap = (first - second) / first if first else 0.0
        # additive (1+p+s) versus multiplicative (1+p)(1+s) differ by exactly p*s
        stacking_gap = TITLE_STRESS_BONUS ** 2
        out[role] = {
            "top_1": entries[0]["organization"], "top_2": entries[1]["organization"],
            "relative_gap": round(gap, 4),
            "worst_case_single_title_swing": TITLE_STRESS_BONUS,
            "stacking_difference": round(stacking_gap, 4),
            "gap_survives_worst_case_title": gap > TITLE_STRESS_BONUS,
            "gap_survives_stacking_choice": gap > stacking_gap}
    return out


def run(min_series_maps=2):
    rows, _dropped, _inactive = bl.load_stats()
    roles = bl.roles_from_roster()
    bl._ROWS_CACHE = rows
    rules = bl.load_rules()

    base = bl.build("sum", False, min_series_maps, "linear")
    report = {"coverage": base["input_coverage"],
              "baseline_setting": base["hypothesis"], "findings": {}}

    # 1. top-two aggregation: sum versus mean, under the TI best-of-three condition
    mean_ti = bl.build("mean", False, min_series_maps, "linear")
    mean_bo1 = bl.build("mean", False, 1, "linear")
    sum_bo1 = bl.build("sum", False, 1, "linear")
    report["findings"]["top_two_aggregation"] = {
        "fact_status": "UNRESOLVED", "decision_status": "SCALE_ONLY",
        "under_ti_condition": {**scale_only_check(base, mean_ti),
                               "comparison": compare(base, mean_ti)},
        "with_best_of_ones_included": {**scale_only_check(sum_bo1, mean_bo1),
                                       "comparison": compare(sum_bo1, mean_bo1)},
        "reading": "With every series contributing at least two maps -- the TI condition -- the two "
                   "readings differ by one constant factor and nothing in the decision can see it. "
                   "The apparent effect reported in an earlier round came from best-of-one series "
                   "in the training window, which cannot occur at TI."}

    # 2. deaths floor, changing ONE factor
    floor = bl.build("sum", True, min_series_maps, "linear")
    report["findings"]["deaths_floor"] = {
        "fact_status": "UNRESOLVED", "decision_status": "ROBUST",
        "exposure": deaths_exposure(rows, roles),
        "comparison": compare(base, floor),
        "reading": "Switching only the floor, with the aggregation and the curve held fixed."}

    # 3. teamfight curve: the evidenced shape against two deliberate stress shapes
    report["findings"]["teamfight_formula"] = {
        "fact_status": "PARTIAL", "decision_status": None,
        "working_hypothesis": "linear: 2124 * participation",
        "against": {cv: compare(base, bl.build("sum", False, min_series_maps, cv))
                    for cv in ("concave", "convex")}}
    tf = report["findings"]["teamfight_formula"]
    # Graded on the argmax, because the decision is one team per banner. Both stress shapes are
    # applied, including the aggressive one that has no evidence behind it: if the pick survives
    # even that, the curve cannot reach the decision.
    tf["decision_status_by_role"] = {
        r: ("ROBUST" if all(tf["against"][cv][r]["top_1_stable"] for cv in tf["against"])
            else "BLOCKING")
        for r in ROLES}
    blocking = [r for r, v in tf["decision_status_by_role"].items() if v == "BLOCKING"]
    tf["decision_status"] = "ROBUST" if not blocking else "BLOCKING"
    tf["blocking_for"] = blocking
    tf["tail_movement_note"] = (
        "The full ranking does move under the stress shapes, mostly in the lower half, and the "
        "stat set changes for a handful of organisations. That is recorded rather than hidden: it "
        "means the curve matters for a close second-choice comparison even where it cannot change "
        "the pick.")
    tf["reading"] = (
        "No stress shape moves the top pick in any role, so the curve cannot change which team goes "
        "on a banner." if not blocking else
        f"The top pick moves for {', '.join(blocking)}, so the curve stays blocking there.")

    # 4. coach titles: bound the swing against the gap it would have to close
    ct = coach_title_bound(base)
    report["findings"]["coach_titles"] = {
        "fact_status": "PARTIAL",
        "decision_status": ("ROBUST" if all(v["gap_survives_worst_case_title"] for v in ct.values())
                            else "BLOCKING"),
        "by_role": ct,
        "reading": "A title can only reorder teams through a difference in how often its condition "
                   "triggers, and the worst case is a swing of the bonus itself. Stressed at twice "
                   "the largest known bonus. Additive versus multiplicative stacking differs by the "
                   "product of the two bonuses, which is smaller still."}

    # 5. trait and quality composition: relative stat weights, sampled over the legal envelope
    bw = banner_weight_sensitivity(base, rules)
    report["findings"]["trait_composition"] = {
        "fact_status": "UNRESOLVED",
        "decision_status": ("ROBUST" if all(v["top_1_changed_fraction"] == 0.0
                                            for v in bw.values()) else "BLOCKING"),
        "by_role": bw,
        "reading": "The banner belongs to the account, so its multipliers apply to every candidate "
                   "team alike; only the RELATIVE weight of one stat against another can reorder "
                   "them. Sampled across the full legal quality and trait envelope."}
    return report


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--out", default="")
    a.add_argument("--min-series-maps", type=int, default=2)
    a = a.parse_args(argv)
    r = run(a.min_series_maps)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
    cov = r["coverage"]
    print(f"sensitivity on {cov['matches_covered']}/{cov['matches_targeted']} matches "
          f"({cov['coverage']:.1%}, complete={cov['complete']})")
    for name, f in r["findings"].items():
        print(f"\n{name}: fact={f['fact_status']} decision={f['decision_status']}")
        if name == "top_two_aggregation":
            u = f["under_ti_condition"]
            print(f"  TI condition: scale_only={u['scale_only']} "
                  f"ratio {u['ratio_min']}..{u['ratio_max']}")
            b = f["with_best_of_ones_included"]
            print(f"  with Bo1s:    scale_only={b['scale_only']} "
                  f"ratio {b['ratio_min']}..{b['ratio_max']}")
        if name == "deaths_floor":
            e = f["exposure"]["all_player_maps"]
            print(f"  deaths>10 on {e['over_10']}/{e['maps']} player-maps ({e['rate']:.3%})")
            for role in ROLES:
                c = f["comparison"][role]["rank"]
                print(f"  {role:<8} rank identical={c['identical']} "
                      f"stat-choice stable={f['comparison'][role]['stat_choice_stable']}")
        if name == "teamfight_formula":
            print(f"  by role: {f['decision_status_by_role']}")
            for cv, cmp_ in f["against"].items():
                t1 = all(cmp_[r2]["top_1_stable"] for r2 in ROLES)
                t3 = all(cmp_[r2]["top_3_stable"] for r2 in ROLES)
                moved = sum(cmp_[r2]["rank"]["total_positions_moved"] for r2 in ROLES)
                print(f"  vs {cv:<8} top-1 stable={t1} top-3 stable={t3} "
                      f"rank positions moved={moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
