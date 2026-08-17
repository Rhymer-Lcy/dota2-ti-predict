"""Period-1 (Main Event) Fantasy: five-slot banners, the scoring chain, and the fast value model.

The load-bearing test in this file is the first one. An earlier round of this project read the
Fantasy LANDING page, which renders three of the five emblems, and recorded a three-slot period-1
banner. Every number built on that was wrong by construction. `test_client_banner_totals_reproduce`
pins all thirty emblems the client itself printed, so the same mistake cannot come back silently.
"""
import json
import os

import pytest

from ti_predict.fantasy import banner_model as bm
from ti_predict.fantasy import build_main_event as bme

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_EVENT = os.path.join(REPO, "predictions", "ti2026", "fantasy", "main_event")

# Every emblem on both accounts' period-1 banners, exactly as the client printed it on 2026-08-17:
# (account, role, slot, colour, stat, tier, trait, displayed total, displayed NET trait bonus).
CLIENT_EMBLEMS = [
    ("operator", "core", 1, "red", "tower_kills", "III", "Benevolent", 1.60, 0.00),
    ("operator", "core", 2, "green", "teamfight_participation", "II", "Fractal", 1.50, 0.20),
    ("operator", "core", 3, "red", "deaths", "I", "Friendly", 1.10, 0.00),
    ("operator", "core", 4, "green", "roshan_kills", "II", "Fractal", 1.30, 0.00),
    ("operator", "core", 5, "red", "gpm", "III", "Friendly", 1.60, 0.00),
    ("operator", "mid", 1, "red", "madstone", "I", "Fractal", 1.10, 0.00),
    ("operator", "mid", 2, "blue", "runes_grabbed", "II", "Unique", 1.50, 0.20),
    ("operator", "mid", 3, "green", "tormentor_kills", "III", "Benevolent", 1.60, 0.00),
    ("operator", "mid", 4, "red", "deaths", "IV", "Friendly", 2.20, 0.20),
    ("operator", "mid", 5, "green", "first_blood", "II", "Unique", 1.30, 0.00),
    ("operator", "support", 1, "blue", "lotuses_grabbed", "III", "Fractal", 1.50, -0.10),
    ("operator", "support", 2, "green", "tormentor_kills", "V", "Vampiric", 3.00, 0.50),
    ("operator", "support", 3, "blue", "wards_placed", "II", "Friendly", 1.20, -0.10),
    ("operator", "support", 4, "green", "teamfight_participation", "II", "Friendly", 1.30, 0.00),
    ("operator", "support", 5, "blue", "smokes_used", "III", "Fractal", 1.60, 0.00),
    ("target", "core", 1, "red", "gpm", "II", "Benevolent", 1.50, 0.20),
    ("target", "core", 2, "green", "roshan_kills", "IV", "Benevolent", 2.10, 0.10),
    ("target", "core", 3, "red", "creep_score", "V", "Vampiric", 3.40, 0.90),
    ("target", "core", 4, "green", "tormentor_kills", "I", "Benevolent", 1.00, -0.10),
    ("target", "core", 5, "red", "madstone", "III", "Unique", 2.10, 0.50),
    ("target", "mid", 1, "red", "deaths", "II", "Vampiric", 1.80, 0.50),
    ("target", "mid", 2, "blue", "wards_placed", "III", "Fractal", 1.50, -0.10),
    ("target", "mid", 3, "green", "stuns", "I", "Fractal", 1.10, 0.00),
    ("target", "mid", 4, "red", "creep_score", "I", "Fractal", 1.10, 0.00),
    ("target", "mid", 5, "green", "first_blood", "II", "Unique", 1.60, 0.30),
    ("target", "support", 1, "blue", "runes_grabbed", "V", "Vampiric", 2.90, 0.40),
    ("target", "support", 2, "green", "first_blood", "I", "Vampiric", 1.50, 0.40),
    ("target", "support", 3, "blue", "watchers_taken", "II", "Fractal", 1.10, -0.20),
    ("target", "support", 4, "green", "teamfight_participation", "II", "Vampiric", 1.80, 0.50),
    ("target", "support", 5, "blue", "wards_placed", "III", "Unique", 1.80, 0.20),
]


def _by_banner():
    out = {}
    for row in CLIENT_EMBLEMS:
        out.setdefault((row[0], row[1]), []).append(row)
    return {k: sorted(v, key=lambda r: r[2]) for k, v in out.items()}


# ---------------------------------------------------------------- five-slot banner

def test_period_1_has_five_slots_in_the_verified_colour_order():
    assert bm.LAYOUTS[1] == {"core": ("red", "green", "red", "green", "red"),
                             "mid": ("red", "blue", "green", "red", "green"),
                             "support": ("blue", "green", "blue", "green", "blue")}
    for role in ("core", "mid", "support"):
        assert bm.slot_count(role, 1) == 5
        assert bm.slot_count(role, 0) == 3, "period 0 stays three; the periods are not the same"


