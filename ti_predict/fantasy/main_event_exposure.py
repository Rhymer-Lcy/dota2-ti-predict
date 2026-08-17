"""How many Main Event series each team plays, exactly, from the committed bracket distribution.

Period 1 is an 8-team double elimination, not the Swiss. `exposure.py` encodes the Swiss record ->
series map (4/5/6 series) and reads the frozen GROUP-STAGE bucket probabilities; applying it to the
Main Event would be wrong twice over. The Main Event range is 2 to 6 series and it is far more
dispersed:

    lose UBQF, lose LBR1                       -> 2 series
    win UBQF, lose UBSF, lose LBR2             -> 3
    win out from UBQF (UBQF, UBSF, UBF, GF)    -> 4
    lose UBSF then run the whole lower bracket -> 6

That dispersion is the point. A period score keeps only the BEST series, so exposure enters as the
NUMBER OF EXTREME-VALUE DRAWS. Going from 2 draws to 6 is worth far more than the Swiss 4-to-6 this
project measured for period 0, and unlike the Swiss it is strongly correlated with team strength.

BRACKET ISOLATION. Nothing here refits, re-tunes or modifies the bracket model. Exactly two
committed numbers are read out of the audited artifact -- each team's `serve` strength and the
serve state's `radiant_c` -- and the topology comes from the same saved league feed the bracket
pipeline reads. The enumeration is the bracket module's own code, called unchanged.
`consistency_gate` re-derives the committed champion / reach-grand-final / win-UBQF marginals and
reports the deviation, so a silent divergence from the audited artifact cannot pass unnoticed.

One modelling difference is declared rather than hidden: production integrated the outcome
distribution over 1000 series-blocked bootstrap draws before optimising, and published only point
estimates. This module reconstructs the POINT-ESTIMATE outcome distribution, so the gate is
expected to show a small deviation, not zero.
"""
import argparse
import json
import os

import numpy as np

from ti_predict import bracket
from ti_predict import ti15_results as tr

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMITTED = os.path.join(REPO, "predictions", "ti2026", "playoffs",
                         "ti15_main_event_prediction.json")

MIN_SERIES, MAX_SERIES = 2, 6
# The gate compares reconstructed marginals against the committed ones. The committed numbers are
# bootstrap-averaged and these are point estimates, so a nonzero gap is expected; this is the
# threshold above which the difference stops being attributable to that and needs explaining.
GATE_TOLERANCE = 0.06


def committed(path=None):
    with open(path or COMMITTED, encoding="utf-8") as fh:
        return json.load(fh)


def serve_parameters(art=None):
    """Per-team serve strength and the serve radiant coefficient, exactly as committed."""
    art = art or committed()
    strength = {t: float(v["serve"]) for t, v in art["strength_evolution"].items()}
    c = float(art["states"]["C_serve"]["radiant_c"])
    return strength, c


def enumerate_once(art=None):
    """The 2^14 coherent outcomes with their point-estimate probabilities and participant table."""
    art = art or committed()
    strength, c = serve_parameters(art)
    topo = bracket.load_topology()
    # tr.UBQF carries the client-facing display names the seating evidence was transcribed in;
    # the committed strength table is keyed by canonical organisation. Resolve through the
    # project's own alias table, never by name similarity.
    seats = {nid: tuple(tr.canon(n) for n in pair) for nid, pair in tr.UBQF.items()}
    teams, W, PR = bracket.enumerate_structure(topo, seats)
    if sorted(teams) != sorted(strength):
        raise SystemExit(f"seated teams {sorted(teams)} do not match the committed strength table "
                         f"{sorted(strength)}")
    P = bracket.outcome_probs(topo, W, PR, teams, strength, c)
    return {"topo": topo, "teams": teams, "W": W, "PR": PR, "P": P,
            "strength": strength, "c": c}


def series_counts(en):
    """(n_outcomes, n_teams) int array: how many nodes each team appears in, per outcome.

    Every bracket node is exactly one series, so a team's series count in an outcome is the number
    of nodes at which it is a participant. Read straight off the participant table the bracket
    module already builds.
    """
    PR = en["PR"]
    n_out, n_nodes, _ = PR.shape
    out = np.zeros((n_out, len(en["teams"])), dtype=np.int8)
    for i in range(len(en["teams"])):
        out[:, i] = ((PR[:, :, 0] == i) | (PR[:, :, 1] == i)).sum(axis=1)
    return out


def exposure_distribution(en=None):
    """team -> {'dist': {series count: probability}, 'expected_series': float}."""
    en = en or enumerate_once()
    C, P = series_counts(en), en["P"]
    out = {}
    for i, team in enumerate(en["teams"]):
        col = C[:, i]
        exact = {n: float(P[col == n].sum()) for n in range(MIN_SERIES, MAX_SERIES + 1)}
        exact = {n: p for n, p in exact.items() if p > 0}
        total = sum(exact.values())
        if abs(total - 1.0) > 1e-9:
            raise SystemExit(f"{team}: series-count distribution sums to {total}")
        out[team] = {"dist": {n: round(p, 6) for n, p in exact.items()},
                     "expected_series": round(sum(k * v for k, v in exact.items()), 4),
                     "min_series": min(exact), "max_series": max(exact)}
    return out


