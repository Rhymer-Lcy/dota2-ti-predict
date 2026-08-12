"""The target account's observed Fantasy state, and what to do with it.

From here on nothing is a prior. The banner exists, it was read off the client, and every emblem's
displayed multiplier is reproducible from banner_model. That reproduction is the validation gate:
if the model cannot reproduce the client's own numbers, the model is wrong and no optimisation built
on it means anything.

The state file is the machine truth. This module loads it, re-derives the nine multipliers, and
prices the operations the client is currently offering.
"""
import argparse
import json
import os

from ti_predict.fantasy import banner_model as bm

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(REPO, "predictions", "ti2026", "fantasy",
                     "account_state_target_20260811.json")
TIER_INDEX = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4}
ROLES = ("core", "mid", "support")


def load_state(path=None):
    """Read the observed account state and check it against the client's own printed numbers.

    Fails closed on any emblem whose displayed multiplier this project cannot reproduce. That is the
    whole point of recording the displayed value: it is a free, exact worked example of Valve's
    composition rule, and it already caught one wrong rule.
    """
    path = path or STATE
    if not os.path.exists(path):
        raise SystemExit(f"account state not found: {path}")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for role in ROLES:
        b = doc["banners"][role]
        q = tuple(TIER_INDEX[s["quality_tier"]] for s in b["slots"])
        t = tuple(s["trait"] for s in b["slots"])
        got = bm.slot_weights(q, t)
        for i, s in enumerate(b["slots"]):
            if abs(got[i] - s["displayed_multiplier"]) > 1e-9:
                raise SystemExit(
                    f"{role} slot {i + 1} ({s['stat']}): the model computes "
                    f"{got[i]:.4f} but the client displays {s['displayed_multiplier']:.4f}. "
                    "Fix the model before optimising anything on top of it.")
    return doc


def banner_weights(doc, role):
    b = doc["banners"][role]
    q = tuple(TIER_INDEX[s["quality_tier"]] for s in b["slots"])
    t = tuple(s["trait"] for s in b["slots"])
    return bm.slot_weights(q, t)


def banner_score(doc, role, stat_values):
    """Banner score for one set of per-stat values, using the OBSERVED weights."""
    b = doc["banners"][role]
    w = banner_weights(doc, role)
    total, missing = 0.0, []
    for i, s in enumerate(b["slots"]):
        v = stat_values.get(s["stat"])
        if v is None:
            missing.append(s["stat"])
            continue
        total += w[i] * v
    return total, missing


def _apply(doc, role, slot_index, quality=None, trait=None):
    b = json.loads(json.dumps(doc["banners"][role]))
    if quality is not None:
        b["slots"][slot_index]["quality_tier"] = quality
    if trait is not None:
        b["slots"][slot_index]["trait"] = trait
    q = tuple(TIER_INDEX[s["quality_tier"]] for s in b["slots"])
    t = tuple(s["trait"] for s in b["slots"])
    return bm.slot_weights(q, t)


def operation_outcomes(doc, role, kind, colour, stat_values, quality_prior=None):
    """Every outcome of one roll-board operation, with its score change.

    kind is "trait" or "quality". A trait reroll is guaranteed to produce a DIFFERENT trait
    (DOTA_FantasyCraftHelp_GemShapeDetails), which is what makes some of these strictly positive.
    A quality reroll carries no such guarantee, so returning the same tier is a live outcome.
    """
    b = doc["banners"][role]
    targets = [i for i, s in enumerate(b["slots"]) if s["colour"] == colour]
    if len(targets) != 1:
        return {"ambiguous_target": True, "candidate_slots": [i + 1 for i in targets],
                "reason": "the client does not state which emblem of a colour an operation hits, "
                          "and this banner has more than one of that colour"}
    i = targets[0]
    base_w = banner_weights(doc, role)
    stats = [s["stat"] for s in b["slots"]]
    base = sum(base_w[k] * stat_values[stats[k]] for k in range(3))
    rows = []
    if kind == "trait":
        cur = b["slots"][i]["trait"]
        options = [t for t in bm.TRAITS if t != cur]
        p = [1.0 / len(options)] * len(options)
        for t, pi in zip(options, p):
            w = _apply(doc, role, i, trait=t)
            rows.append({"outcome": t, "p": round(pi, 4),
                         "delta": round(sum(w[k] * stat_values[stats[k]]
                                            for k in range(3)) - base, 1)})
    else:
        tiers = list(TIER_INDEX)
        p = quality_prior or [0.2] * 5
        for t, pi in zip(tiers, p):
            w = _apply(doc, role, i, quality=t)
            rows.append({"outcome": f"Tier {t}", "p": round(pi, 4),
                         "delta": round(sum(w[k] * stat_values[stats[k]]
                                            for k in range(3)) - base, 1)})
    ev = sum(r["p"] * r["delta"] for r in rows)
    return {"target_slot": i + 1, "target_stat": b["slots"][i]["stat"], "base_score": round(base, 1),
            "outcomes": sorted(rows, key=lambda r: r["delta"]),
            "expected_delta": round(ev, 1),
            "floor": round(min(r["delta"] for r in rows), 1),
            "downside_probability": round(sum(r["p"] for r in rows if r["delta"] < 0), 4)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--state", default=STATE)
    a = a.parse_args(argv)
    doc = load_state(a.state)
    print(f"account state {os.path.basename(a.state)}: validated against the client")
    for role in ROLES:
        b = doc["banners"][role]
        w = banner_weights(doc, role)
        print(f"\n{role} ({b['client_team']})")
        for i, s in enumerate(b["slots"]):
            print(f"  slot {i + 1} {s['colour']:<6} {s['stat']:<22} Tier {s['quality_tier']:<3} "
                  f"{s['trait']:<14} {w[i]:.2f} (client {s['displayed_multiplier']:.2f})")
    print(f"\nroll tokens: {doc['roll_tokens']}   board: "
          + "; ".join(o["label_en"] for o in doc["roll_board"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
