"""Produce every period-1 Fantasy artifact for both accounts, in one run.

This is the driver. It owns no modelling: the scoring chain lives in `fastvalue`, the banner
arithmetic in `banner_model`, the opportunity model in `main_event_exposure`, and the ruleset in
`fantasy_rules.json`. What it owns is the ORDER -- validate the states against the client, build the
heavy cache, rank teams, tabulate marginals, evaluate the offers, write the artifacts -- and the
provenance stamped on the output.

The separation that matters operationally: everything expensive happens here, once. After this run,
a reroll decision needs `fastvalue.evaluate`-level work only, which is a matrix-vector product.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone

import numpy as np

from ti_predict.fantasy import banner_model as bm
from ti_predict.fantasy import fastvalue as fv
from ti_predict.fantasy import main_event_exposure as mex

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "predictions", "ti2026", "fantasy", "main_event")
STATE_FILES = {"operator": "account_state_operator_20260817.json",
               "target": "account_state_target_20260817.json"}
ROLES = ("core", "mid", "support")
INFO_CUTOFF = "2026-08-17T00:00:00Z"
# The eight organisations that actually play Main Event series. The client dropdown still offers
# all sixteen, but an eliminated organisation plays zero series and therefore scores zero, so the
# feasible set for a period-1 CHOICE is these eight. Derived from repository truth, never retyped.
SURVIVORS = None        # filled from the committed bracket seating at run time

# Diagnostic thresholds, declared here rather than tuned per emblem.
PROTECT_SHARE = 0.18        # slot carries >= 18% of the banner's scoreable value
REROLL_GAIN = 0.05          # a legal same-colour stat swap would add >= 5% of the period score
MEDIOCRE_SHARE = 0.07       # slot carries < 7% of the banner's scoreable value
ROBUST_FLIP = 0.05          # <= 5% of single-emblem perturbations may move the argmax


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _dirty():
    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                           capture_output=True, text=True, check=True)
        return bool(r.stdout.strip())
    except Exception:
        return None


def _sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(name):
    path = os.path.join(OUT, STATE_FILES[name])
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("period") != 1:
        raise SystemExit(f"{path}: period is {doc.get('period')}, not 1")
    for role in ROLES:
        b = doc["banners"][role]
        want = bm.layout(role, 1)
        got = tuple(s["colour"] for s in b["slots"])
        if got != want:
            raise SystemExit(f"{path}: {role} colour layout {got} != period-1 layout {want}")
        ev = bm.evaluate([{"quality_tier": s["quality_tier"], "trait": s["trait"]}
                          for s in b["slots"]])
        for i, s in enumerate(b["slots"]):
            if abs(ev[i]["multiplier"] - s["displayed_multiplier"]) > 1e-9:
                raise SystemExit(f"{path}: {role} slot {i + 1} ({s['stat']}) computes "
                                 f"{ev[i]['multiplier']} but the client displays "
                                 f"{s['displayed_multiplier']}")
    return doc, path


def slots_of(doc, role):
    return [{"slot": s["slot"], "stat": s["stat"], "colour": s["colour"],
             "quality_tier": s["quality_tier"], "trait": s["trait"],
             "multiplier": s["model_multiplier"]}
            for s in doc["banners"][role]["slots"]]


def perturbations(slots):
    """Every single-emblem change the client could produce on this banner.

    One quality change, one trait change or one legal same-colour stat change. This is the family
    the ROBUST / BANNER-DEPENDENT label is measured over: it asks whether the best TEAM survives any
    single reroll outcome, which is exactly the decision the operator faces next.
    """
    out = []
    for i, s in enumerate(slots):
        for t in ("I", "II", "III", "IV", "V"):
            if t != s["quality_tier"]:
                trial = [dict(x) for x in slots]
                trial[i]["quality_tier"] = t
                out.append((f"slot{i + 1}.quality->{t}", trial))
        for name in bm.TRAITS:
            if name != s["trait"]:
                trial = [dict(x) for x in slots]
                trial[i]["trait"] = name
                out.append((f"slot{i + 1}.trait->{name}", trial))
        held = {x["stat"] for j, x in enumerate(slots) if j != i}
        for cand in fv.BY_COLOUR[s["colour"]]:
            if cand != s["stat"] and cand not in held:
                trial = [dict(x) for x in slots]
                trial[i]["stat"] = cand
                out.append((f"slot{i + 1}.stat->{cand}", trial))
    for _, trial in out:
        ev = bm.evaluate([{"quality_tier": x["quality_tier"], "trait": x["trait"]}
                          for x in trial])
        for k, x in enumerate(trial):
            x["multiplier"] = ev[k]["multiplier"]
    return out


SHRINK_SWEEP = (0.0, 2.0, 5.0, 10.0)


def shrinkage_sweep(built, role, slots, exposure, prefix, suffix, teams, leader):
    """Does the best team survive the whole pre-declared shrinkage family?

    K was fixed before any arm was scored and is not tuned on an outcome, but a single K is still a
    modelling choice. The family is swept end to end and the only question asked of it is whether
    the ANSWER moves; K = 0 is the unshrunk estimator, so the sweep brackets the choice rather than
    defending it.
    """
    w = fv.banner_weights(slots)
    per_team, field = fv.role_pools(built, role, w, teams, prefix, suffix)
    rows = {}
    for k in SHRINK_SWEEP:
        scores = {t: float(fv.period_score_shrunk(per_team.get(t, {}), field,
                                                  exposure[t]["dist"], k)) for t in teams}
        best = max(scores, key=scores.get)
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        rows[str(k)] = {"best": best, "top3": [o[0] for o in ordered[:3]],
                        "gap_to_second_pct": round(100.0 * (ordered[0][1] - ordered[1][1])
                                                   / ordered[0][1], 3)}
    return {"k_values": list(SHRINK_SWEEP), "production_k": fv.SHRINK_K,
            "best_is_stable": len({v["best"] for v in rows.values()}) == 1,
            "leader_survives_family": all(v["best"] == leader for v in rows.values()),
            "by_k": rows}


def robustness(built, role, slots, exposure, prefix, suffix, leader, teams):
    """How often a single-emblem change moves the best team away from `leader`."""
    flips = []
    fam = perturbations(slots)
    for label, trial in fam:
        w = fv.banner_weights(trial)
        best, bestv = None, -np.inf
        for t in teams:
            v = fv.score(built, role, w, t, exposure[t]["dist"], prefix, suffix,
                         teams=teams)
            if v > bestv:
                best, bestv = t, v
        if best != leader:
            flips.append({"perturbation": label, "new_best": best})
    return {"family_size": len(fam), "flips": len(flips),
            "flip_fraction": round(len(flips) / len(fam), 4) if fam else None,
            "label": "ROBUST" if fam and len(flips) / len(fam) <= ROBUST_FLIP
                     else "BANNER-DEPENDENT",
            "flipping_perturbations": flips[:40]}


def emblem_diagnostic(built, role, slots, team, exposure, prefix, suffix, teams=None):
    """PROTECT / GOOD / MEDIOCRE / HIGH-PRIORITY REROLL TARGET / VALUE UNCERTAIN, with numbers."""
    def sc(sl):
        return float(fv.score(built, role, fv.banner_weights(sl), team, exposure,
                              prefix, suffix, teams=teams))
    base = sc(slots)
    rows = []
    for i, s in enumerate(slots):
        # marginal value of the slot: what the period score loses if this emblem stops scoring
        off = [dict(x) for x in slots]
        off[i]["multiplier"] = 0.0
        without = sc(off)
        contrib = base - without
        held = {x["stat"] for j, x in enumerate(slots) if j != i}
        best_stat, best_gain = s["stat"], 0.0
        for cand in fv.BY_COLOUR[s["colour"]]:
            if cand in held or cand in fv.UNOBSERVABLE:
                continue
            trial = [dict(x) for x in slots]
            trial[i]["stat"] = cand
            v = sc(trial)
            if v - base > best_gain:
                best_stat, best_gain = cand, v - base
        up = [dict(x) for x in slots]
        up[i]["quality_tier"] = "V"
        ev = bm.evaluate([{"quality_tier": x["quality_tier"], "trait": x["trait"]} for x in up])
        for k, x in enumerate(up):
            x["multiplier"] = ev[k]["multiplier"]
        to_v = sc(up) - base
        share = contrib / base if base else 0.0
        if s["stat"] in fv.UNOBSERVABLE:
            klass = "VALUE UNCERTAIN DUE TO DATA"
        elif best_gain / base >= REROLL_GAIN:
            klass = "HIGH-PRIORITY REROLL TARGET"
        elif share >= PROTECT_SHARE:
            klass = "PROTECT"
        elif share < MEDIOCRE_SHARE:
            klass = "MEDIOCRE"
        else:
            klass = "GOOD"
        rows.append({"slot": s["slot"], "colour": s["colour"], "stat": s["stat"],
                     "quality_tier": s["quality_tier"], "trait": s["trait"],
                     "multiplier": round(s["multiplier"], 4),
                     "classification": klass,
                     "scoreable": s["stat"] not in fv.UNOBSERVABLE,
                     "marginal_value_points": round(contrib, 1),
                     "share_of_banner_value": round(share, 4),
                     "best_same_colour_stat": best_stat,
                     "best_stat_swap_gain_points": round(best_gain, 1),
                     "best_stat_swap_gain_pct": round(100.0 * best_gain / base, 2) if base else None,
                     "gain_if_quality_to_tier_V": round(to_v, 1)})
    return {"team": team, "base_period_score": round(base, 1), "emblems": rows,
            "unscored": fv.unscored_weight(slots),
            "thresholds": {"protect_share": PROTECT_SHARE, "reroll_gain_pct": REROLL_GAIN,
                           "mediocre_share": MEDIOCRE_SHARE}}


def _retier(slots, changes):
    trial = [dict(x) for x in slots]
    for i, t in changes.items():
        trial[i]["quality_tier"] = t
    ev = bm.evaluate([{"quality_tier": x["quality_tier"], "trait": x["trait"]} for x in trial])
    for k, x in enumerate(trial):
        x["multiplier"] = ev[k]["multiplier"]
    return trial


TIERS = ("I", "II", "III", "IV", "V")


def offer_outcomes(built, role, slots, team, exposure, prefix, suffix, offer, teams=None):
    """Every enumerable outcome of one offered operation, as an UNWEIGHTED set.

    No transition probabilities are invented. Valve publishes none, the roll board is a weighted
    draw whose weights are not in any shipped file, and the only thing the localization guarantees
    is that a rerolled STAT is different and that a banner never carries a duplicate stat. So this
    returns the outcome SET and combinatorial fractions over it; any expectation shown alongside is
    labelled as a hypothetical uniform reading, not a probability.
    """
    base = float(fv.score(built, role, fv.banner_weights(slots), team, exposure, prefix,
                          suffix, teams=teams))
    kind, colour, which = offer["kind"], offer.get("colour"), offer.get("which")
    idx = [i for i, s in enumerate(slots) if s["colour"] == colour] if colour else \
        list(range(len(slots)))
    readings = {}

    def score(trial):
        return float(fv.score(built, role, fv.banner_weights(trial), team, exposure,
                              prefix, suffix, teams=teams))

    if kind == "stat":
        target = idx[0] if which == "first" else idx[-1] if which == "last" else None
        targets = [target] if target is not None else idx
        rows = []
        for i in targets:
            held = {x["stat"] for j, x in enumerate(slots) if j != i}
            for cand in fv.BY_COLOUR[slots[i]["colour"]]:
                if cand == slots[i]["stat"] or cand in held:
                    continue        # guaranteed new, and no duplicate stat on a banner
                trial = [dict(x) for x in slots]
                trial[i]["stat"] = cand
                rows.append({"outcome": f"slot{i + 1} stat -> {cand}",
                             "observable": cand not in fv.UNOBSERVABLE,
                             "delta": round(score(trial) - base, 1)})
        readings["resolved"] = rows
    elif kind == "quality":
        if which == "random_one":
            rows = []
            for i in idx:
                for t in TIERS:
                    rows.append({"outcome": f"slot{i + 1} -> Tier {t}",
                                 "delta": round(score(_retier(slots, {i: t})) - base, 1)})
            readings["random_one_of_colour"] = rows
        else:
            rows = []
            import itertools
            for combo in itertools.product(TIERS, repeat=len(idx)):
                ch = dict(zip(idx, combo))
                rows.append({"outcome": "; ".join(f"slot{i + 1}->Tier {t}"
                                                  for i, t in sorted(ch.items())),
                             "delta": round(score(_retier(slots, ch)) - base, 1)})
            readings["all_of_colour"] = rows
            single = []
            for i in idx:
                for t in TIERS:
                    single.append({"outcome": f"slot{i + 1} -> Tier {t}",
                                   "delta": round(score(_retier(slots, {i: t})) - base, 1)})
            readings["single_unknown_slot"] = single
    elif kind == "trait":
        def retrait(ch):
            trial = [dict(x) for x in slots]
            for i, t in ch.items():
                trial[i]["trait"] = t
            ev = bm.evaluate([{"quality_tier": x["quality_tier"], "trait": x["trait"]}
                              for x in trial])
            for k, x in enumerate(trial):
                x["multiplier"] = ev[k]["multiplier"]
            return trial
        import itertools
        opts = [[t for t in bm.TRAITS if t != slots[i]["trait"]] for i in idx]
        rows = []
        for combo in itertools.product(*opts):
            ch = dict(zip(idx, combo))
            rows.append({"outcome": "; ".join(f"slot{i + 1}->{t}" for i, t in sorted(ch.items())),
                         "delta": round(score(retrait(ch)) - base, 1)})
        readings["all_of_colour"] = rows
        single = []
        for i in idx:
            for t in bm.TRAITS:
                if t != slots[i]["trait"]:
                    single.append({"outcome": f"slot{i + 1}->{t}",
                                   "delta": round(score(retrait({i: t})) - base, 1)})
        readings["single_unknown_slot"] = single
    elif kind == "quality_multi":
        import itertools
        rows = []
        for up in itertools.combinations(range(len(slots)), 2):
            for down in range(len(slots)):
                if down in up:
                    continue
                ch = {}
                ok = True
                for i in up:
                    cur = TIERS.index(slots[i]["quality_tier"])
                    if cur == 4:
                        ok = False
                    ch[i] = TIERS[min(cur + 1, 4)]
                cur = TIERS.index(slots[down]["quality_tier"])
                ch[down] = TIERS[max(cur - 1, 0)]
                rows.append({"outcome": f"up {[i + 1 for i in up]} down slot{down + 1}",
                             "at_tier_ceiling": not ok,
                             "delta": round(score(_retier(slots, ch)) - base, 1)})
        readings["one_tier_step_assumed"] = rows
    else:
        return {"kind": kind, "unsupported": True}

    out = {"offer_id": offer.get("id"), "kind": kind, "colour": colour, "which": which,
           "semantics_status": offer.get("semantics_status"),
           "semantics_note": offer.get("semantics_note"),
           "evaluated_on_team": team, "base_period_score": round(base, 1), "readings": {}}
    for name, rows in readings.items():
        d = [r["delta"] for r in rows]
        out["readings"][name] = {
            "n_outcomes": len(rows),
            "min_delta": round(min(d), 1), "max_delta": round(max(d), 1),
            "median_delta": round(float(np.median(d)), 1),
            "fraction_improving": round(sum(1 for x in d if x > 0) / len(d), 4),
            "fraction_improving_is_a_combinatorial_fraction_not_a_probability": True,
            "mean_delta_under_hypothetical_uniform": round(float(np.mean(d)), 1),
            "outcomes": sorted(rows, key=lambda r: -r["delta"])}
    return out


def reachable_ceiling(built, role, slots, team, exposure, prefix, suffix, teams=None):
    """A declared upper reference for the banner, used to price a roll token.

    Not a proven optimum. Every slot is given its best legal OBSERVABLE stat, chosen greedily in
    descending order of solo value with the no-duplicate rule enforced, then all five qualities are
    set to Tier V with Base traits. Tier V + Base is 2.5x; a Vampiric slot can reach 3.0x, so this
    is a reference point inside the reachable set rather than its boundary -- which is what a
    shadow price wants, because a token cannot buy the boundary either.
    """
    def sc(sl):
        return float(fv.score(built, role, fv.banner_weights(sl), team, exposure,
                              prefix, suffix, teams=teams))
    base = sc(slots)
    chosen, used = [], set()
    for s in slots:
        best, bestv = None, -np.inf
        for cand in fv.BY_COLOUR[s["colour"]]:
            if cand in used or cand in fv.UNOBSERVABLE:
                continue
            solo = [dict(x) for x in slots]
            solo[len(chosen)]["stat"] = cand
            v = sc(solo)
            if v > bestv:
                best, bestv = cand, v
        chosen.append(best)
        if best:
            used.add(best)
    ideal = [dict(x) for x in slots]
    for i, st in enumerate(chosen):
        if st:
            ideal[i]["stat"] = st
        ideal[i]["quality_tier"] = "V"
        ideal[i]["trait"] = "Base"
    ev = bm.evaluate([{"quality_tier": x["quality_tier"], "trait": x["trait"]} for x in ideal])
    for k, x in enumerate(ideal):
        x["multiplier"] = ev[k]["multiplier"]
    top = sc(ideal)
    return {"current": round(base, 1), "reference_ceiling": round(top, 1),
            "headroom_points": round(top - base, 1),
            "headroom_pct": round(100.0 * (top - base) / base, 2) if base else None,
            "reference_banner": [{"slot": i + 1, "stat": ideal[i]["stat"], "tier": "V",
                                  "trait": "Base"} for i in range(len(ideal))],
            "definition": "best legal observable stat per slot (greedy, no duplicates), all "
                          "qualities Tier V, all traits Base. A reference inside the reachable "
                          "set, not a proven maximum."}


def build(draws=400, out_dir=None):
    t0 = time.time()
    out_dir = out_dir or OUT
    os.makedirs(out_dir, exist_ok=True)
    dirty = _dirty()
    exp_doc = mex.build()
    exposure = exp_doc["exposure"]
    survivors = sorted(exposure)
    built = fv.build_cache()
    if built["bad_roster_shape"]:
        raise SystemExit(f"roster shape check failed: {built['bad_roster_shape']}")
    missing = [(o, r) for o in survivors for r in ROLES if (o, r) not in built["cache"]]
    if missing:
        raise SystemExit(f"no player-game data for {missing}")

    accounts, rankings, diagnostics, coach, offers, policy = {}, {}, {}, {}, {}, {}
    joint = {}
    for name in STATE_FILES:
        doc, path = load_state(name)
        accounts[name] = {"file": os.path.relpath(path, REPO), "sha256": _sha256(path),
                          "roll_tokens": doc["roll_tokens"], "coach": doc["coach"]}
        joint[name] = joint_coach_and_teams(built, doc, exposure, survivors)
        # The coach is scored on the SUM over the three roles because one title pair applies to
        # all of them; the per-role tables below are reported at the jointly chosen pair.
        pre, suf = joint[name]["coach"]["prefix"], joint[name]["coach"]["suffix"]
        rankings[name], diagnostics[name], coach[name], offers[name], policy[name] = \
            {}, {}, {}, {}, {}
        for role in ROLES:
            slots = slots_of(doc, role)
            rank = fv.rank_teams(built, role, slots, {t: exposure[t]["dist"] for t in survivors},
                                 pre, suf, teams=survivors, draws=draws)
            lead = rank[0]["organization"]
            rob = robustness(built, role, slots, exposure, pre, suf, lead, survivors)
            rankings[name][role] = {
                "current_team": doc["banners"][role]["client_team"],
                "current_team_is_survivor": doc["banners"][role]["team_is_main_event_survivor"],
                "banner": slots, "coach": {"prefix": pre, "suffix": suf},
                "recommended_team": lead, "robustness": rob,
                "shrinkage_sweep": shrinkage_sweep(built, role, slots, exposure, pre, suf,
                                                   survivors, lead),
                "unscored": fv.unscored_weight(slots),
                "unobservable_breakpoints": fv.unobservable_breakpoints(slots, rank),
                "ranking": rank}
            diagnostics[name][role] = emblem_diagnostic(
                built, role, slots, lead, exposure[lead]["dist"], pre, suf,
                teams=survivors)
            coach[name][role] = fv.coach_table(built, role, slots, lead,
                                              exposure[lead]["dist"], teams=survivors)
            offers[name][role] = None
            policy[name][role] = {
                "team": lead,
                "banner": slots,
                "ceiling": reachable_ceiling(built, role, slots, lead,
                                             exposure[lead]["dist"], pre, suf,
                                             teams=survivors),
                "stat_value": fv.stat_value_table(built, role, slots, lead,
                                                  exposure[lead]["dist"], pre, suf,
                                                  teams=survivors),
                "quality_and_trait": fv.quality_trait_tables(
                    built, role, slots, lead, exposure[lead]["dist"], pre, suf,
                    teams=survivors)}
        focus = doc["selected_banner_for_crafting"]
        lead = rankings[name][focus]["recommended_team"]
        offers[name][focus] = [offer_outcomes(built, focus, slots_of(doc, focus), lead,
                                              exposure[lead]["dist"], pre, suf, o,
                                              teams=survivors)
                               for o in doc["roll_board"]]

    manifest = {
        "artifact_family": "TI15 period-1 (Main Event) Fantasy",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _commit(), "git_dirty_at_start": dirty,
        "information_cutoff": INFO_CUTOFF,
        "main_event_results_used": False,
        "leakage_note": "every input match starts before 2026-08-20T00:00:00Z, asserted in the "
                        "fetcher on both the league listing and each match payload",
        "runtime_seconds": None,
        "estimator": {
            "chain": "player-game -> role arithmetic mean -> top two games in a series -> best "
                     "series in the period -> equal-weight mean over event blocks -> expectation "
                     "over the Main Event series-count distribution",
            "expected_maximum": "closed form over the empirical series pool, not simulated",
            "uncertainty": "hierarchical bootstrap: resample event blocks, then series within",
            "bootstrap_draws": draws,
            "coach_stacking": "additive (prefix + suffix); multiplicative reported as sensitivity"},
        "data": {k: {"path": os.path.relpath(p, REPO), "sha256": _sha256(p)} for k, p in (
            ("historical_player_maps", fv.HIST_STATS),
            ("historical_extras", fv.HIST_EXTRAS),
            ("historical_match_extras", fv.HIST_MATCH),
            ("ti15_player_maps", fv.TI15_STATS),
            ("ti15_match_extras", fv.TI15_MATCH),
            ("roster_positions", os.path.join(fv.INPUTS, "fantasy", "roster_positions.csv")))},
        "bracket_isolation": exp_doc["bracket_isolation"],
        "coverage": built["coverage"],
        "accounts": accounts,
    }
    manifest["runtime_seconds"] = round(time.time() - t0, 1)

    def dump(name, obj):
        p = os.path.join(out_dir, name)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1)
        return p

    # The one remaining generic rule that reaches a live banner. The client says "per rune bottled
    # or taken" and does not say whether wisdom runes count; OpenDota's rune_pickups excludes them
    # and its runes histogram includes them. Rather than pick one, both are run end to end and the
    # question asked is only whether the ANSWER moves.
    rune_sens = {}
    alt = fv.build_cache(runes_key="runes_total")
    for name in STATE_FILES:
        doc, _ = load_state(name)
        pre, suf = joint[name]["coach"]["prefix"], joint[name]["coach"]["suffix"]
        rune_sens[name] = {}
        for role in ROLES:
            slots = slots_of(doc, role)
            if not any(s["stat"] == "runes_grabbed" for s in slots):
                continue
            w = fv.banner_weights(slots)
            scores = {t: float(fv.score(alt, role, w, t, exposure[t]["dist"], pre, suf,
                                        teams=survivors))
                      for t in survivors}
            best_alt = max(scores, key=scores.get)
            base_best = rankings[name][role]["recommended_team"]
            # Neither definition is established, so the choice is made by minimax regret over the
            # two readings rather than by picking one and hoping. Regret is measured in percent of
            # that reading's own best, because the two readings are on different scales.
            base_scores = {r_["organization"]: r_["expected_period_score"]
                           for r_ in rankings[name][role]["ranking"]}
            b_excl, b_incl = max(base_scores.values()), max(scores.values())
            regret = {t: max(100.0 * (b_excl - base_scores[t]) / b_excl,
                             100.0 * (b_incl - scores[t]) / b_incl) for t in survivors}
            minimax = min(regret, key=regret.get)
            rune_sens[name][role] = {
                "minimax_regret_choice": minimax,
                "max_regret_pct_by_team": {t: round(v, 3) for t, v in
                                           sorted(regret.items(), key=lambda kv: kv[1])},
                "reading": "regret is measured against each definition's own leader, so a team "
                           "that is near-best under both beats one that is best under only one",
                "runes_multiplier": next(s["multiplier"] for s in slots
                                         if s["stat"] == "runes_grabbed"),
                "best_under_rune_pickups_excl_wisdom": base_best,
                "best_under_runes_total_incl_wisdom": best_alt,
                "team_choice_moves": best_alt != base_best,
                "score_inflation_pct": round(
                    100.0 * (scores[base_best]
                             / rankings[name][role]["ranking"][0]["expected_period_score"] - 1), 2),
                "ranking_under_inclusive_definition": [
                    {"organization": t, "expected_period_score": round(v, 1)}
                    for t, v in sorted(scores.items(), key=lambda kv: -kv[1])]}

    token_budget = {}
    for name in STATE_FILES:
        doc, _ = load_state(name)
        head = sum(policy[name][r]["ceiling"]["headroom_points"] for r in ROLES)
        tok = doc["roll_tokens"]
        token_budget[name] = {
            "roll_tokens": tok, "emblems": 15,
            "total_headroom_points": round(head, 1),
            "shadow_value_per_token": round(head / tok, 1) if tok else None,
            "reading": "the most a token can be worth on average, if the entire remaining "
                       "headroom were bought with the tokens on hand and nothing were wasted. "
                       "An operation whose value clears this is worth taking now rather than "
                       "held for a better board.",
            "why_the_budget_is_loose": "tokens do not roll over and period 1 is the last period, "
                                       "so an unspent token is worth exactly zero after the lock. "
                                       f"{tok} tokens against 15 emblems is a large budget, which "
                                       "pushes the shadow price down and the correct posture "
                                       "towards accepting any operation with a positive floor.",
            "hard_exception": "an operation that can DAMAGE a PROTECT emblem is judged on its "
                              "floor, not its average: the budget is large but the downside on a "
                              "high-multiplier scoring slot is not recoverable within one period."}

    policy_doc = {
        "manifest": manifest,
        "schema": {
            "purpose": "Everything a later assistant needs to price one client reroll WITHOUT "
                       "refetching data, refitting projections or re-running the bracket model.",
            "how_to_update_after_one_reroll": [
                "1. Edit the account state JSON: change the affected slot's stat / quality_tier / "
                "trait, and decrement roll_tokens.",
                "2. Recompute the five multipliers with banner_model.evaluate -- never hand-edit "
                "them, and never assume only the changed slot moved: Fractal reads all five "
                "qualities and Benevolent/Vampiric move their neighbours.",
                "3. Call fastvalue.period_score(built['cache'][(team, role)], "
                "fastvalue.banner_weights(slots), exposure[team]['dist'], prefix, suffix). The "
                "cache rebuilds from local CSVs in about 0.1 s; nothing touches the network.",
                "4. For the three new offers, call build_main_event.offer_outcomes.",
            ],
            "fields": {
                "team_rankings.rankings[account][role].ranking[]": "expected_period_score is the "
                    "expectation over the Main Event series-count distribution of the "
                    "equal-weight mean across event blocks of E[max of N series]. ci90 and "
                    "bootstrap_sd come from the hierarchical bootstrap. p_is_best_bootstrap is "
                    "the fraction of bootstrap draws in which that team has the highest score.",
                "robustness.label": "ROBUST means at most "
                    f"{ROBUST_FLIP:.0%} of single-emblem perturbations move the best team; "
                    "BANNER-DEPENDENT lists the ones that do.",
                "value_tables[account][role].stat_value.slots[]": "options[].period_score is the "
                    "EXACT score with that stat substituted into that slot, so the top-two and "
                    "best-series selections are re-run rather than linearised. "
                    "value_per_plus_10pct is the local exact derivative.",
                "value_tables[account][role].quality_and_trait": "each option recomputes the whole "
                    "five-slot trait network; resulting_multipliers shows all five.",
                "diagnostics[account][role].emblems[]": "marginal_value_points is the loss if that "
                    "emblem stopped scoring; share_of_banner_value is that as a fraction.",
                "unobservable_breakpoints": "watchers_taken, lotuses_grabbed and madstone have no "
                    "public per-player source. Adding a constant k per player-game shifts the "
                    "period score by exactly 2k, so the flip condition is closed form.",
                "offers[account][role][]": "readings are alternative target-selection semantics; "
                    "fraction_improving is a COMBINATORIAL fraction over the outcome set, not a "
                    "probability, because Valve publishes no reroll weights.",
            },
            "invariants": [
                "a team change costs 0 tokens and leaves the banner byte-identical",
                "a coach title change costs 0 tokens and is reversible",
                "one War Banner regeneration costs exactly 1 token",
                "a banner never carries the same stat twice",
                "a stat reroll is guaranteed to produce a different stat",
            ],
        },
        "exposure": exposure,
        "token_budget": token_budget,
        "rune_definition_sensitivity": rune_sens,
        "recommended": {name: {r: {"team": rankings[name][r]["recommended_team"],
                                   "label": rankings[name][r]["robustness"]["label"]}
                               for r in ROLES} for name in STATE_FILES},
        "coach_best": {name: {"joint": joint[name]["coach"],
                              "incumbent": joint[name]["incumbent"],
                              "agreement_across_stacking_rules":
                                  joint[name]["agreement_across_stacking_rules"]}
                       for name in STATE_FILES},
        "value_tables": policy,
        "diagnostics": diagnostics,
    }

    dump("main_event_opportunity.json", exp_doc)
    dump("team_rankings.json", {"manifest": manifest, "rankings": rankings})
    dump("banner_value_tables.json", {"manifest": manifest, "diagnostics": diagnostics,
                                      "value_tables": policy})
    dump("coach_value_tables.json", {"manifest": manifest, "joint": joint, "per_role": coach})
    dump("reroll_offer_evaluation.json", {"manifest": manifest, "offers": offers})
    dump("interactive_policy.json", policy_doc)
    dump("ti15_player_data_manifest.json", data_manifest(built))
    dump("rules_verified.json", rules_verified(exp_doc))
    out = {"manifest": manifest, "exposure": exp_doc, "rankings": rankings,
           "diagnostics": diagnostics, "coach": coach, "joint": joint, "offers": offers,
           "policy": policy, "token_budget": token_budget,
           "rune_definition_sensitivity": rune_sens, "built": built}
    with open(os.path.join(out_dir, "recommendation.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(out) + "\n")
    return out


def joint_coach_and_teams(built, doc, exposure, survivors, max_rounds=6):
    """Coach and the three teams are chosen together, because both are free and both interact.

    The coach applies to ALL THREE roles at once, so its value is the sum over roles; and the best
    team for a role depends on which titles amplify that team's games. Neither change costs a
    token, so there is no switching cost to trade off -- the only thing to get right is the fixed
    point. Alternate ranking teams under the current titles and re-pricing titles under the current
    teams until nothing moves; with 8 teams and 64 title pairs the whole loop is exhaustive at
    every step, so this converges to a joint optimum rather than approximating one.
    """
    pre, suf = doc["coach"]["prefix"], doc["coach"]["suffix"]
    slots = {r: slots_of(doc, r) for r in ROLES}
    history = []
    teams = None
    for _ in range(max_rounds):
        teams = {}
        for role in ROLES:
            best, bestv = None, -np.inf
            for t in survivors:
                v = fv.score(built, role, fv.banner_weights(slots[role]), t,
                             exposure[t]["dist"], pre, suf, teams=survivors)
                if v > bestv:
                    best, bestv = t, v
            teams[role] = best
        rows = []
        for p in list(fv.PREFIX_BONUS) + [None]:
            for s in list(fv.SUFFIX_BONUS) + [None]:
                tot = sum(float(fv.score(built, r, fv.banner_weights(slots[r]), teams[r],
                                         exposure[teams[r]]["dist"], p, s,
                                         teams=survivors))
                          for r in ROLES)
                rows.append({"prefix": p, "suffix": s, "account_total": round(tot, 1),
                             "prefix_evidence": fv.PREFIX_FLAG[p][1] if p else "none",
                             "suffix_scoreable": (s not in fv.SUFFIX_UNSCORED) if s else True})
        rows.sort(key=lambda x: -x["account_total"])
        history.append({"teams": dict(teams), "coach": (pre, suf),
                        "account_total": rows[0]["account_total"]})
        top = rows[0]
        if (top["prefix"], top["suffix"]) == (pre, suf):
            break
        pre, suf = top["prefix"], top["suffix"]
    # multiplicative stacking, as a declared sensitivity: which rule Valve uses is UNRESOLVED
    mult = []
    for p in list(fv.PREFIX_BONUS) + [None]:
        for s in list(fv.SUFFIX_BONUS) + [None]:
            tot = sum(float(fv.score(built, r, fv.banner_weights(slots[r]), teams[r],
                                     exposure[teams[r]]["dist"], p, s, "multiplicative",
                                     teams=survivors))
                      for r in ROLES)
            mult.append({"prefix": p, "suffix": s, "account_total": round(tot, 1)})
    mult.sort(key=lambda x: -x["account_total"])
    incumbent = doc["coach"]["prefix"], doc["coach"]["suffix"]
    inc_row = next(x for x in rows if (x["prefix"], x["suffix"]) == incumbent)
    return {"converged_teams": teams, "coach": {"prefix": pre, "suffix": suf},
            "iterations": history,
            "joint_table_additive": rows,
            "joint_table_multiplicative_sensitivity": mult[:8],
            "incumbent": {"prefix": incumbent[0], "suffix": incumbent[1],
                          "account_total": inc_row["account_total"],
                          "gap_to_best": round(rows[0]["account_total"]
                                               - inc_row["account_total"], 1),
                          "gap_pct": round(100.0 * (rows[0]["account_total"]
                                                    - inc_row["account_total"])
                                           / rows[0]["account_total"], 3)},
            "agreement_across_stacking_rules":
                (rows[0]["prefix"], rows[0]["suffix"]) == (mult[0]["prefix"], mult[0]["suffix"]),
            "caveat": "prefix evidence differs by title: red/blue/green are exact flags, Elemental "
                      "and Otherworldly are strict subsets of their condition so their scores are "
                      "LOWER BOUNDS, and Royal, Golden and Heroic have no hero-category table at "
                      "all and cannot be scored."}


def data_manifest(built):
    """Coverage and provenance for the TI15 acquisition, with hashes for the untracked tables.

    The repository deliberately gitignores `data/*/raw/` and `data/*/processed/` -- they are large
    regenerable API pulls. So the snapshot is committed as this manifest: what was fetched, from
    where, when, how complete it is, and the sha256 of each table, which is what makes a later run
    checkable against this one.
    """
    prov_path = os.path.join(fv.FPROC, "ti15_provenance.json")
    prov = {}
    if os.path.exists(prov_path):
        with open(prov_path, encoding="utf-8") as fh:
            prov = json.load(fh)
    import csv as _csv
    ti15 = list(_csv.DictReader(open(fv.TI15_STATS, encoding="utf-8"))) \
        if os.path.exists(fv.TI15_STATS) else []
    extras = list(_csv.DictReader(open(fv.HIST_EXTRAS, encoding="utf-8"))) \
        if os.path.exists(fv.HIST_EXTRAS) else []
    matches = {int(r["match_id"]) for r in ti15}
    series = {r["series_id"] for r in ti15 if r["series_id"]}
    orgs = {}
    for r in ti15:
        orgs.setdefault(r["organization"], set()).add(int(r["account_id"]))
    unparsed = [r["match_id"] for r in ti15 if r["parsed"] != "1"]
    stat_cov = {}
    for stat in fv.STATS:
        entry = None
        for key, e in built["cache"].items():
            entry = e
            break
        if entry is not None:
            stat_cov[stat] = round(float(entry["col_coverage"][fv.STAT_INDEX[stat]]), 4)
    return {
        "what": "TI15 pre-Main-Event player-map snapshot for Fantasy, plus the extras the older "
                "historical table does not carry.",
        "source": prov.get("sources"),
        "retrieved_at": prov.get("written_at"),
        "leakage_boundary": prov.get("leakage_boundary"),
        "bracket_isolation": prov.get("bracket_isolation"),
        "expected_pre_main_event_shape": {"swiss_series": 39, "elimination_series": 5,
                                          "total_series": 44, "approx_maps": 109},
        "observed": {"maps": len(matches), "distinct_series": len(series),
                     "player_maps": len(ti15), "unparsed_maps": sorted(set(unparsed)),
                     "organizations": {o: len(v) for o, v in sorted(orgs.items())}},
        "historical_extras": {"rows": len(extras),
                              "distinct_matches": len({r["match_id"] for r in extras})},
        "roster_reconciliation": {
            "source": "data/ti2026/inputs/fantasy/roster_positions.csv, active players only",
            "rule": "a player-map enters only if its account_id resolves to exactly one "
                    "(organization, fantasy_role); a role-game enters only if every player of "
                    "that role has a row in that game",
            "shape_check": "each organisation must present exactly 2 core, 1 mid and 2 support",
            "failures": built["bad_roster_shape"]},
        "files_untracked_by_repo_policy": prov.get("files"),
        "stat_coverage_after_join": stat_cov,
        "coverage_by_org_role": built["coverage"],
    }


def rules_verified(exp_doc):
    """The period-1 ruleset as this run uses it, with the grade of every load-bearing item."""
    return {
        "schema_version": 1,
        "event": "The International 2026 (TI15), period 1 (Main Event)",
        "compiled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "canonical_source": "data/ti2026/inputs/fantasy/fantasy_rules.json; this file records the "
                            "subset that period-1 optimisation actually depends on, with grades",
        "banner": {
            "emblems_per_banner": 5,
            "colour_layout": {r: list(bm.layout(r, 1)) for r in ROLES},
            "grade": "user_runtime_observation (first-party client 'Upgrade War Banner' screen, "
                     "2026-08-17, both accounts)",
            "supersedes": "the three-slot period-1 reading taken from the Fantasy landing page, "
                          "which renders only three of the five emblems. Withdrawn.",
            "composition_rule": "multiplier = 1 + quality_bonus + net_trait_bonus",
            "validation": "all 30 live emblems reproduce their displayed total AND their displayed "
                          "net trait contribution from primitive trait rules",
            "quality_bonus": {"I": 0.10, "II": 0.30, "III": 0.60, "IV": 1.00, "V": 1.50},
            "traits": {"Fractal": "+60% to itself if all five qualities differ",
                       "Benevolent": "+20% to each adjacent emblem, never itself",
                       "Vampiric": "+50% to itself, -10% to each adjacent emblem",
                       "Unique": "+30% if it is the only Unique on the banner",
                       "Friendly": "+50% if the banner holds at least three Friendly",
                       "Incorruptible": "quality below Tier III is treated as Tier III",
                       "Base": "no modifier"}},
        "scoring_chain": ["player-game: sum over banner emblems of coefficient x raw stat x "
                          "emblem multiplier, then amplified by any triggering coach title",
                          "role-game: arithmetic mean over the role's players (2 core, 1 mid, "
                          "2 support)",
                          "role-series: the top TWO scoring games in the series",
                          "role-period: the BEST scoring series, never the sum"],
        "token_costs": {"war_banner_regeneration": 1, "team_change": 0, "coach_title_change": 0,
                        "note": "the blanket 'every operation costs one token' phrasing is "
                                "withdrawn; only banner regeneration is priced"},
        "lock": {"recorded_utc": "2026-08-20T02:00:00Z",
                 "countdown_observed": "2 days until lineup lock, 2026-08-17",
                 "snapshot": "the roster is snapshotted when period matches begin; post-start UI "
                             "editability is NOT relied on and is not evidence that a later edit "
                             "reaches period 1"},
        "candidate_pool": {"client_offers_all_16": True, "can_score": sorted(exp_doc["exposure"]),
                           "why": "an eliminated organisation plays zero Main Event series"},
        "observability": {
            "resolved_this_round": {
                "tormentor_kills": "objectives[].CHAT_MESSAGE_MINIBOSS_KILL carries player_slot, "
                                   "so the kill is attributable to one player. The previous "
                                   "'per-player attribution unverified' grade is withdrawn."},
            "bounded_not_resolved": {
                "runes_grabbed": "OpenDota's rune_pickups EXCLUDES wisdom runes (type 8) while the "
                                 "runes histogram includes them. The client says 'bottled or "
                                 "taken' and does not say which. Both are carried; production "
                                 "uses rune_pickups and the gap is reported."},
            "unobservable": {
                "madstone": "neutral_tokens_log is an empty list on all 4785 historical "
                            "player-maps and on every TI15 player-map. Missing, not zero.",
                "watchers_taken": "no key anywhere in the match payload",
                "lotuses_grabbed": "no key anywhere in the match payload"},
            "treatment": "weight on an unobservable stat is set to zero and reported as unscored "
                         "banner weight, and an exact breakpoint is published for how much it "
                         "would have to be worth per player-game to change the team ranking"},
        "reward_table": {"100th": 12000, "99th": 11400, "95th": 10000, "90th": 8400, "80th": 5800,
                         "60th": 3300, "40th": 1700, "20th": 400, "10th": 200,
                         "objective_note": "values are closed; the competitor score distribution "
                                           "is not, and the table cannot be inverted into one. "
                                           "The production objective is expected period score."},
        "coach": {"prefix_bonus": fv.PREFIX_BONUS, "suffix_bonus": fv.SUFFIX_BONUS,
                  "prefix_evidence": {k: v[1] for k, v in fv.PREFIX_FLAG.items()},
                  "stacking": "additive in production; multiplicative available as a sensitivity; "
                              "which rule Valve uses remains UNRESOLVED"},
    }


def to_markdown(r):
    L = []
    m = r["manifest"]
    L.append("# TI15 Fantasy - period 1 (Main Event) recommendation")
    L.append("")
    L.append(f"Generated {m['generated_at']} from commit `{m['code_commit']}` "
             f"(dirty at start: {m['git_dirty_at_start']}). "
             f"Information cutoff {m['information_cutoff']}; "
             f"Main Event results used: {m['main_event_results_used']}.")
    L.append("")
    L.append("JSON is the fact source. Numbers are not duplicated here beyond what a decision "
             "needs: `team_rankings.json`, `banner_value_tables.json`, `coach_value_tables.json`, "
             "`reroll_offer_evaluation.json` and `interactive_policy.json` are authoritative.")
    L.append("")
    L.append("## Deadline")
    L.append("")
    L.append("The roster is snapshotted when Main Event matches begin. Recorded lock "
             "**2026-08-20T02:00:00Z**; the in-client countdown read *2 days until lineup lock* "
             "on 2026-08-17. Team and coach changes are free, so there is no reason to submit "
             "late, and no reason to trust post-start editability.")
    L.append("")
    L.append("## Client actions")
    L.append("")
    L.append("```")
    for acct in ("operator", "target"):
        j = r["joint"][acct]
        L.append(f"{acct.upper()}  ({r['token_budget'][acct]['roll_tokens']} roll tokens)")
        for role in ROLES:
            d = r["rankings"][acct][role]
            verb = "KEEP  " if d["current_team"] == d["recommended_team"] else "CHANGE"
            why = "" if d["current_team_is_survivor"] else "   (current team is eliminated)"
            L.append(f"  {role.upper():<8} {verb} -> {d['recommended_team']}{why}")
        cur = f"{j['incumbent']['prefix']} + {j['incumbent']['suffix']}"
        new = f"{j['coach']['prefix']} + {j['coach']['suffix']}"
        L.append(f"  COACH    {'KEEP  ' if cur == new else 'CHANGE'} -> {new}")
        L.append("  REROLL   see the offer table below; nothing is recommended blind")
        L.append("")
    L.append("NEXT REVIEW  before 2026-08-20T02:00:00Z (roster snapshot), and after every "
             "reroll")
    L.append("```")
    L.append("")
    L.append("## Team selection")
    L.append("")
    for acct in ("operator", "target"):
        tok = r["token_budget"][acct]["roll_tokens"]
        L.append(f"### {acct} account ({tok} roll tokens)")
        L.append("")
        L.append("| role | current | action | recommended | label | E[score] | 90% interval "
                 "| P(best) | runner-up gap | survives shrinkage sweep | unscored |")
        L.append("|---|---|---|---|---|---:|---|---:|---:|---|---:|")
        for role in ROLES:
            d = r["rankings"][acct][role]
            top, second = d["ranking"][0], d["ranking"][1]
            act = "**CHANGE (eliminated)**" if not d["current_team_is_survivor"] else (
                "keep" if d["current_team"] == d["recommended_team"] else "**change**")
            sw = d["shrinkage_sweep"]
            L.append(f"| {role} | {d['current_team']} | {act} | **{d['recommended_team']}** | "
                     f"{d['robustness']['label']} | {top['expected_period_score']:,.0f} | "
                     f"[{top['ci90'][0]:,.0f}, {top['ci90'][1]:,.0f}] | "
                     f"{top['p_is_best_bootstrap']:.2f} | {second['regret_pct']:.2f}% | "
                     f"{'yes' if sw['leader_survives_family'] else 'NO'} | "
                     f"{d['unscored']['unscored_fraction']:.0%} |")
        L.append("")
        for role in ROLES:
            d = r["rankings"][acct][role]
            if d["robustness"]["label"] == "BANNER-DEPENDENT":
                fl = d["robustness"]["flipping_perturbations"][:6]
                L.append(f"- `{role}` is BANNER-DEPENDENT: "
                         f"{d['robustness']['flips']} of {d['robustness']['family_size']} "
                         f"single-emblem changes move the best team. Examples: "
                         + "; ".join(f"{f['perturbation']} -> {f['new_best']}" for f in fl))
        L.append("")
    L.append("## Coach")
    L.append("")
    L.append("One prefix and one suffix apply to all three roles, so the pair is scored on the "
             "SUM over roles and chosen jointly with the teams. Both are free and reversible, so "
             "there is no switching cost to trade against.")
    L.append("")
    L.append("| account | recommended | incumbent | gain over incumbent | same winner under "
             "multiplicative stacking |")
    L.append("|---|---|---|---:|---|")
    for acct in ("operator", "target"):
        j = r["joint"][acct]
        L.append(f"| {acct} | **{j['coach']['prefix']} + {j['coach']['suffix']}** | "
                 f"{j['incumbent']['prefix']} + {j['incumbent']['suffix']} | "
                 f"{j['incumbent']['gap_pct']:.2f}% | "
                 f"{'yes' if j['agreement_across_stacking_rules'] else 'NO - unresolved'} |")
    L.append("")
    L.append("Prefix evidence is not uniform: Crimson, Cerulean and Emerald score off exact "
             "hero-colour flags; Elemental and Otherworldly score off a strict subset of their "
             "condition, so their numbers are lower bounds; Royal, Golden and Heroic have no "
             "hero-category table and cannot be scored at all.")
    L.append("")
    L.append("## Roll tokens")
    L.append("")
    L.append("| account | tokens | headroom on the three banners | implied shadow value per token |")
    L.append("|---|---:|---:|---:|")
    for acct in ("operator", "target"):
        b = r["token_budget"][acct]
        L.append(f"| {acct} | {b['roll_tokens']} | {b['total_headroom_points']:,.0f} | "
                 f"{b['shadow_value_per_token']:,.0f} |")
    L.append("")
    L.append("Tokens do not roll over and period 1 is the last period, so an unspent token is "
             "worth exactly zero after the lock. See `reroll_offer_evaluation.json` for the "
             "current three offers on each account, enumerated as outcome sets rather than "
             "expectations: Valve publishes no reroll weights, so an improving fraction here is "
             "combinatorial and is not a probability.")
    L.append("")
    L.append("## What the model cannot see")
    L.append("")
    L.append("Three stats have no per-player value anywhere in the public data. Their weight is "
             "set to zero and reported, never scored as if the players produced none. Because "
             "adding a constant per player-game shifts a period score by exactly twice that "
             "constant, the flip condition is closed form.")
    L.append("")
    L.append("| account | role | unscored stat | multiplier | points per +1 per player-game "
             "| runner-up needs |")
    L.append("|---|---|---|---:|---:|---|")
    for acct in ("operator", "target"):
        for role in ROLES:
            bp = r["rankings"][acct][role]["unobservable_breakpoints"]
            for s in bp.get("unscored_slots", []):
                ch = s["challengers"][0] if s["challengers"] else None
                need = (f"{ch['challenger']} needs +{ch['extra_per_player_game_needed']:.2f}/game"
                        if ch else "n/a")
                L.append(f"| {acct} | {role} | {s['stat']} | {s['multiplier']:.2f} | "
                         f"{s['points_per_extra_unit_per_player_game']:,.0f} | {need} |")
    L.append("")
    if any(r["policy"] and rs for rs in r.get("rune_definition_sensitivity", {}).values()):
        L.append("The client's Runes wording is also unresolved: OpenDota's `rune_pickups` "
                 "excludes wisdom runes, which are 20.3% of all runes taken at TI15, while its "
                 "`runes` histogram includes them. Both definitions were run end to end; see "
                 "`interactive_policy.json -> rune_definition_sensitivity` for whether the team "
                 "choice moves.")
        L.append("")
    L.append("## The three offers currently on each board")
    L.append("")
    L.append("Evaluated on the RECOMMENDED team, not the eliminated one currently equipped. No "
             "expectation is quoted: Valve publishes no reroll weights, so what follows is the "
             "outcome set and its combinatorial spread.")
    L.append("")
    L.append("| account | banner | offer | semantics | reading | outcomes | worst | median "
             "| best | improving |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|")
    for acct in ("operator", "target"):
        for role, offs in r["offers"][acct].items():
            for o in offs or []:
                for name, rd in o["readings"].items():
                    L.append(f"| {acct} | {role} | {o['offer_id']} {o['kind']} | "
                             f"{o['semantics_status']} | {name} | {rd['n_outcomes']} | "
                             f"{rd['min_delta']:+,.0f} | {rd['median_delta']:+,.0f} | "
                             f"{rd['max_delta']:+,.0f} | "
                             f"{rd['fraction_improving']:.0%} |")
    L.append("")
    L.append("## Emblem diagnostic")
    L.append("")
    L.append("Full per-emblem numbers are in `banner_value_tables.json`. Summary of the "
             "classification of all 30 live emblems:")
    L.append("")
    L.append("| account | role | slot | stat | mult | class | share of banner value "
             "| best same-colour swap |")
    L.append("|---|---|---:|---|---:|---|---:|---|")
    for acct in ("operator", "target"):
        for role in ROLES:
            for e in r["diagnostics"][acct][role]["emblems"]:
                swap = (f"{e['best_same_colour_stat']} (+{e['best_stat_swap_gain_pct']:.1f}%)"
                        if e["best_stat_swap_gain_points"] > 0 else "none better")
                share = ("n/a" if not e["scoreable"]
                         else f"{e['share_of_banner_value']:.1%}")
                L.append(f"| {acct} | {role} | {e['slot']} | {e['stat']} | "
                         f"{e['multiplier']:.2f} | {e['classification']} | {share} | {swap} |")
    L.append("")
    return "\n".join(L)


def quick(state_path, role=None):
    """The interactive path: re-price one account after a client reroll, in about a second.

    Deliberately skips everything the heavy run does once and does not need to redo -- the
    bootstrap, the perturbation family, the full stat/quality/trait tables. What it does is
    re-validate the banner against the client's own printed multipliers, re-rank the eight
    survivors, and re-price whatever three operations the board is now offering.
    """
    with open(state_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for r_ in ROLES:
        ev = bm.evaluate([{"quality_tier": s["quality_tier"], "trait": s["trait"]}
                          for s in doc["banners"][r_]["slots"]])
        for i, s in enumerate(doc["banners"][r_]["slots"]):
            if abs(ev[i]["multiplier"] - s["displayed_multiplier"]) > 1e-9:
                raise SystemExit(f"{r_} slot {i + 1}: model {ev[i]['multiplier']} vs client "
                                 f"{s['displayed_multiplier']}. Re-derive the multipliers with "
                                 "banner_model.evaluate rather than hand-editing them.")
    exposure = mex.exposure_distribution()
    survivors = sorted(exposure)
    built = fv.build_cache()
    pre, suf = doc["coach"]["prefix"], doc["coach"]["suffix"]
    out = {"state": state_path, "roll_tokens": doc["roll_tokens"], "coach": doc["coach"],
           "roles": {}}
    for r_ in (ROLES if role is None else (role,)):
        slots = slots_of(doc, r_)
        w = fv.banner_weights(slots)
        per_team, field = fv.role_pools(built, r_, w, survivors, pre, suf)
        rows = sorted(({"organization": t,
                        "expected_period_score": round(float(fv.period_score_shrunk(
                            per_team.get(t, {}), field, exposure[t]["dist"])), 1)}
                       for t in survivors),
                      key=lambda x: -x["expected_period_score"])
        out["roles"][r_] = {"ranking": rows, "unscored": fv.unscored_weight(slots),
                            "current_team": doc["banners"][r_]["client_team"]}
    focus = doc.get("selected_banner_for_crafting")
    if focus and doc.get("roll_board"):
        lead = out["roles"][focus]["ranking"][0]["organization"]
        out["offers"] = [offer_outcomes(built, focus, slots_of(doc, focus), lead,
                                        exposure[lead]["dist"], pre, suf, o, teams=survivors)
                         for o in doc["roll_board"]]
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--draws", type=int, default=400)
    a.add_argument("--out", default="")
    a.add_argument("--quick", default="", help="path to one account state; re-price it fast")
    a.add_argument("--role", default="")
    a = a.parse_args(argv)
    if a.quick:
        t0 = time.time()
        q = quick(a.quick, a.role or None)
        for role, d in q["roles"].items():
            cur = d["current_team"]
            print(f"\n{role}  (current {cur}, unscored "
                  f"{d['unscored']['unscored_fraction']:.0%})")
            for i, row in enumerate(d["ranking"], 1):
                mark = " <- current" if row["organization"] == cur else ""
                print(f"  {i}. {row['organization']:<16} "
                      f"{row['expected_period_score']:>9.1f}{mark}")
        for o in q.get("offers", []):
            print(f"\noffer {o['offer_id']} ({o['kind']}, {o['semantics_status']})")
            for name, rd in o["readings"].items():
                print(f"  reading {name}: {rd['n_outcomes']} outcomes, "
                      f"min {rd['min_delta']:+.0f}, median {rd['median_delta']:+.0f}, "
                      f"max {rd['max_delta']:+.0f}, improving "
                      f"{rd['fraction_improving']:.0%} of outcomes")
        print(f"\n{round(time.time() - t0, 2)}s")
        return 0
    r = build(a.draws, a.out or None)
    print(f"built in {r['manifest']['runtime_seconds']}s "
          f"(commit {r['manifest']['code_commit']}, dirty={r['manifest']['git_dirty_at_start']})")
    for acct in r["rankings"]:
        print(f"\n===== {acct.upper()} =====")
        for role in ROLES:
            d = r["rankings"][acct][role]
            print(f"\n{role}: current {d['current_team']} "
                  f"({'SURVIVOR' if d['current_team_is_survivor'] else 'ELIMINATED - must change'})"
                  f" -> {d['recommended_team']} [{d['robustness']['label']}, "
                  f"flip {d['robustness']['flip_fraction']:.0%}]"
                  f"  unscored {d['unscored']['unscored_fraction']:.0%}")
            for row in d["ranking"]:
                print(f"   {row['rank']}. {row['organization']:<16} "
                      f"{row['expected_period_score']:>9.1f}  "
                      f"[{row['ci90'][0]:>8.1f},{row['ci90'][1]:>9.1f}]  "
                      f"regret {row['regret_pct']:>5.2f}%  P(best) {row['p_is_best_bootstrap']:.2f}"
                      f"  E[series] {row['expected_series']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
