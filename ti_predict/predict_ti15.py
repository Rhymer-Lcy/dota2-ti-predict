"""End-to-end TI15 group-stage prediction pipeline (gated).

Chains: team identity -> B-bt strengths -> Swiss Monte-Carlo (swiss.py) -> 16x6 bucket matrix ->
assignment solver (assign.py) -> D4 sensitivity -> JSON (fact source) + Markdown + run manifest.

Three modes, by design:
  --dry-run   pipeline rehearsal on synthetic or historical inputs. Writes to <repo>/.dryrun/.
              Every artifact is stamped "DRY RUN - NOT OFFICIAL". Never emits an official slate.
  --candidate the production answer as of NOW: identical inputs, identical gates and identical
              computation to --official, but stamped "SUBMISSION-GRADE CANDIDATE - NOT FINAL
              LOCK-DAY RUN" and written to predictions/.../candidates/ under a UTC-stamped file
              name. It answers "what would we submit if the client demanded it right now" without
              ever occupying the final artifact's path or label.
  --official  the real slate. HARD-GATED: refuses to run unless ALL are present -- the posted
              round-1 pairings, a CONFIRMED structure (the official two-pod format; the open-16 pool
              is a sensitivity comparator and is refused here), an explicit timezone-aware --cutoff,
              B-bt strengths (--strengths bt) for all 16 teams, a roster audit with no
              CONFLICT/UNRESOLVED team, and a fresh universe. Missing any -> actionable error.
              If the pod MEMBERSHIP is still unpublished the slate is marginalized over every
              membership compatible with round 1, the manifest records that, and the run is blocked
              if any admissible membership would have made a materially better slate.

This prevents a rehearsal from ever masquerading as the official prediction. The main-event
(14-series) track is deferred until the group draw is set.

Rules, assumptions and their scope live in docs/contest-official-ti15.md. "Rule verification" here
means the simulator passed STRUCTURAL / PROPERTY tests (swiss.py), NOT that it replicates the
organizer's unpublished pairing decisions.

Usage:
  python -m ti_predict.predict_ti15 --dry-run
  python -m ti_predict.predict_ti15 --dry-run --strengths bt --cutoff 2026-06-01
  python -m ti_predict.predict_ti15 --candidate --draw data/ti2026/inputs/draw.json \
      --strengths bt --cutoff 2026-08-13T02:00:00Z --sims 280000
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
from ti_predict.contest_rules import (GROUP_SCORE, POD_MEMBERSHIP_REGRET_MAX, POD_STRUCTURE,
                                      PRODUCTION_HALF_LIFE_DAYS, STALE_MAX_DAYS)
from ti_predict.rosters import roster_audit
from ti_predict.swiss import (BUCKETS, CAPACITY, admissible_two_pod_partitions, d4_sensitivity_crn,
                              is_two_pod, monte_carlo, teams_of)

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


def read_draw(draw_path):
    """Load the draw JSON as a dict, or {} when no path is given. Exits on unreadable/invalid JSON."""
    if not draw_path:
        return {}
    try:
        with open(draw_path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"draw: cannot read {draw_path}: {e}")
    if not isinstance(d, dict):
        sys.exit("draw: top-level JSON must be an object with podA/podB/r1_pairings")
    return d


def draw_status(draw_path):
    """Publication status of the draw, for the run manifest: what is official and what is assumed.

    Three separate facts, deliberately not collapsed into one flag:
      structure               -- 'two_pod' (the official rule) or 'open-16' (sensitivity comparator);
      structure_status        -- whether that structure is an official rule or an assumption;
      pod_membership_status   -- whether the actual eight-team split is published.
    A feed that carries no pod field leaves MEMBERSHIP unresolved; it says nothing about STRUCTURE.
    """
    d = read_draw(draw_path)
    if not d:
        return {"r1_status": "synthetic", "structure": "two_pod", "structure_status": "synthetic",
                "pod_membership_status": "synthetic", "structure_evidence": None,
                "pod_membership_evidence": None, "feed_sha256": None, "retrieved_at": None}
    return {"r1_status": str(d.get("r1_status", "unknown")).lower(),
            "structure": str(d.get("structure", POD_STRUCTURE)).lower(),
            "structure_status": str(d.get("structure_status", "confirmed")).lower(),
            "pod_membership_status": str(d.get("pod_membership_status", "confirmed")).lower(),
            "structure_evidence": d.get("structure_evidence"),
            "pod_membership_evidence": d.get("pod_membership_evidence") or d.get("source"),
            "feed_sha256": d.get("feed_sha256"), "retrieved_at": d.get("retrieved_at")}


def resolve_draw(teams, draw_path, require_r1=False):
    """Return (pods, r1_pairings, source). Draw file references teams by their teams.csv 'team' name.

    `pods` is:
      (podA, podB) -- the published two-pod membership;
      None         -- two-pod structure with UNRESOLVED membership: the caller must marginalize over
                      swiss.admissible_two_pod_partitions(r1);
      (teams,)     -- the open 16-team pool. NOT the official format; a sensitivity comparator only,
                      and refused in official mode.

    Full validation: a published membership is two disjoint sets of 8 partitioning exactly the 16
    teams; if require_r1 (official mode) the round-1 draw MUST be present -- exactly 8 matches of two
    distinct teams covering every team once, and within pods when the membership is published. A
    missing r1 is rejected in official mode (it would otherwise be randomized yet still labeled
    OFFICIAL), and so is any structure whose status is not 'confirmed'.
    """
    names = {t["team"] for t in teams}
    if not draw_path:
        if require_r1:
            sys.exit("official run requires --draw with the posted pods and round-1 pairings")
        order = [t["team"] for t in teams]      # synthetic split (dry-run only), random round 1
        return (order[0::2], order[1::2]), None, "synthetic (teams.csv split, random round 1)"

    d = read_draw(draw_path)
    structure = str(d.get("structure", POD_STRUCTURE)).lower()
    structure_status = str(d.get("structure_status", "confirmed")).lower()
    membership = str(d.get("pod_membership_status", "confirmed")).lower()
    if structure not in ("two_pod", "open-16"):
        sys.exit(f"draw: structure must be 'two_pod' or 'open-16', found {structure!r}")
    if structure_status not in ("confirmed", "assumed"):
        sys.exit("draw: structure_status must be 'confirmed' or 'assumed', found "
                 f"{structure_status!r}")
    if require_r1 and structure_status != "confirmed":
        sys.exit(f"OFFICIAL RUN BLOCKED: draw declares structure_status={structure_status!r}; an "
                 "official slate needs a CONFIRMED pairing structure, not an assumed one.")
    if membership not in ("confirmed", "unresolved"):
        sys.exit("draw: pod_membership_status must be 'confirmed' or 'unresolved', found "
                 f"{membership!r}")
    if structure == "open-16":
        if require_r1:
            sys.exit("OFFICIAL RUN BLOCKED: structure='open-16' is a sensitivity comparator, not the "
                     "official format. The official TI15 rules split the field into two initial "
                     "groups (rounds 1-3 inside the group, round 4 across), so an official slate "
                     "must use structure='two_pod'.")
        pods, pod_of, allp = (sorted(names),), None, sorted(names)
    elif membership == "unresolved":
        # Two-pod structure is an official rule; only WHICH eight teams are in each group is
        # unpublished. The caller marginalizes over every partition compatible with round 1.
        pods, pod_of, allp = None, None, sorted(names)
    else:
        podA, podB = list(d.get("podA", [])), list(d.get("podB", []))
        if len(podA) != 8 or len(podB) != 8:
            sys.exit("draw: podA and podB must each list 8 teams")
        allp = podA + podB
        if len(set(allp)) != 16:
            sys.exit("draw: pods must be 16 distinct teams (duplicate or overlap found)")
        if set(allp) != names:
            sys.exit(f"draw: pods must partition exactly the 16 teams; mismatch {set(allp) ^ names}")
        pod_of = {t: "A" for t in podA}; pod_of.update({t: "B" for t in podB})
        pods = (podA, podB)

    raw = d.get("r1_pairings") or []
    if not raw:
        if require_r1:
            sys.exit("draw: official run requires r1_pairings (the posted round-1 matchups)")
        return pods, None, _relpath(draw_path)
    r1 = [tuple(p) for p in raw]
    if len(r1) != 8:
        sys.exit(f"draw: r1_pairings must have exactly 8 matches, found {len(r1)}")
    seen = []
    for a, b in r1:
        if a not in names or b not in names:
            sys.exit(f"draw: r1 references unknown team(s): {a}, {b}")
        if a == b:
            sys.exit(f"draw: r1 match has a team against itself: {a}")
        if pod_of is not None and pod_of[a] != pod_of[b]:
            sys.exit(f"draw: r1 match crosses pods: {a} vs {b}")
        seen += [a, b]
    if sorted(seen) != sorted(allp):
        sys.exit("draw: r1_pairings must cover every team exactly once")
    return pods, r1, _relpath(draw_path)


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


def _pods_manifest(pods_list, agreement):
    """What the artifact claims about the pod structure -- never more than is published."""
    if len(pods_list) == 1 and not is_two_pod(pods_list[0]):
        return {"structure": "open-16", "structure_status": "comparator (NOT the official format)",
                "teams": teams_of(pods_list[0])}
    if len(pods_list) == 1:
        return {"structure": POD_STRUCTURE, "pod_membership_status": "confirmed",
                "A": list(pods_list[0][0]), "B": list(pods_list[0][1])}
    return {"structure": POD_STRUCTURE, "structure_status": "confirmed (official rule)",
            "pod_membership_status": "unresolved",
            "handling": "marginalized over every pod membership compatible with the posted round 1",
            "membership_agreement": agreement}


def _marginal_mc(pods_list, strength, n, seed, r1, c, return_diag=False):
    """Simulate every admissible pod structure and pool the results.

    `n` is the TOTAL number of simulations, split evenly across the structures, so the pooled archive
    keeps the precision the caller asked for (and with it the points-refinement gate power) no matter
    how many memberships are still admissible. Returns (P, archive, per_structure_P, diag).
    """
    n_each = max(1, n // len(pods_list))
    archs, per_struct, tie16, tie32, tot = [], [], 0.0, 0.0, 0
    for k, pods in enumerate(pods_list):
        out = monte_carlo(pods, strength, n=n_each, seed=seed + 1009 * k, r1_pairings=r1,
                          elim_choice="strategic", return_diag=return_diag, c=c, return_archive=True)
        if return_diag:
            Pk, dg, ak = out
            tie16 += dg["tie_16_rate"] * n_each; tie32 += dg["tie_32_rate"] * n_each
        else:
            Pk, ak = out
        per_struct.append(Pk)
        archs.append({t: np.asarray(v, dtype=np.int8) for t, v in ak.items()})
        tot += n_each
    teams = list(archs[0])
    arch = {t: np.concatenate([a[t] for a in archs]) for t in teams}
    P = {t: {b: float((arch[t] == _BIDX[b]).sum()) / tot for b in BUCKETS} for t in teams}
    diag = ({"tie_16_rate": tie16 / tot, "tie_32_rate": tie32 / tot, "n": tot}
            if return_diag else None)
    return P, arch, per_struct, diag


def membership_agreement(per_opt, per_ver, assigned):
    """How much the unresolved pod membership could cost, if the slate were wrong about it.

    For every admissible membership: does its own optimal slate equal the submitted one, and if not,
    how many expected-correct slots does submitting the marginalized slate give up under that
    membership? Label disagreement alone is not decisive here -- three teams sit within 0.01 of each
    other in the extreme buckets, so per-membership slates reshuffle on Monte-Carlo noise at any
    affordable simulation count. The regret is what says whether being wrong would matter.

    The regret is measured OUT OF SAMPLE: each membership's alternative slate is chosen on the
    optimize archive and scored on the independent verification archive. Scoring a slate on the
    archive that selected it is the same winner's-curse trap the points refinement was corrected for
    (backtest2/results-adversarial.md) -- in-sample it reported 0.21 expected correct where the
    held-out value is near zero.
    """
    identical, regrets = 0, []
    for Popt, Pver in zip(per_opt, per_ver):
        _, _, rows = assign(Popt)
        alt = {t: b for t, b, _ in rows}
        if alt == assigned:
            identical += 1
        regrets.append(sum(Pver[t][alt[t]] for t in alt) - sum(Pver[t][assigned[t]] for t in assigned))
    return {"n_admissible_memberships": len(per_opt),
            "memberships_with_identical_slate": identical,
            "max_regret_expected_correct": round(max(regrets), 4),
            "mean_regret_expected_correct": round(sum(regrets) / len(regrets), 4),
            "regret_basis": "held-out: alternative slate chosen on the optimize archive, scored on "
                            "the independent verification archive"}


def sensitivity(pods_list, strength, n, seed, r1, c=0.0):
    """CRN D4 sensitivity: buckets whose membership changes across opponent-choice scenarios, with a
    shared Swiss outcome + shared match RNG per sim (isolates the choice effect from path noise).
    Averaged over the admissible pod structures when the membership is still unresolved."""
    n_each = max(1, n // len(pods_list))
    acc = None
    for k, pods in enumerate(pods_list):
        Pk = d4_sensitivity_crn(pods, strength, n=n_each, seed=seed + 1009 * k, r1_pairings=r1, c=c,
                                choices=D4_SCENARIOS)
        if acc is None:
            acc = {sc: {t: {b: 0.0 for b in BUCKETS} for t in Pk[sc]} for sc in D4_SCENARIOS}
        for sc in D4_SCENARIOS:
            for t in Pk[sc]:
                for b in BUCKETS:
                    acc[sc][t][b] += Pk[sc][t][b] / len(pods_list)
    Ps = acc
    slates = {sc: {b: {t for t, _ in assign(Ps[sc])[0][b]} for b in BUCKETS} for sc in D4_SCENARIOS}
    sensitive = {}
    base = slates["strategic"]
    for b in BUCKETS:
        union = set().union(*(slates[sc][b] for sc in D4_SCENARIOS))
        if any(slates[sc][b] != base[b] for sc in D4_SCENARIOS):
            sensitive[b] = sorted(union - base[b] | base[b] - union
                                  | {t for sc in D4_SCENARIOS for t in slates[sc][b] ^ base[b]})
    return Ps, sensitive


def build(teams, strength, pods_list, r1, draw_source, n, seed, mode, cutoff, strengths_source,
          train_maps, c=0.0, provenance=None, draw_state=None, rosters=None):
    """`pods_list` is every admissible pod structure: one entry when the membership is published,
    all round-1-compatible partitions when it is not (the slate is then marginalized over them)."""
    P, arch, per_struct, diag = _marginal_mc(pods_list, strength, n, seed, r1, c, return_diag=True)
    slate_h, exp_correct_h, rows_h = assign(P)
    asgA = {t: b for t, b, _ in rows_h}

    # verified expected-points refinement (decision layer; independent verification archive)
    _, arch_ver, per_ver, _ = _marginal_mc(pods_list, strength, n, seed + 424243, r1, c)
    assigned, refine = points_refinement(asgA, arch, arch_ver, seed + 7)

    slate = {b: sorted(((t, P[t][b]) for t in assigned if assigned[t] == b),
                       key=lambda x: -x[1]) for b in BUCKETS}
    rows = [(t, assigned[t], P[t][assigned[t]]) for t in assigned]
    exp_correct = sum(p for _, _, p in rows)
    refine["hungarian_expected_correct"] = round(exp_correct_h, 3)

    _, sensitive = sensitivity(pods_list, strength, n, seed, r1, c=c)
    agreement = (membership_agreement(per_struct, per_ver, assigned) if len(pods_list) > 1
                 else None)
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
        "status": {"official": "OFFICIAL",
                   "candidate": "SUBMISSION-GRADE CANDIDATE - NOT FINAL LOCK-DAY RUN"}.get(
                       mode, "DRY RUN - NOT OFFICIAL"),
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
        "draw_status": draw_state,
        "roster_audit": rosters,
        "pods": _pods_manifest(pods_list, agreement),
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
    if m["mode"] == "candidate":
        L += ["> SUBMISSION-GRADE CANDIDATE - the production answer as of the snapshot above, under "
              "the full official gates. NOT the final lock-day run: the exact in-client lock time, "
              "any published pod membership, any newer match data and any late roster change must "
              "still be re-checked on the day.", ""]
    elif m["mode"] != "official":
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
    g.add_argument("--candidate", action="store_true",
                   help="production run under the official gates, stamped and filed as a candidate")
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
    mode = "official" if a.official else ("candidate" if a.candidate else "dry-run")
    gated = a.official or a.candidate      # the candidate run answers to every official gate
    teams = load_teams()

    # ---- hard gate for the official slate ----
    if gated:
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
        stale = (cut_ts - uni_max) > STALE_SECS
        provenance["freshness_gate"] = {
            "stale_max_days": STALE_MAX_DAYS, "stale": bool(stale),
            "overridden": bool(stale and a.allow_stale),
            "note": ("override accepted: no professional match exists between the universe's latest "
                     "map and the cutoff; re-run scan_promatches to re-verify before trusting this"
                     if stale and a.allow_stale else None)}
        if gated and not a.allow_stale and stale:
            sys.exit(f"OFFICIAL RUN BLOCKED: universe latest map {_iso(uni_max)} is "
                     f"{provenance['universe_lag_days_before_cutoff']}d before cutoff {cut_iso}; "
                     f"refresh the data (or pass --allow-stale if there truly are no pre-lock games).")
        if gated and provenance["git_dirty"]:
            print("WARNING: repo is dirty (uncommitted changes) for an official run.", file=sys.stderr)
    else:
        strength = synthetic_strengths(teams)
        ssrc = "synthetic (non-predictive)"

    pods, r1, draw_source = resolve_draw(teams, a.draw, require_r1=gated)
    state = draw_status(a.draw)
    if pods is None:                                     # membership unresolved -> marginalize
        if r1 is None:
            sys.exit("draw: pod membership is unresolved, so round-1 pairings are required to "
                     "enumerate the admissible memberships")
        pods_list = admissible_two_pod_partitions(r1)
        print(f"pod membership unresolved: marginalizing over {len(pods_list)} memberships "
              f"compatible with the posted round 1", file=sys.stderr)
    else:
        pods_list = [pods]
    if provenance is not None:
        provenance["draw_sha256"] = _sha256(a.draw)      # recompute now the draw path is validated
    rosters = roster_audit(orgs=[t["team"] for t in teams])
    if gated and rosters["blocking"]:
        sys.exit("OFFICIAL RUN BLOCKED: unresolved roster audit for "
                 + ", ".join(rosters["blocking"])
                 + "\nresolve the lineup in data/ti2026/inputs/roster_events.csv (a CONFLICT must "
                   "never be silently decided in favour of the roster already in the model).")
    out = build(teams, strength, pods_list, r1, draw_source, a.sims, a.seed, mode, cut_iso, ssrc,
                train_maps, c=c, provenance=provenance, draw_state=state, rosters=rosters)

    # An unresolved membership may be marginalized, never asserted: the slate is only allowed to go
    # out OFFICIAL if no single admissible membership would have made a materially better one.
    agree = out["manifest"]["pods"].get("membership_agreement")
    if gated and agree and agree["max_regret_expected_correct"] > POD_MEMBERSHIP_REGRET_MAX:
        sys.exit("OFFICIAL RUN BLOCKED: the pod membership is unresolved and it matters -- the worst "
                 f"admissible membership beats the marginalized slate by "
                 f"{agree['max_regret_expected_correct']:.3f} expected correct (limit "
                 f"{POD_MEMBERSHIP_REGRET_MAX}). Wait for the published membership.")

    stamp = out["manifest"]["generated_at"].replace("-", "").replace(":", "").replace("+0000", "Z")
    outdir = a.out or {
        "official": os.path.join(REPO, "predictions", "ti2026", "group-stage"),
        "candidate": os.path.join(REPO, "predictions", "ti2026", "group-stage", "candidates"),
    }.get(mode, os.path.join(REPO, ".dryrun"))
    os.makedirs(outdir, exist_ok=True)
    stem = {"official": "ti15_group_prediction",
            "candidate": f"ti15_group_candidate_{stamp}"}.get(mode, "ti15_group_dryrun")
    with open(os.path.join(outdir, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, stem + ".md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(out))
    print(to_markdown(out))
    print(f"[{out['manifest']['status']}] wrote {stem}.json / .md to {os.path.relpath(outdir, REPO)}")


if __name__ == "__main__":
    main()
