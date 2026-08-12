"""The exact period-0 War Banner: three emblems, real traits, real quality tiers.

An earlier version of this project collapsed a banner into three independent scalar multipliers
drawn from Uniform(0.9, 2.1). That was a stand-in, and it is withdrawn: it cannot represent
adjacency (Benevolent and Vampiric act on neighbours), it cannot represent banner-level conditions
(Unique, Friendly, Fractal look at the whole banner), and it silently smeared the discrete quality
ladder into a continuum. All three of those change the RELATIVE weight of one stat against another,
which is exactly the thing that decides which team belongs on a banner.

What is exact here: the quality ladder, every trait's effect, slot order and adjacency.
What is not known: the draw weights (which stat, which quality, which trait, how often), and the
order in which the multipliers compose. The first is handled by evaluating under several declared
prior families plus a distribution-free worst case; the second is stated below and carried as an
open question rather than hidden.
"""
import itertools

# Tier I..V, from DOTA_FantasyCraft_Quality_Explainer0..4 (Tier-1 client strings).
QUALITY = (0.10, 0.30, 0.60, 1.00, 1.50)
MIN_QUALITY_FLOOR = 0.60          # Incorruptible: below Tier III is treated as Tier III

TRAITS = ("Base", "Incorruptible", "Benevolent", "Vampiric", "Unique", "Friendly", "Fractal")

# Composition rule. The client does not state whether trait bonuses multiply or add before the
# quality multiplier is applied, so the additive-within-slot reading is used and recorded as an
# open question (fantasy_rules.unknowns.trait_composition). Adjacency effects are applied to the
# NEIGHBOUR's bonus pool, which is what the wording describes.
SELF_BONUS = {"Vampiric": 0.50, "Unique": 0.30, "Friendly": 0.50, "Fractal": 0.60}
ADJACENT_BONUS = {"Benevolent": 0.20, "Vampiric": -0.10}


def trait_bonus(qualities, traits):
    """Net trait bonus each slot receives, as a fraction. Validated against the live client.

    A slot's own trait pays it only when that trait's condition holds; neighbours pay it through
    Benevolent (+20 percent) and Vampiric (-10 percent). Benevolent pays its neighbours and never
    itself, which is what makes the observed Core banner add up.
    """
    n = len(qualities)
    n_unique = sum(1 for t in traits if t == "Unique")
    n_friendly = sum(1 for t in traits if t == "Friendly")
    all_qualities_differ = len(set(qualities)) == n
    out = []
    for i in range(n):
        bonus, t = 0.0, traits[i]
        if t == "Vampiric":
            bonus += SELF_BONUS["Vampiric"]
        elif t == "Unique" and n_unique == 1:
            bonus += SELF_BONUS["Unique"]
        elif t == "Friendly" and n_friendly >= 3:
            bonus += SELF_BONUS["Friendly"]
        elif t == "Fractal" and all_qualities_differ:
            bonus += SELF_BONUS["Fractal"]
        for j in (i - 1, i + 1):
            if 0 <= j < n:
                bonus += ADJACENT_BONUS.get(traits[j], 0.0)
        out.append(bonus)
    return out


def slot_weights(qualities, traits):
    """Per-slot multiplier for a three-emblem banner, applying every trait exactly.

    COMPOSITION, corrected against the live client. The client prints, per emblem, a total percentage
    together with its two components: a quality line ("Tier III +60%") and a trait line
    ("Benevolent +20%"). The total is their SUM on a 100 percent base:

        multiplier = 1 + quality_bonus + net_trait_bonus

    An earlier version of this file treated quality as a MULTIPLIER and traits as a factor on top of
    it, so a Tier I emblem scored 0.10 of its stat rather than 1.10. That is withdrawn. It mattered:
    the true multiplier range is roughly 1.1 to 2.6, not 0.09 to 3.15, so a banner reweights the
    stats far less violently than the old model implied.

    qualities: three indices into QUALITY. traits: three names from TRAITS, in slot order.
    """
    bonuses = trait_bonus(qualities, traits)
    out = []
    for i, qi in enumerate(qualities):
        q = QUALITY[qi]
        if traits[i] == "Incorruptible":
            q = max(q, MIN_QUALITY_FLOOR)
        out.append(1.0 + q + bonuses[i])
    return out


# Declared prior families. None of these is the truth; the draw weights are not published. They are
# run together so a recommendation can be shown to survive the whole family, and a distribution-free
# worst case is computed alongside.
PRIOR_FAMILIES = {
    "uniform": {"quality": (0.2, 0.2, 0.2, 0.2, 0.2),
                "trait": tuple([1.0 / len(TRAITS)] * len(TRAITS))},
    "quality_low_heavy": {"quality": (0.40, 0.30, 0.18, 0.09, 0.03),
                          "trait": tuple([1.0 / len(TRAITS)] * len(TRAITS))},
    "quality_high_heavy": {"quality": (0.03, 0.09, 0.18, 0.30, 0.40),
                           "trait": tuple([1.0 / len(TRAITS)] * len(TRAITS))},
    "trait_base_heavy": {"quality": (0.2, 0.2, 0.2, 0.2, 0.2),
                         "trait": (0.52, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08)},
    "trait_active_heavy": {"quality": (0.2, 0.2, 0.2, 0.2, 0.2),
                           "trait": (0.04, 0.16, 0.16, 0.16, 0.16, 0.16, 0.16)},
}


def sample_banner_state(rng, family="uniform"):
    """(quality indices, trait names) for three slots, under a declared prior family."""
    fam = PRIOR_FAMILIES[family]
    q = rng.choice(len(QUALITY), size=3, p=fam["quality"])
    t = rng.choice(len(TRAITS), size=3, p=fam["trait"])
    return tuple(int(x) for x in q), tuple(TRAITS[int(i)] for i in t)


def reachable_weight_extremes(max_states=None):
    """Every reachable (quality, trait) banner state, for the distribution-free worst case.

    5^3 quality assignments times 7^3 trait assignments is 42875 states, which is small enough to
    enumerate exactly. No prior is involved: this is the set of things the client can actually
    produce, which is what a minimax statement has to range over.
    """
    states = []
    for q in itertools.product(range(len(QUALITY)), repeat=3):
        for t in itertools.product(TRAITS, repeat=3):
            states.append((q, t))
            if max_states and len(states) >= max_states:
                return states
    return states