def test_client_banner_totals_reproduce():
    """All thirty live emblems, total AND net trait bonus, from primitive trait rules only."""
    for (acct, role), rows in _by_banner().items():
        assert tuple(r[3] for r in rows) == bm.layout(role, 1), f"{acct}/{role} colour order"
        got = bm.evaluate([{"quality_tier": r[5], "trait": r[6]} for r in rows])
        for i, r in enumerate(rows):
            assert got[i]["multiplier"] == pytest.approx(r[7], abs=1e-9), \
                f"{acct}/{role} slot {r[2]} ({r[4]}) total"
            assert got[i]["net_trait_bonus"] == pytest.approx(r[8], abs=1e-9), \
                f"{acct}/{role} slot {r[2]} ({r[4]}) net trait"


def test_fractal_uses_all_five_qualities():
    five_different = ["II", "IV", "V", "I", "III"]
    traits = ["Fractal"] + ["Base"] * 4
    q = [bm.tier_to_index(t) for t in five_different]
    assert bm.trait_bonus(q, traits)[0] == pytest.approx(0.60)
    # one duplicate anywhere in the five, and Fractal stops paying
    dup = ["II", "IV", "V", "I", "II"]
    q = [bm.tier_to_index(t) for t in dup]
    assert bm.trait_bonus(q, traits)[0] == pytest.approx(0.0)


def test_friendly_counts_all_five_traits():
    q = [0, 1, 2, 3, 4]
    assert bm.trait_bonus(q, ["Friendly", "Friendly", "Base", "Base", "Base"])[0] == \
        pytest.approx(0.0), "two Friendly is not enough"
    got = bm.trait_bonus(q, ["Friendly", "Friendly", "Friendly", "Base", "Base"])
    assert got[0] == pytest.approx(0.50) and got[2] == pytest.approx(0.50)


def test_adjacency_at_endpoints_and_interior():
    q = [0, 1, 2, 3, 4]
    b = bm.trait_bonus(q, ["Benevolent", "Base", "Base", "Base", "Base"])
    assert b[1] == pytest.approx(0.20) and b[0] == pytest.approx(0.0)
    assert b[2] == pytest.approx(0.0), "Benevolent reaches one neighbour, not two"
    b = bm.trait_bonus(q, ["Base", "Base", "Benevolent", "Base", "Base"])
    assert b[1] == pytest.approx(0.20) and b[3] == pytest.approx(0.20)
    b = bm.trait_bonus(q, ["Base", "Base", "Base", "Base", "Benevolent"])
    assert b[3] == pytest.approx(0.20)
    v = bm.trait_bonus(q, ["Base", "Vampiric", "Base", "Base", "Base"])
    assert v[1] == pytest.approx(0.50)
    assert v[0] == pytest.approx(-0.10) and v[2] == pytest.approx(-0.10)


def test_unique_is_banner_wide_over_five_slots():
    q = [0, 1, 2, 3, 4]
    assert bm.trait_bonus(q, ["Unique", "Base", "Base", "Base", "Base"])[0] == pytest.approx(0.30)
    assert bm.trait_bonus(q, ["Unique", "Base", "Base", "Base", "Unique"])[0] == pytest.approx(0.0)


# ---------------------------------------------------------------- account states

@pytest.mark.parametrize("name,tokens", [("operator", 40), ("target", 36)])
def test_account_state_loads_and_matches_the_client(name, tokens):
    doc, _ = bme.load_state(name)
    assert doc["period"] == 1
    assert doc["roll_tokens"] == tokens
    for role in ("core", "mid", "support"):
        slots = doc["banners"][role]["slots"]
        assert len(slots) == 5, f"{name}/{role} must carry exactly five emblems"
        assert tuple(s["colour"] for s in slots) == bm.layout(role, 1)
        assert all(s["reproduces_client"] for s in slots)
    assert doc["token_costs"]["war_banner_regeneration"] == 1
    assert doc["token_costs"]["team_change_via_banner_button"] == 0
    assert doc["token_costs"]["coach_title_change"] == 0


def test_eliminated_team_is_flagged_not_silently_scored():
    for name in ("operator", "target"):
        doc, _ = bme.load_state(name)
        for role in ("core", "support"):
            b = doc["banners"][role]
            assert b["client_team"] == "Xtreme Gaming"
            assert b["team_is_main_event_survivor"] is False
        assert doc["banners"]["mid"]["team_is_main_event_survivor"] is True


def test_a_three_slot_state_cannot_load_as_period_1(tmp_path):
    doc, _ = bme.load_state("operator")
    doc["banners"]["core"]["slots"] = doc["banners"]["core"]["slots"][:3]
    p = tmp_path / "stale.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    orig = bme.STATE_FILES["operator"]
    bme.STATE_FILES["operator"] = os.path.relpath(str(p), bme.OUT)
    try:
        with pytest.raises(SystemExit, match="colour layout"):
            bme.load_state("operator")
    finally:
        bme.STATE_FILES["operator"] = orig
