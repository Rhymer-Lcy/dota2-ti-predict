"""End-to-end TI15 group-stage prediction pipeline (gated).

Chains: team identity -> B-bt strengths -> Swiss Monte-Carlo (swiss.py) -> 16x6 bucket matrix ->
assignment solver (assign.py) -> D4 sensitivity -> JSON (fact source) + Markdown + run manifest.

Two modes, by design:
  --dry-run   pipeline rehearsal on synthetic or historical inputs. Writes to <repo>/.dryrun/.
              Every artifact is stamped "DRY RUN - NOT OFFICIAL". Never emits an official slate.
  --official  the real slate. HARD-GATED: refuses to run unless ALL are present -- the posted draw
              file (two pods + round-1 pairings), an explicit frozen --cutoff, and B-bt strengths
              (--strengths bt) computed for all 16 teams. Missing any -> exit with an error.

This prevents a rehearsal from ever masquerading as the official prediction. The main-event
(14-series) track is deferred until the group draw is set.

Rules, assumptions and their scope live in docs/contest-official-ti15.md. "Rule verification" here
means the simulator passed STRUCTURAL / PROPERTY tests (swiss.py), NOT that it replicates the
organizer's unpublished pairing decisions.

Usage:
  python -m ti_predict.predict_ti15 --dry-run
  python -m ti_predict.predict_ti15 --dry-run --strengths bt --cutoff 2026-06-01
  python -m ti_predict.predict_ti15 --official --draw data/ti2026/inputs/draw.json \
      --strengths bt --cutoff 2026-08-13
"""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.swiss import BUCKETS, CAPACITY, monte_carlo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
TEAMS_CSV = os.path.join(INPUTS, "teams.csv")
D4_SCENARIOS = ("strategic", "noisy", "random")
C5_POLICY = ("enumerate legal perfect pairings; minimize rematches, then optimize the rank-gap "
             "objective (min, or max for round-5 elimination matches), then break ties at random "
             "with a fixed seed")


