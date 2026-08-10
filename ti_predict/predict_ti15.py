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
      --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 120000
  (official mode REQUIRES a timezone-aware ISO timestamp; replace 02:00:00Z with the lock time
  confirmed in-client on the day)
"""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.assign import assign
from ti_predict.contest_rules import (GROUP_SCORE, PRODUCTION_HALF_LIFE_DAYS, STALE_MAX_DAYS)
from ti_predict.swiss import BUCKETS, CAPACITY, d4_sensitivity_crn, monte_carlo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
PROC = os.path.join(REPO, "data", "ti2026", "processed")
TEAMS_CSV = os.path.join(INPUTS, "teams.csv")
CANON_CSV = os.path.join(INPUTS, "canonical_identity.csv")
UNIVERSE_CSV = os.path.join(PROC, "universe_maps.csv")
D4_SCENARIOS = ("strategic", "noisy", "random")
STALE_SECS = STALE_MAX_DAYS * 86400   # official run rejects a universe whose latest map is too old
C5_POLICY = ("enumerate legal perfect pairings; minimize rematches, then optimize the rank-gap "
             "objective (min, or max for round-5 elimination matches), then break ties at random "
             "with a fixed seed")


def _commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def _git_dirty():
    try:
        return bool(subprocess.check_output(["git", "-C", REPO, "status", "--porcelain"],
                                            text=True).strip())
    except Exception:
        return None


def _sha256(path):
    import hashlib
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _relpath(p):
    """Repo-relative path for display, tolerant of a draw file on a different drive/mount."""
    try:
        return os.path.relpath(p, REPO)
    except ValueError:
        return p


def _tz_aware(s):
    """True only for a timezone-aware ISO timestamp WITH a time component (rejects date-only)."""
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    return dt.tzinfo is not None and "T" in str(s)


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


def parse_cutoff(s):
    """Accept 'YYYY-MM-DD' or a full ISO-8601 timestamp (e.g. 2026-08-13T02:00:00Z).

    Returns (unix_ts, canonical_utc_iso). A date-only value is treated as 00:00 UTC; official runs
    require a full timestamp so pre-lock same-day matches are not silently excluded.
    """
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp()), dt.astimezone(timezone.utc).isoformat()


def bt_strengths_for(teams, cut_ts):
    """Real B-bt log-strengths + radiant coefficient c as of the cutoff, keyed by ORGANIZATION NAME.

    The frozen universe (universe.py) collapses each TI roster's source_team_ids to its organization
    name, so a team's strength key is teams.csv 'team' (== canonical organization), not a raw
    opendota_team_id. c is the train-only radiant coefficient (calibrate.est_c) used for the frozen
    side-neutral map prob. Requires the processed universe dataset; raises clearly if data/keys are
    missing. Returns (strengths, c, n_train).
    """
    from ti_predict.backtest import load
    from ti_predict.calibrate import bt_strengths, est_c
    if not os.path.exists(UNIVERSE_CSV):
        raise SystemExit(
            "processed universe not found (data/ti2026/processed/universe_maps.csv). The public repo "
            "does not ship match data; regenerate it per docs/lockday-runbook.md: fetch_opendota -> "
            "resolve_identity / roster_coverage -> build_canonical -> universe -> build_dataset.")
    uni, _, _ = load()
    train = [m for m in uni if m["start_time"] < cut_ts]
    if not train:
        raise SystemExit("no training maps before cutoff")
    smap = bt_strengths(train, cut_ts, hl=PRODUCTION_HALF_LIFE_DAYS)
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
    uni_max = max(m["start_time"] for m in uni)
    return out, float(est_c(train, smap)), len(train), len(uni), uni_max


def resolve_draw(teams, draw_path, require_r1=False):
    """Return (pods, r1_pairings, source). Draw file references teams by their teams.csv 'team' name.

    Full validation: pods are two disjoint sets of 8 that partition exactly the 16 teams with no
    duplicates; if require_r1 (official mode) the round-1 draw MUST be present, exactly 8 within-pod
    matches of two distinct teams covering every team exactly once. A missing r1 is rejected in
    official mode (it would otherwise be randomized yet still labeled OFFICIAL).
    """
    names = {t["team"] for t in teams}
    if not draw_path:
        if require_r1:
            sys.exit("official run requires --draw with the posted pods and round-1 pairings")
        order = [t["team"] for t in teams]      # synthetic split (dry-run only), random round 1
        return (order[0::2], order[1::2]), None, "synthetic (teams.csv split, random round 1)"

    try:
        with open(draw_path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"draw: cannot read {draw_path}: {e}")
    if not isinstance(d, dict):
        sys.exit("draw: top-level JSON must be an object with podA/podB/r1_pairings")
    podA, podB = list(d.get("podA", [])), list(d.get("podB", []))
    if len(podA) != 8 or len(podB) != 8:
        sys.exit("draw: podA and podB must each list 8 teams")
    allp = podA + podB
    if len(set(allp)) != 16:
        sys.exit("draw: pods must be 16 distinct teams (duplicate or overlap found)")
    if set(allp) != names:
        sys.exit(f"draw: pods must partition exactly the 16 teams; mismatch {set(allp) ^ names}")
    pod_of = {t: "A" for t in podA}; pod_of.update({t: "B" for t in podB})

    raw = d.get("r1_pairings") or []
    if not raw:
        if require_r1:
            sys.exit("draw: official run requires r1_pairings (the posted round-1 matchups)")
        return (podA, podB), None, _relpath(draw_path)
    r1 = [tuple(p) for p in raw]
    if len(r1) != 8:
        sys.exit(f"draw: r1_pairings must have exactly 8 matches, found {len(r1)}")
    seen = []
    for a, b in r1:
        if a not in names or b not in names:
            sys.exit(f"draw: r1 references unknown team(s): {a}, {b}")
        if a == b:
            sys.exit(f"draw: r1 match has a team against itself: {a}")
        if pod_of[a] != pod_of[b]:
            sys.exit(f"draw: r1 match crosses pods: {a} vs {b}")
        seen += [a, b]
    if sorted(seen) != sorted(allp):
        sys.exit("draw: r1_pairings must cover every team exactly once")
    return (podA, podB), r1, _relpath(draw_path)


def se(p, n):
    return math.sqrt(max(p * (1 - p), 0.0) / n)


_FVEC = np.array([GROUP_SCORE[k] for k in range(17)])
_BIDX = {b: i for i, b in enumerate(BUCKETS)}


def _points(asg, arch):
    """Expected official points of an assignment on a simulation archive (numpy bucket indices)."""
    n = len(next(iter(arch.values())))
    K = np.zeros(n, dtype=np.int16)
    for t, b in asg.items():
        K += arch[t] == _BIDX[b]
    return float(_FVEC[K].mean()), K


def _swap_search(asg, arch):
    """Pairwise-swap hill climb on expected official points (local optimum, not global)."""
    asg = dict(asg)
    best, K = _points(asg, arch)
    teams = list(asg)
    for _ in range(6):
        improved = False
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                t1, t2 = teams[i], teams[j]
                b1, b2 = asg[t1], asg[t2]
                if b1 == b2:
                    continue
                delta = ((arch[t1] == _BIDX[b2]).astype(np.int16) + (arch[t2] == _BIDX[b1])
                         - (arch[t1] == _BIDX[b1]) - (arch[t2] == _BIDX[b2]))
                cand = float(_FVEC[K + delta].mean())
                if cand > best + 1e-9:
                    asg[t1], asg[t2] = b2, b1
                    K = K + delta
                    best = cand
                    improved = True
        if not improved:
            break
    return asg, best


def points_refinement(asgA, arch_opt, arch_ver, seed):
    """Verified expected-points refinement of the Hungarian slate (decision layer only).

    Swap-search on the optimize archive proposes a slate; it is adopted ONLY if an independent
    verification archive shows a paired per-simulation points gain over the Hungarian slate
    exceeding two bootstrap standard errors. Otherwise the Hungarian slate stands.

    Evidence (adversarially audited, backtest2/refine_audit.py + results-adversarial.md): the true
    effect of a boundary-pair swap is about +6 points (fresh-archive combined estimate +6.5 +/- 1.0;
    the originally reported +18.3 was a winner's-curse-typical high draw). In 30 end-to-end
    replications the rule adopted zero harmful moves; on draws without a boundary pair it proposes
    rarely and the gate filters further. NOTE: the paired_gain recorded in the manifest is
    conditioned on adoption and therefore biased upward (observed factor about 1.7); read it as an
    optimistic estimate of a genuinely positive effect. Gate power at 40k sims is about 80% for a
    true +6 effect; 120000 sims raise it to about 94% (recommended for the official run).
    Multi-start, 3-cycle and simulated-annealing searches found nothing beyond pairwise swaps.
    """
    asgB, _ = _swap_search(asgA, arch_opt)
    moves = sorted(t for t in asgB if asgB[t] != asgA[t])
    if not moves:
        return asgA, {"proposed_moves": [], "adopted": False, "paired_gain": 0.0,
                      "paired_gain_se": 0.0, "rule": "no move proposed; Hungarian slate stands"}
    n = len(next(iter(arch_ver.values())))
    _, KB = _points(asgB, arch_ver)
    _, KA = _points(asgA, arch_ver)
    d = _FVEC[KB].astype(np.float64) - _FVEC[KA]
    rng = np.random.default_rng(seed)
    boots = [float(d[rng.integers(0, n, n)].mean()) for _ in range(500)]
    gain, se_ = float(d.mean()), float(np.std(boots))
    adopted = gain > 2.0 * se_
    return (asgB if adopted else asgA), {
        "proposed_moves": moves, "adopted": bool(adopted),
        "paired_gain": round(gain, 1), "paired_gain_se": round(se_, 1),
        "rule": "adopt iff independent-archive paired gain > 2 se"}


def sensitivity(pods, strength, n, seed, r1, c=0.0):
    """CRN D4 sensitivity: buckets whose membership changes across opponent-choice scenarios, with a
    shared Swiss outcome + shared match RNG per sim (isolates the choice effect from path noise)."""
    Ps = d4_sensitivity_crn(pods, strength, n=n, seed=seed, r1_pairings=r1, c=c, choices=D4_SCENARIOS)
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
          train_maps, c=0.0, provenance=None):
    P, diag, arch = monte_carlo(pods, strength, n=n, seed=seed, r1_pairings=r1,
                                elim_choice="strategic", return_diag=True, c=c,
                                return_archive=True)
    arch = {t: np.asarray(v, dtype=np.int8) for t, v in arch.items()}
    slate_h, exp_correct_h, rows_h = assign(P)
    asgA = {t: b for t, b, _ in rows_h}

    # verified expected-points refinement (decision layer; independent verification archive)
    _, arch_ver = monte_carlo(pods, strength, n=n, seed=seed + 424243, r1_pairings=r1,
                              elim_choice="strategic", c=c, return_archive=True)
    arch_ver = {t: np.asarray(v, dtype=np.int8) for t, v in arch_ver.items()}
    assigned, refine = points_refinement(asgA, arch, arch_ver, seed + 7)

    slate = {b: sorted(((t, P[t][b]) for t in assigned if assigned[t] == b),
                       key=lambda x: -x[1]) for b in BUCKETS}
    rows = [(t, assigned[t], P[t][assigned[t]]) for t in assigned]
    exp_correct = sum(p for _, _, p in rows)
    refine["hungarian_expected_correct"] = round(exp_correct_h, 3)

    _, sensitive = sensitivity(pods, strength, n, seed, r1, c=c)
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
        "radiant_c": round(c, 4),
        "half_life_days": PRODUCTION_HALF_LIFE_DAYS,
        "map_prob": "side-neutral 0.5*(sigmoid(d+c)+sigmoid(d-c))",
        "training_maps": train_maps,
        "provenance": provenance,
        "n_sims": n, "seed": seed,
        "c5_pairing_policy": C5_POLICY,
        "points_refinement": refine,
        "d4_primary": "strategic", "d4_scenarios": list(D4_SCENARIOS),
        "d4_selection_sensitive_buckets": sensitive,
        "tiebreak_diagnostic": {"tie_16_rate": round(diag["tie_16_rate"], 4),
                                "tie_32_rate": round(diag["tie_32_rate"], 4),
                                "note": "fraction of sims where the first five tiebreakers all tie, "
                                        "so the result falls to the unmodeled avg-duration/coin-toss "
                                        "tail: overall (tie_16) / bucket-relevant 3-2 pick order "
                                        "(tie_32)"},
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
          f"- first-five-tiebreakers-tie rate (falls to unmodeled avg-duration/coin-toss tail): "
          f"standings {m['tiebreak_diagnostic']['tie_16_rate']:.3f}, "
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
    ap.add_argument("--cutoff", help="date (YYYY-MM-DD) for dry-run; official needs a full ISO "
                                     "timestamp with timezone, e.g. 2026-08-13T02:00:00Z")
    ap.add_argument("--draw", help="path to draw.json (pods + round-1 pairings)")
    ap.add_argument("--sims", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--allow-stale", action="store_true",
                    help="official: skip the data-freshness gate (use only if there genuinely are no "
                         "pre-lock matches near the cutoff)")
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
        if not _tz_aware(a.cutoff):
            problems.append("--cutoff must be a timezone-aware ISO timestamp with a time, e.g. "
                            "2026-08-13T02:00:00Z (date-only would truncate at 00:00 UTC)")
        if problems:
            sys.exit("OFFICIAL RUN BLOCKED:\n  - " + "\n  - ".join(problems))

    # ---- strengths ----
    train_maps, c, cut_iso, provenance = None, 0.0, a.cutoff, None
    if a.strengths == "bt":
        if not a.cutoff:
            sys.exit("--strengths bt requires --cutoff (YYYY-MM-DD or full ISO timestamp)")
        cut_ts, cut_iso = parse_cutoff(a.cutoff)
        strength, c, train_maps, uni_rows, uni_max = bt_strengths_for(teams, cut_ts)
        ssrc = f"B-bt @ {cut_iso} (radiant c={c:+.3f})"
        provenance = {"requested_cutoff": cut_iso, "universe_rows": uni_rows,
                      "universe_max_start_time": _iso(uni_max),
                      "universe_lag_days_before_cutoff": round((cut_ts - uni_max) / 86400, 2),
                      "teams_sha256": _sha256(TEAMS_CSV),
                      "canonical_identity_sha256": _sha256(CANON_CSV),
                      "universe_sha256": _sha256(UNIVERSE_CSV), "draw_sha256": _sha256(a.draw),
                      "git_commit": _commit(), "git_dirty": _git_dirty()}
        # data-freshness gate: a stale universe must not silently produce an OFFICIAL slate
        if a.official and not a.allow_stale and (cut_ts - uni_max) > STALE_SECS:
            sys.exit(f"OFFICIAL RUN BLOCKED: universe latest map {_iso(uni_max)} is "
                     f"{provenance['universe_lag_days_before_cutoff']}d before cutoff {cut_iso}; "
                     f"refresh the data (or pass --allow-stale if there truly are no pre-lock games).")
        if a.official and provenance["git_dirty"]:
            print("WARNING: repo is dirty (uncommitted changes) for an official run.", file=sys.stderr)
    else:
        strength = synthetic_strengths(teams)
        ssrc = "synthetic (non-predictive)"

    pods, r1, draw_source = resolve_draw(teams, a.draw, require_r1=a.official)
    if provenance is not None:
        provenance["draw_sha256"] = _sha256(a.draw)      # recompute now the draw path is validated
    out = build(teams, strength, pods, r1, draw_source, a.sims, a.seed, mode, cut_iso, ssrc,
                train_maps, c=c, provenance=provenance)

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
