"""What death positions can and cannot say about the Cruel.

The Cruel fires when a player is killed inside their OWN fountain. An earlier round called this
UNAVAILABLE on the grounds that the source carries no death positions; that was wrong and is
withdrawn. OpenDota does expose deaths_pos, inside teamfights[].players[].

Two limits survive that correction, and only one of them is about coverage:

  coverage      deaths_pos only exists for deaths inside a detected teamfight, so a large minority
                of deaths have no position at all.
  attribution   within a teamfight, a player's deaths_pos is a HISTOGRAM over all of that player's
                deaths in that fight. A death cannot be tied to the killer that caused it. The
                calibration route -- locate the fountains from deaths credited to dota_fountain --
                therefore fails: those players' position histograms also contain their ordinary
                deaths, and the fountain death cannot be picked out of them.

So the fountain regions cannot be calibrated from the data, and typing coordinates in from memory
is not allowed. What CAN be said without any calibration is this: whatever the fountain regions
are, they sit in the two extreme corners of the map. A death that is not near a corner cannot be a
fountain death. Counting deaths near the corners therefore gives an UPPER bound on the Cruel's
trigger rate that assumes nothing about where the fountains are, beyond that they are cornered.
"""
import csv
import json
import os

from ti_predict.fantasy import fetch_player_stats as fp

POS_CSV = os.path.join(fp.FANTASY_PROC, "death_positions.csv")
CORNER_RADII = (5, 10, 15, 20, 30)


def load_positions(path=POS_CSV):
    with open(path or POS_CSV, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def coverage(rows):
    total = sum(int(r["deaths"]) for r in rows)
    covered = sum(int(r["teamfight_deaths"]) for r in rows)
    return {"matches": len({r["match_id"] for r in rows}),
            "player_rows": len(rows),
            "total_deaths": total,
            "deaths_with_a_position": covered,
            "position_coverage": round(covered / total, 4) if total else None,
            "rows_with_no_position": sum(1 for r in rows if r["positions"] == "[]"),
            "structure": "teamfights[].players[].deaths_pos, a per-fight histogram over that "
                         "player's deaths; not attributable to an individual death or killer"}


def extent(rows):
    xs, ys = [], []
    for r in rows:
        for x, y, _c in json.loads(r["positions"]):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys)}


def calibration_attempt(rows):
    """Try to locate a fountain from deaths credited to dota_fountain, and show why it fails."""
    victims = [r for r in rows if int(r["fountain_killer_deaths"]) > 0]
    isolable = [r for r in victims
                if int(r["fountain_killer_deaths"]) == int(r["teamfight_deaths"]) ==
                int(r["deaths"]) and r["positions"] != "[]"]
    spread = {}
    for side, label in ((1, "radiant_victim"), (0, "dire_victim")):
        pts = [(x, y) for r in victims if int(r["is_radiant"]) == side
               for x, y, _c in json.loads(r["positions"])]
        if pts:
            spread[label] = {"positioned_deaths": len(pts),
                             "x_range": [min(p[0] for p in pts), max(p[0] for p in pts)],
                             "y_range": [min(p[1] for p in pts), max(p[1] for p in pts)]}
    return {"players_with_a_fountain_death": len(victims),
            "of_those_with_positions": sum(1 for r in victims if r["positions"] != "[]"),
            "cleanly_isolable": len(isolable),
            "spread_of_their_death_histograms": spread,
            "verdict": "FAILED. A victim's histogram mixes the fountain death with every other "
                       "death they took in the same fight, so the fountain cannot be located "
                       "from it. The spreads above cover most of the map, which is what that "
                       "mixing looks like.",
            "what_would_fix_it": "a per-death record carrying both position and killer, which "
                                 "this endpoint does not provide"}


def corner_bound(rows, radii=CORNER_RADII):
    """Upper bound on the Cruel, assuming only that fountains sit in the map's extreme corners."""
    ext = extent(rows)
    if not ext:
        return None
    out = []
    by_match = {}
    for r in rows:
        pts = json.loads(r["positions"])
        if not pts:
            continue
        by_match.setdefault(r["match_id"], []).append(pts)
    for rad in radii:
        near = 0
        for _mid, players in by_match.items():
            hit = any(
                (x <= ext["x_min"] + rad and y <= ext["y_min"] + rad)
                or (x >= ext["x_max"] - rad and y >= ext["y_max"] - rad)
                for pts in players for x, y, _c in pts)
            near += 1 if hit else 0
        out.append({"corner_radius": rad,
                    "matches_with_a_corner_death": near,
                    "matches": len(by_match),
                    "upper_bound_match_rate": round(near / len(by_match), 4)})
    return {"map_extent_observed": ext,
            "assumption": "a fountain lies within `corner_radius` of an observed map extreme; "
                          "nothing else about its location is assumed",
            "why_it_is_an_upper_bound": "it counts deaths near EITHER corner and does not check "
                                        "whose fountain it is, so it necessarily over-counts",
            "further_over_counts": "it also ignores that only deaths inside a teamfight are "
                                   "visible, so the true rate could be higher than the covered "
                                   "subset shows; the bound is on the covered subset",
            "rows": out}


def build(path=None):
    rows = load_positions(path)
    return {"coverage": coverage(rows),
            "fountain_calibration": calibration_attempt(rows),
            "corner_upper_bound": corner_bound(rows),
            "classification": "PARTIAL / BOUNDED -- positions exist but cannot be attributed to a "
                              "killer, so the fountain region cannot be calibrated from data and "
                              "hard-coding it is not permitted",
            "withdrawn": "the earlier claim that the source has no death positions"}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