def _commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def load_teams():
    import csv
    with open(TEAMS_CSV, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 16, f"teams.csv must list 16 teams, found {len(rows)}"
    return rows


def synthetic_strengths(teams):
    """Deterministic, clearly NON-predictive strengths spread over a range, for dry-run only."""
    n = len(teams)
    return {t["team"]: round(-1.4 + 2.8 * i / (n - 1), 4) for i, t in enumerate(teams)}


def bt_strengths_for(teams, cutoff_date):
    """Real B-bt log-strengths as of the cutoff, mapped to the 16 teams by ORGANIZATION NAME.

    The frozen universe (universe.py) collapses each TI roster's source_team_ids to its organization
    name, so a team's strength key is teams.csv 'team' (== canonical organization), not a raw
    opendota_team_id. Requires the processed universe dataset; raises clearly if data or keys are
    missing.
    """
    from ti_predict.backtest import load
    from ti_predict.calibrate import bt_strengths
    cut = int(datetime.strptime(cutoff_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    uni, _, _ = load()
    train = [m for m in uni if m["start_time"] < cut]
    if not train:
        raise SystemExit(f"no training maps before cutoff {cutoff_date}")
    smap = bt_strengths(train, cut)
    out, missing = {}, []
    for t in teams:
        key = t["team"]                      # organization name == universe.py ident() for TI rosters
        if key in smap:
            out[key] = float(smap[key])
        else:
            missing.append(key)
    if missing:
        raise SystemExit("B-bt strengths missing for: " + ", ".join(missing)
                         + "\n(check organization name vs universe key / roster canonicalization)")
    return out, len(train)


def resolve_draw(teams, draw_path):
    """Return (pods, r1_pairings, source). Draw file references teams by their teams.csv 'team' name."""
    names = {t["team"] for t in teams}
    if draw_path:
        with open(draw_path, encoding="utf-8") as fh:
            d = json.load(fh)
        podA, podB = d["podA"], d["podB"]
        r1 = [tuple(p) for p in d.get("r1_pairings", [])] or None
        for grp in (podA, podB, [x for p in (r1 or []) for x in p]):
            bad = [x for x in grp if x not in names]
            assert not bad, f"draw references unknown teams: {bad}"
        assert len(podA) == 8 and len(podB) == 8, "each pod must have 8 teams"
        return (podA, podB), r1, os.path.relpath(draw_path, REPO)
    # synthetic split (dry-run only): alternate teams.csv order into two pods; random round 1
    order = [t["team"] for t in teams]
    return (order[0::2], order[1::2]), None, "synthetic (teams.csv split, random round 1)"


def se(p, n):
    return math.sqrt(max(p * (1 - p), 0.0) / n)


def sensitivity(pods, strength, n, seed, r1):
    """Run all three D4 scenarios; return {scenario: P} and the buckets whose membership changes."""
    Ps = {sc: monte_carlo(pods, strength, n=n, seed=seed, r1_pairings=r1, elim_choice=sc)
          for sc in D4_SCENARIOS}
    slates = {sc: {b: {t for t, _ in assign(Ps[sc])[0][b]} for b in BUCKETS} for sc in D4_SCENARIOS}
    sensitive = {}
    base = slates["strategic"]
    for b in BUCKETS:
        union = set().union(*(slates[sc][b] for sc in D4_SCENARIOS))
        if any(slates[sc][b] != base[b] for sc in D4_SCENARIOS):
            sensitive[b] = sorted(union - base[b] | base[b] - union
                                  | {t for sc in D4_SCENARIOS for t in slates[sc][b] ^ base[b]})
    return Ps, sensitive


def build(teams, strength, pods, r1, draw_source, n, seed, mode, cutoff, strengths_source,
          train_maps):
    P, diag = monte_carlo(pods, strength, n=n, seed=seed, r1_pairings=r1,
                          elim_choice="strategic", return_diag=True)
    slate, exp_correct, rows = assign(P)
    _, sensitive = sensitivity(pods, strength, n, seed, r1)

    assigned = {t: b for t, b, _ in rows}
    per_team = {}
    for t in P:
        b = assigned[t]
        ranked = sorted(BUCKETS, key=lambda x: -P[t][x])
        second = ranked[1] if ranked[0] == b else ranked[0]
        per_team[t] = {"assigned": b, "p": round(P[t][b], 4), "se": round(se(P[t][b], n), 4),
                       "second_best": second, "second_p": round(P[t][second], 4),
                       "gap": round(P[t][b] - P[t][second], 4)}
    slate_out = {b: [{"team": t, "p": round(p, 4), "se": round(se(p, n), 4)} for t, p in slate[b]]
                 for b in BUCKETS}

    manifest = {
        "mode": mode,
        "status": "OFFICIAL" if mode == "official" else "DRY RUN - NOT OFFICIAL",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _commit(),
        "data_cutoff": cutoff,
        "strengths_source": strengths_source,
        "training_maps": train_maps,
        "n_sims": n, "seed": seed,
        "c5_pairing_policy": C5_POLICY,
        "d4_primary": "strategic", "d4_scenarios": list(D4_SCENARIOS),
        "d4_selection_sensitive_buckets": sensitive,
        "tiebreak_diagnostic": {"tie_16_rate": round(diag["tie_16_rate"], 4),
                                "tie_32_rate": round(diag["tie_32_rate"], 4),
                                "note": "fraction of sims where a coin toss arbitrated the standings "
                                        "(tie_16) / the bucket-relevant 3-2 pick order (tie_32)"},
        "draw_source": draw_source,
        "pods": {"A": list(pods[0]), "B": list(pods[1])},
        "r1_pairings": [list(p) for p in r1] if r1 else None,
        "teams": [{"team": t["team"], "alias": t["ti_alias"], "region": t["region"],
                   "opendota_team_id": t["opendota_team_id"], "note": t["notes"]} for t in teams],
        "expected_correct": round(exp_correct, 3),
        "caveats": ["model-only; NOT validated against historical market increment",
                    "structural/property tested, not a replica of unpublished pairing decisions",
                    "C5 pairing and D4 opponent-choice are modeling assumptions (see docs)"],
    }
    return {"manifest": manifest, "probabilities": {t: {b: round(P[t][b], 4) for b in BUCKETS}
                                                    for t in P},
            "slate": slate_out, "per_team": per_team, "expected_correct": round(exp_correct, 3)}


def to_markdown(out):
    m = out["manifest"]
    L = [f"# TI15 group-stage prediction ({m['status']})", "",
         f"- mode: **{m['mode']}** | commit `{m['code_commit']}` | generated {m['generated_at']}",
         f"- strengths: {m['strengths_source']} | cutoff: {m['data_cutoff']} | "
         f"sims: {m['n_sims']} | seed: {m['seed']}",
         f"- draw: {m['draw_source']}",
         f"- expected correct: **{m['expected_correct']} / 16**", ""]
    if m["mode"] != "official":
        L += ["> DRY RUN - synthetic/historical inputs; NOT the official prediction.", ""]
    L += ["## Slate (assignment maximizing expected correct)", ""]
    for b in BUCKETS:
        picks = ", ".join(f"{c['team']} ({c['p']:.2f}+/-{c['se']:.2f})" for c in out["slate"][b])
        star = "  [selection-sensitive]" if b in m["d4_selection_sensitive_buckets"] else ""
        L.append(f"- **{b}** x{CAPACITY[b]}: {picks}{star}")
    L += ["", "## Bucket probability matrix (rows = teams)", "",
          "| team | " + " | ".join(BUCKETS) + " |",
          "|" + "---|" * (len(BUCKETS) + 1)]
    order = sorted(out["probabilities"], key=lambda t: -out["per_team"][t]["p"])
    for t in order:
        L.append("| " + t + " | " + " | ".join(f"{out['probabilities'][t][b]:.3f}" for b in BUCKETS)
                 + " |")
    L += ["", "## Notes",
          f"- tiebreak coin-toss rate: standings {m['tiebreak_diagnostic']['tie_16_rate']:.3f}, "
          f"3-2 pick order {m['tiebreak_diagnostic']['tie_32_rate']:.3f}",
          f"- D4 selection-sensitive buckets: "
          f"{m['d4_selection_sensitive_buckets'] or 'none'}",
          "- " + "; ".join(m["caveats"])]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="TI15 group-stage prediction pipeline (gated)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--official", action="store_true")
    ap.add_argument("--strengths", choices=("synthetic", "bt"), default="synthetic")
    ap.add_argument("--cutoff", help="YYYY-MM-DD frozen data cutoff (required for bt / official)")
    ap.add_argument("--draw", help="path to draw.json (pods + round-1 pairings)")
    ap.add_argument("--sims", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--out", help="output directory")
    a = ap.parse_args()
    mode = "official" if a.official else "dry-run"
    teams = load_teams()

    # ---- hard gate for the official slate ----
    if a.official:
        problems = []
        if not a.draw or not os.path.exists(a.draw or ""):
            problems.append("--draw must point to the posted official draw file (pods + round 1)")
        if a.strengths != "bt":
            problems.append("--strengths must be 'bt' (no synthetic strengths in official mode)")
        if not a.cutoff:
            problems.append("--cutoff (frozen data cutoff) is required")
        if problems:
            sys.exit("OFFICIAL RUN BLOCKED:\n  - " + "\n  - ".join(problems))

    # ---- strengths ----
    train_maps = None
    if a.strengths == "bt":
        if not a.cutoff:
            sys.exit("--strengths bt requires --cutoff YYYY-MM-DD")
        strength, train_maps = bt_strengths_for(teams, a.cutoff)
        ssrc = f"B-bt @ {a.cutoff}"
    else:
        strength = synthetic_strengths(teams)
        ssrc = "synthetic (non-predictive)"

    pods, r1, draw_source = resolve_draw(teams, a.draw)
    out = build(teams, strength, pods, r1, draw_source, a.sims, a.seed, mode, a.cutoff, ssrc,
                train_maps)

    outdir = a.out or (os.path.join(REPO, "predictions", "ti2026", "group-stage")
                       if a.official else os.path.join(REPO, ".dryrun"))
    os.makedirs(outdir, exist_ok=True)
    stem = "ti15_group_prediction" if a.official else "ti15_group_dryrun"
    with open(os.path.join(outdir, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, stem + ".md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(out))
    print(to_markdown(out))
    print(f"[{out['manifest']['status']}] wrote {stem}.json / .md to {os.path.relpath(outdir, REPO)}")


if __name__ == "__main__":
    main()