def consistency_gate(en=None, art=None):
    """Re-derive the committed marginals from the reconstruction and report the deviation."""
    en = en or enumerate_once()
    art = art or committed()
    topo, teams, W, PR, P = en["topo"], en["teams"], en["W"], en["PR"], en["P"]
    order = topo["order"]
    col_of = {nid: i for i, nid in enumerate(order)}
    # Grand Final is the last node in the topology's own ordering of the final; find it by type.
    gf = [n for n in order if topo["best_of"][n] == 5]
    if len(gf) != 1:
        raise SystemExit(f"expected exactly one Bo5 node (the Grand Final), found {gf}")
    gf = gf[0]
    ubqf = [n for n in order if not topo["inputs"][n]]
    if len(ubqf) != 4:
        raise SystemExit(f"expected 4 seeded UBQF nodes, found {len(ubqf)}")
    rows = {}
    for i, team in enumerate(teams):
        gcol = col_of[gf]
        in_gf = (PR[:, gcol, 0] == i) | (PR[:, gcol, 1] == i)
        champ = in_gf & (W[:, gcol] == i)
        won_ubqf = np.zeros(len(P), dtype=bool)
        for nid in ubqf:
            k = col_of[nid]
            played = (PR[:, k, 0] == i) | (PR[:, k, 1] == i)
            won_ubqf |= played & (W[:, k] == i)
        rows[team] = {"champion": float(P[champ].sum()),
                      "reach_grand_final": float(P[in_gf].sum()),
                      "win_ubqf": float(P[won_ubqf].sum())}
    tp = art["tournament_probabilities"]
    dev = {}
    worst = 0.0
    for team, got in rows.items():
        d = {k: round(got[k] - tp[team][k], 5) for k in got}
        dev[team] = {"reconstructed": {k: round(v, 5) for k, v in got.items()},
                     "committed": {k: tp[team][k] for k in got}, "deviation": d}
        worst = max(worst, max(abs(v) for v in d.values()))
    return {"max_abs_deviation": round(worst, 5), "tolerance": GATE_TOLERANCE,
            "within_tolerance": worst <= GATE_TOLERANCE,
            "why_nonzero": "the committed marginals are averaged over 1000 series-blocked "
                           "bootstrap draws of the strengths; this reconstruction uses the "
                           "committed POINT-ESTIMATE serve strengths, which is the only strength "
                           "vector the artifact publishes",
            "per_team": dev}


def expected_max_gain(counts=(2, 3, 4, 5, 6)):
    """Reference table: E[max of n iid draws] relative to n=2, for a few shapes.

    Diagnostic only -- the real numbers come from each team's own empirical series pool. This exists
    so the size of the exposure effect can be sanity-checked without a projection.
    """
    rng = np.random.default_rng(20260817)
    out = {}
    for name, sample in (("lognormal_sd0.30", rng.lognormal(0, 0.30, 40000)),
                         ("lognormal_sd0.50", rng.lognormal(0, 0.50, 40000))):
        base = None
        row = {}
        for n in counts:
            draws = rng.choice(sample, size=(20000, n)).max(axis=1).mean()
            base = base if base is not None else draws
            row[n] = round(draws / base, 4)
        out[name] = row
    return out


def build(out_path=None):
    en = enumerate_once()
    art = committed()
    doc = {
        "schema_version": 1,
        "what": "Main Event (period 1) series-count distribution per team, exact over the 2^14 "
                "coherent bracket outcomes.",
        "bracket_isolation": {
            "committed_artifact": os.path.relpath(COMMITTED, REPO),
            "artifact_generated_at": art["manifest"]["generated_at"],
            "artifact_code_commit": art["manifest"]["code_commit"],
            "consumed_read_only": ["strength_evolution[*].serve", "states.C_serve.radiant_c",
                                   "the saved league feed topology via ti_predict.bracket"],
            "refit": False, "modified": False,
            "universe_maps_csv_touched": False},
        "seating": {str(k): [tr.canon(n) for n in v] for k, v in sorted(tr.UBQF.items())},
        "n_outcomes": int(len(en["P"])),
        "consistency_gate": consistency_gate(en, art),
        "exposure": exposure_distribution(en),
        "reference_option_value": {
            "note": "E[max of n draws] / E[max of 2 draws] for two illustrative right-skewed "
                    "shapes. Not used in production; production uses each team's own empirical "
                    "series pool.",
            "table": expected_max_gain()},
    }
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
    return doc


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--out", default="")
    a = a.parse_args(argv)
    d = build(a.out or None)
    g = d["consistency_gate"]
    print(f"{d['n_outcomes']} coherent outcomes; consistency gate max |dev| "
          f"{g['max_abs_deviation']:.4f} (tolerance {g['tolerance']}) -> "
          f"{'PASS' if g['within_tolerance'] else 'FAIL'}")
    print("\nMain Event series exposure (best-series draws):")
    for team, v in sorted(d["exposure"].items(), key=lambda kv: -kv[1]["expected_series"]):
        bars = " ".join(f"{n}:{p:.3f}" for n, p in sorted(v["dist"].items()))
        print(f"  {team:<16} E[series] {v['expected_series']:.3f}   {bars}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
