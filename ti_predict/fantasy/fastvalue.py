"""The heavy layer, built once, and the fast value function built on top of it.

The split this module exists to make:

    HEAVY (build_cache)   read every player-map, apply the exact scoring coefficients, resolve
                          rosters, attach coach-title trigger indicators, index games into series
                          and series into event blocks. Runs in seconds, once, and then never again
                          for a reroll decision.

    FAST  (evaluate)      given an ordered banner, a team and a coach pair, return the expected
                          period score. One matrix-vector product, two segment reductions and a
                          closed-form expected maximum. Sub-millisecond, deterministic, no fetch.

WHY IT FACTORISES. The scoring chain is linear only up to the role-game score:

    player-game  P = (stat row . banner weights) * coach factor        <- linear in the weights
    role-game    R = mean of P over the role's players                 <- linear
    role-series  S = sum of the top two R in the series                <- NOT linear (a selection)
    role-period  T = max over the series in the period                 <- NOT linear (a maximum)

So a banner cannot be scored by a lookup table of per-stat values: changing one emblem can change
WHICH two games and WHICH series win. But everything before the first nonlinearity is a dot
product against a matrix that does not depend on the banner, and that matrix is what the heavy
layer caches. Every nonlinearity downstream is a cheap reduction over precomputed index arrays.

THE EXPECTED MAXIMUM IS CLOSED FORM, NOT SIMULATED. A period keeps the best of N series, and N is
random (2 to 6 in the Main Event bracket). For an empirical pool of m series scores sorted
ascending, drawing N with replacement gives P(max <= s_k) = (k/m)^N, so

    E[max of N] = sum_k s_k * ((k/m)^N - ((k-1)/m)^N)

exactly. No Monte Carlo, no seed, no convergence argument -- which is what makes the fast path both
fast and reproducible.

EVENT BLOCKS, NOT ONE POOL. Series are pooled per event and the per-event expected maxima are
averaged with equal weight. Flattening every event into one pool would let attendance act as weight
and would let a simulated period take its maximum from a different tournament; that defect was
found and fixed earlier in this project and the same estimator is used here. TI15 itself is one
more block, and the most relevant one.
"""
import csv
import json
import os
from collections import defaultdict

import numpy as np

from ti_predict.fantasy import build_roster_positions as brp

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUTS = os.path.join(REPO, "data", "ti2026", "inputs")
PROC = os.path.join(REPO, "data", "ti2026", "processed")
FPROC = os.path.join(PROC, "fantasy")

HIST_STATS = os.path.join(FPROC, "player_map_stats.csv")
HIST_EXTRAS = os.path.join(FPROC, "hist_player_map_extras.csv")
HIST_MATCH = os.path.join(FPROC, "match_extras.csv")
HIST_HEROES = os.path.join(FPROC, "player_map_heroes.csv")
TI15_STATS = os.path.join(FPROC, "ti15_player_map_stats.csv")
TI15_MATCH = os.path.join(FPROC, "ti15_match_extras.csv")
UNIVERSE = os.path.join(PROC, "universe_maps.csv")          # read only, never written
HERO_CATS = os.path.join(INPUTS, "fantasy", "hero_categories.json")

ROLES = ("core", "mid", "support")
PLAYERS_PER_ROLE = {"core": 2, "mid": 1, "support": 2}
# The TI series format. A series contributing fewer than two maps breaks the top-two step, and no
# TI series is a Bo1, so short series are training-window artefacts and are excluded.
MIN_SERIES_MAPS = 2

# helpstat index order, which is Valve's own Fantasy_Scoring enum order.
STATS = ("kills", "deaths", "creep_score", "gpm", "tower_kills", "roshan_kills",
         "teamfight_participation", "wards_placed", "camps_stacked", "runes_grabbed",
         "first_blood", "stuns", "smokes_used", "madstone", "watchers_taken",
         "lotuses_grabbed", "tormentor_kills", "courier_kills")
STAT_INDEX = {s: i for i, s in enumerate(STATS)}
COLOUR = {"kills": "red", "deaths": "red", "creep_score": "red", "gpm": "red",
          "tower_kills": "red", "madstone": "red",
          "wards_placed": "blue", "camps_stacked": "blue", "runes_grabbed": "blue",
          "watchers_taken": "blue", "smokes_used": "blue", "lotuses_grabbed": "blue",
          "roshan_kills": "green", "teamfight_participation": "green", "stuns": "green",
          "tormentor_kills": "green", "first_blood": "green", "courier_kills": "green"}
BY_COLOUR = {c: tuple(s for s in STATS if COLOUR[s] == c) for c in ("red", "blue", "green")}

COEF = {"kills": 107.0, "creep_score": 3.0, "gpm": 2.0, "tower_kills": 352.0, "madstone": 13.0,
        "wards_placed": 117.0, "camps_stacked": 234.0, "runes_grabbed": 141.0,
        "watchers_taken": 147.0, "smokes_used": 293.0, "lotuses_grabbed": 176.0,
        "roshan_kills": 1172.0, "stuns": 10.0, "tormentor_kills": 879.0, "first_blood": 1934.0,
        "courier_kills": 703.0}
DEATH_CREDIT, DEATH_DEBIT = 1950.0, 195.0
TFP_MAX = 2124.0

# Measured, not assumed. Three stats have no per-player value anywhere in the OpenDota payload:
#   madstone         `neutral_tokens_log` is an empty list on all 4785 historical player-maps AND
#                    on every TI15 player-map. That is a missing field, NOT a zero.
#   watchers_taken   no key anywhere in the match object; a full recursive key scan finds nothing.
#   lotuses_grabbed  same.
# They are excluded from the scored subset and handled by explicit bounds instead. Tormentor is NOT
# on this list any more: objectives[].CHAT_MESSAGE_MINIBOSS_KILL carries player_slot, so it is
# attributable, and the earlier "attribution unverified" grade is withdrawn.
UNOBSERVABLE = ("madstone", "watchers_taken", "lotuses_grabbed")
OBSERVABLE = tuple(s for s in STATS if s not in UNOBSERVABLE)

# Coach titles. Bonus is a percentage of the FINAL game score, applied when the condition holds.
PREFIX_BONUS = {"Crimson": 0.06, "Cerulean": 0.11, "Emerald": 0.06, "Royal": 0.10,
                "Golden": 0.08, "Elemental": 0.08, "Otherworldly": 0.07, "Heroic": 0.09}
SUFFIX_BONUS = {"the Tormented": 0.23, "the Flayed Twins Acolyte": 0.09, "the Patient": 0.23,
                "the Underdog": 0.06, "the Decisive": 0.24, "the Clutch": 0.16,
                "the Lucky": 0.21, "the Cruel": 0.13}
# Which prefixes a hero-category table can actually evaluate. The community table carries red,
# blue, green, undead and aquatic flags only.
#   exact       the flag IS the client's condition
#   lower_bound the flag is a strict SUBSET of the condition, so the score is a lower bound
#   untabled    no flag at all; the prefix cannot be scored and is reported as such
PREFIX_FLAG = {"Crimson": ("isred", "exact"), "Cerulean": ("isblue", "exact"),
               "Emerald": ("isgreen", "exact"), "Elemental": ("isaquatic", "lower_bound"),
               "Otherworldly": ("isundead", "lower_bound"),
               "Royal": (None, "untabled"), "Golden": (None, "untabled"),
               "Heroic": (None, "untabled")}
# Fountain deaths were bounded at 0.0000-0.0016 at any fountain-sized radius by an earlier round,
# far below anything that could matter, and no field attributes a death to a fountain location.
SUFFIX_UNSCORED = ("the Cruel",)


def _f(v, default=None):
    if v in ("", "None", None):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def roster(path=None):
    """organization -> {role: [account_id, ...]} for ACTIVE players only, with a shape check."""
    out = defaultdict(lambda: defaultdict(list))
    for r in _rows(path or os.path.join(INPUTS, "fantasy", "roster_positions.csv")):
        if str(r["active"]).lower() != "true":
            continue
        out[r["organization"]][r["fantasy_role"]].append(int(r["account_id"]))
    bad = {}
    for org, roles in out.items():
        shape = {k: len(roles.get(k, [])) for k in ROLES}
        if shape != PLAYERS_PER_ROLE:
            bad[org] = shape
    return {o: dict(v) for o, v in out.items()}, bad


def hero_flags(path=None):
    with open(path or HERO_CATS, encoding="utf-8") as fh:
        return {int(k): v for k, v in json.load(fh).items()}


def _series_map():
    """match_id -> (leagueid, series_id) for the historical window, read from the frozen universe.

    Read only. The bracket pipeline owns this file; nothing here writes to it.
    """
    out = {}
    for r in _rows(UNIVERSE):
        out[int(r["match_id"])] = (r["leagueid"], r["series_id"] or f"m{r['match_id']}")
    return out


def stat_vector(row, tormentor=None, runes_key="rune_pickups"):
    """Per-stat point contribution of ONE player-game at multiplier 1.0.

    Unobservable stats are left as NaN, never zero: a missing field and a real zero are different
    facts and collapsing them is exactly how an unscoreable slot silently becomes a free one.
    """
    v = np.full(len(STATS), np.nan)
    g = lambda k: _f(row.get(k))                                                    # noqa: E731
    kills, deaths = g("kills"), g("deaths")
    lh, dn = g("last_hits"), g("denies")
    if kills is not None:
        v[STAT_INDEX["kills"]] = COEF["kills"] * kills
    if deaths is not None:
        v[STAT_INDEX["deaths"]] = DEATH_CREDIT - DEATH_DEBIT * deaths
    if lh is not None and dn is not None:
        v[STAT_INDEX["creep_score"]] = COEF["creep_score"] * (lh + dn)
    for stat, key in (("gpm", "gold_per_min"), ("tower_kills", "towers_killed"),
                      ("roshan_kills", "roshans_killed"), ("wards_placed", "obs_placed"),
                      ("camps_stacked", "camps_stacked"), ("stuns", "stuns"),
                      ("first_blood", "firstblood_claimed"), ("courier_kills", "courier_kills"),
                      ("smokes_used", "smokes_used")):
        x = g(key)
        if x is not None:
            v[STAT_INDEX[stat]] = COEF[stat] * x
    r = g(runes_key)
    if r is not None:
        v[STAT_INDEX["runes_grabbed"]] = COEF["runes_grabbed"] * r
    tfp = g("teamfight_participation")
    if tfp is not None:
        v[STAT_INDEX["teamfight_participation"]] = TFP_MAX * tfp
    t = tormentor if tormentor is not None else g("tormentor_kills")
    if t is not None:
        v[STAT_INDEX["tormentor_kills"]] = COEF["tormentor_kills"] * t
    return v


def _suffix_row(match, is_last_possible_game, player_lost):
    """Which suffix conditions this player-game satisfies."""
    fb = _f(match.get("first_blood_time"))
    dur = _f(match.get("duration"))
    torm = _f(match.get("all_tormentor_deaths"), _f(match.get("any_miniboss_death"), 0.0))
    out = {}
    out["the Tormented"] = bool(torm and torm > 0)
    out["the Flayed Twins Acolyte"] = bool(fb is not None and fb < 0)
    out["the Patient"] = bool(fb is not None and fb > 600)
    out["the Underdog"] = bool(player_lost)
    out["the Decisive"] = bool(dur is not None and dur < 1500)
    out["the Clutch"] = bool(is_last_possible_game)
    out["the Lucky"] = bool(dur is not None and int(dur) % 10 == 8)
    out["the Cruel"] = False        # bounded at <=0.0016; no field attributes a fountain death
    return out


def build_cache(orgs=None, runes_key="rune_pickups"):
    """The heavy layer. One pass over every player-map, producing per (org, role) matrices."""
    roster_map, bad_shape = roster()
    if orgs:
        roster_map = {o: v for o, v in roster_map.items() if o in orgs}
    flags = hero_flags()
    inactive = set(brp.inactive_accounts())
    smap = _series_map()

    hist_extra = {}
    for r in _rows(HIST_EXTRAS):
        if r["account_id"]:
            hist_extra[(int(r["match_id"]), int(r["account_id"]))] = r
    hist_hero = {(int(r["match_id"]), int(r["account_id"])): int(r["hero_id"])
                 for r in _rows(HIST_HEROES) if r.get("hero_id")}
    hist_match = {int(r["match_id"]): r for r in _rows(HIST_MATCH)}
    ti15_match = {int(r["match_id"]): r for r in _rows(TI15_MATCH)}

    # (event, series) -> {match_id -> [(org, role, account, statvec, hero_id, lost, source)]}
    pool = defaultdict(lambda: defaultdict(list))
    acct_role = {}
    for org, roles in roster_map.items():
        for role, accts in roles.items():
            for a in accts:
                acct_role[a] = (org, role)

    def ingest(rows, source):
        for r in rows:
            if r.get("parsed") not in ("1", 1):
                continue
            acct = int(r["account_id"])
            if acct in inactive or acct not in acct_role:
                continue
            org, role = acct_role[acct]
            mid = int(r["match_id"])
            if source == "history":
                if mid not in smap:
                    continue
                event, series = smap[mid]
                ex = hist_extra.get((mid, acct))
                torm = _f(ex.get("tormentor_kills")) if ex else None
                rk = r.get("rune_pickups")
                if runes_key == "runes_total" and ex is not None:
                    rk = ex.get("runes_total")
                row = dict(r)
                row["rune_pickups"] = rk
                hero = hist_hero.get((mid, acct))
                match = hist_match.get(mid, {})
            else:
                event, series = r["leagueid"], r["series_id"] or f"m{mid}"
                torm = _f(r.get("tormentor_kills"))
                row = dict(r)
                if runes_key == "runes_total":
                    row["rune_pickups"] = r.get("runes_total")
                hero = int(r["hero_id"]) if r.get("hero_id") else None
                match = ti15_match.get(mid, {})
            vec = stat_vector(row, tormentor=torm)
            lost = not bool(int(_f(r.get("win"), 0)))
            pool[(event, str(series))][mid].append(
                {"org": org, "role": role, "account": acct, "vec": vec, "hero": hero,
                 "lost": lost, "match": match, "source": source})

    ingest(_rows(HIST_STATS), "history")
    ingest(_rows(TI15_STATS), "ti15")

    cache = {}
    coverage = defaultdict(lambda: {"series": 0, "games": 0, "player_games": 0, "events": set()})
    for (event, series), games in sorted(pool.items()):
        mids = sorted(games)
        if len(mids) < MIN_SERIES_MAPS:
            continue
        last_mid = mids[-1]
        # "the last possible match of a series" -- the Clutch condition. Reading it as "the final
        # map of a series with at least three maps" would be wrong: a Bo5 that ends 3-0 also has
        # three maps, and its third map was not the last possible one. The format-free test is the
        # final MARGIN: a series decided on its last possible map ends one map apart (2-1, 3-2),
        # and one decided early does not (2-0, 3-1, 3-0). The two teams' records are complements,
        # so the margin can be read off either one.
        maps_won = defaultdict(set)
        maps_lost = defaultdict(set)
        for mid in mids:
            for e in games[mid]:
                (maps_lost if e["lost"] else maps_won)[e["org"]].add(mid)
        went_the_distance = False
        for org in maps_won.keys() | maps_lost.keys():
            went_the_distance = abs(len(maps_won[org]) - len(maps_lost[org])) == 1
            break
        for mid in mids:
            by_role = defaultdict(list)
            for e in games[mid]:
                by_role[(e["org"], e["role"])].append(e)
            for (org, role), entries in by_role.items():
                if len(entries) != PLAYERS_PER_ROLE[role]:
                    continue        # fail closed: an incomplete role pair is not a role-game
                key = (org, role)
                c = cache.setdefault(key, {"X": [], "game": [], "series": [], "event": [],
                                           "prefix": [], "suffix": [], "n_players": []})
                for e in entries:
                    c["X"].append(e["vec"])
                    c["game"].append((event, series, mid))
                    c["series"].append((event, series))
                    c["event"].append(event)
                    hf = flags.get(e["hero"], {})
                    c["prefix"].append([bool(hf.get(PREFIX_FLAG[p][0]))
                                        if PREFIX_FLAG[p][0] else False for p in PREFIX_BONUS])
                    sx = _suffix_row(e["match"], mid == last_mid and went_the_distance, e["lost"])
                    c["suffix"].append([sx[s] for s in SUFFIX_BONUS])
                    c["n_players"].append(PLAYERS_PER_ROLE[role])
                cv = coverage[key]
                cv["games"] += 1
                cv["player_games"] += len(entries)
                cv["events"].add(event)
        for (org, role) in {(e["org"], e["role"]) for g in games.values() for e in g}:
            coverage[(org, role)]["series"] += 1

    out = {}
    for key, c in cache.items():
        X = np.array(c["X"], dtype=float)
        # Per-stat coverage over this block's player-games. A NaN is a MISSING VALUE, never a zero,
        # and np.nansum would quietly turn it into one -- so coverage is measured here and asserted
        # in period_score before any weight is put on a column.
        col_cov = 1.0 - np.isnan(X).mean(axis=0)
        gid, g_uni = _factorize(c["game"])
        sid, s_uni = _factorize(c["series"])
        eid, e_uni = _factorize(c["event"])
        out[key] = {
            "X": X, "game": gid, "n_games": len(g_uni),
            "series": sid, "n_series": len(s_uni),
            "event": eid, "n_events": len(e_uni), "events": [e[0] for e in e_uni],
            "prefix": np.array(c["prefix"], dtype=bool),
            "suffix": np.array(c["suffix"], dtype=bool),
            "n_players": np.array(c["n_players"], dtype=float),
            "col_coverage": col_cov,
            # per-game -> series and per-series -> event maps, built once
            "game_series": _first_of(gid, sid), "series_event": _first_of(sid, eid),
        }
    cov = {f"{o}|{r}": {"series": v["series"], "games": v["games"],
                        "player_games": v["player_games"], "events": sorted(v["events"])}
           for (o, r), v in coverage.items()}
    return {"cache": out, "coverage": cov, "bad_roster_shape": bad_shape,
            "runes_key": runes_key}


def _factorize(keys):
    uni, idx = {}, []
    order = []
    for k in keys:
        kk = k if isinstance(k, tuple) else (k,)
        if kk not in uni:
            uni[kk] = len(uni)
            order.append(kk)
        idx.append(uni[kk])
    return np.array(idx, dtype=np.int64), order


def _first_of(child, parent):
    """For each distinct child index, the parent index it belongs to."""
    n = int(child.max()) + 1 if len(child) else 0
    out = np.full(n, -1, dtype=np.int64)
    out[child] = parent
    return out


# --------------------------------------------------------------------------------------------
# FAST PATH
# --------------------------------------------------------------------------------------------

def expected_max(sorted_pool, n):
    """E[max of n iid draws with replacement] from an empirical pool. Closed form, exact."""
    m = len(sorted_pool)
    if m == 0:
        return np.nan
    k = np.arange(1, m + 1, dtype=float)
    w = (k / m) ** n - ((k - 1) / m) ** n
    return float(sorted_pool @ w)


def assert_scoreable(entry, w, tol=1e-9):
    """Refuse to put weight on a stat this block does not fully observe.

    Without this, np.nansum reads a missing value as a zero, and a stat that is merely unfetched
    becomes a stat the team never produced. Fail closed instead: the caller must either complete
    the data or zero the weight and declare the slot unscored.
    """
    bad = [(STATS[i], round(float(entry["col_coverage"][i]), 4))
           for i in range(len(STATS)) if w[i] > tol and entry["col_coverage"][i] < 1.0 - tol]
    if bad:
        raise ValueError(
            "weight placed on stat(s) this block does not fully observe: "
            + ", ".join(f"{s} coverage {c}" for s, c in bad)
            + ". A missing value is not a zero; complete the data or declare the slot unscored.")


def series_scores(entry, w, prefix=None, suffix=None, stacking="additive"):
    """Per-series role scores (top two games summed), plus the event each series belongs to."""
    assert_scoreable(entry, w)
    X = entry["X"]
    s = np.nansum(X * w[None, :], axis=1)
    if prefix is not None or suffix is not None:
        pb = PREFIX_BONUS[prefix] * entry["prefix"][:, list(PREFIX_BONUS).index(prefix)] \
            if prefix else 0.0
        sb = SUFFIX_BONUS[suffix] * entry["suffix"][:, list(SUFFIX_BONUS).index(suffix)] \
            if suffix else 0.0
        s = s * ((1.0 + pb) * (1.0 + sb) if stacking == "multiplicative" else 1.0 + pb + sb)
    # role-game score = arithmetic mean over the role's players in that game
    tot = np.bincount(entry["game"], weights=s, minlength=entry["n_games"])
    cnt = np.bincount(entry["game"], minlength=entry["n_games"])
    R = tot / np.maximum(cnt, 1)
    # series score = sum of the top TWO game scores in the series
    order = np.argsort(-R)
    gs = entry["game_series"]
    rank = np.zeros(entry["n_games"], dtype=np.int64)
    seen = defaultdict(int)
    for g in order:
        sidx = gs[g]
        rank[g] = seen[sidx]
        seen[sidx] += 1
    keep = rank < 2
    S = np.bincount(gs[keep], weights=R[keep], minlength=entry["n_series"])
    return S, entry["series_event"]


def expected_max_weighted(values, weights, n):
    """E[max of n draws] from a WEIGHTED empirical distribution. Same closed form, general weights.

    values must be sorted ascending and aligned with weights; weights need not be normalised.
    """
    w = np.asarray(weights, dtype=float)
    F = np.cumsum(w)
    F = F / F[-1]
    Fprev = np.concatenate(([0.0], F[:-1]))
    return float(np.asarray(values, dtype=float) @ (F ** n - Fprev ** n))


# Shrinkage constant, declared before any arm was scored and never tuned on an outcome. A team's
# per-EVENT series pool is small -- typically four to twelve series -- and E[max of six draws] from
# a pool that size is dominated by its own largest element, i.e. by one lucky series. Each pool is
# therefore mixed with the pool of every team in the SAME event, which controls for patch, format
# and field strength while dragging a thin team towards the field. K is the pool size at which a
# team's own distribution gets equal weight with the field's.
SHRINK_K = 5.0


def role_pools(built, role, w, teams, prefix=None, suffix=None, stacking="additive"):
    """Per-team, per-event series-score pools plus the pooled field pool for each event.

    Built once per (role, banner, coach) and reused across every candidate team, which is what
    keeps the shrunk estimator as cheap as the unshrunk one.
    """
    per_team, by_event = {}, defaultdict(list)
    for t in teams:
        entry = built["cache"].get((t, role))
        if entry is None:
            continue
        S, sev = series_scores(entry, w, prefix, suffix, stacking)
        pools = {}
        for e in range(entry["n_events"]):
            vals = S[sev == e]
            if len(vals):
                key = entry["events"][e]
                pools[key] = np.sort(vals)
                by_event[key].append(vals)
        per_team[t] = pools
    # The prior weights each TEAM equally, not each series. Concatenating raw pools would
    # let a team that happened to play more series in an event dominate the prior every
    # other team is shrunk towards, which is attendance acting as weight -- the same
    # defect this project already fixed once at the event level.
    field = {}
    for key, arrays in by_event.items():
        vals = np.concatenate(arrays)
        wts = np.concatenate([np.full(len(a), 1.0 / (len(a) * len(arrays)))
                              for a in arrays])
        order = np.argsort(vals, kind="stable")
        field[key] = (vals[order], wts[order])
    return per_team, field


def period_score_shrunk(pools, field, exposure, k=SHRINK_K):
    """Expected period score with each per-event pool shrunk towards that event's field pool.

    The mixture is on the DISTRIBUTION, not on a summary statistic: the shrunk CDF is
    lam * F_team + (1 - lam) * F_field with lam = m / (m + k), and E[max of N] is taken against it
    in the same closed form. k = 0 reproduces the unshrunk estimator exactly, which is how the
    sensitivity is run.
    """
    if not pools:
        return np.nan
    total = 0.0
    for n, prob in exposure.items():
        vals = []
        for ev, pool in pools.items():
            vals.append(_emax_shrunk(pool, field.get(ev), int(n), k))
        total += prob * float(np.mean(vals))
    return total


def period_score(entry, w, exposure, prefix=None, suffix=None, stacking="additive"):
    """Unshrunk expected period score: E over series count N of the mean per-event E[max of N]."""
    S, sev = series_scores(entry, w, prefix, suffix, stacking)
    pools = []
    for e in range(entry["n_events"]):
        p = np.sort(S[sev == e])
        if len(p):
            pools.append(p)
    if not pools:
        return np.nan
    total = 0.0
    for n, prob in exposure.items():
        total += prob * float(np.mean([expected_max(p, int(n)) for p in pools]))
    return total


def banner_weights(slots, drop_unobservable=True):
    """An ordered emblem banner -> the length-18 weight vector the fast path consumes.

    Slots carrying a stat with no public per-player source are zeroed by default and reported
    separately by `unscored_weight`. Zeroing the WEIGHT is not the same as zeroing the STAT: it
    says the model declines to score that slot, which is why every ranking is accompanied by the
    unscored fraction and by an exact breakpoint for how much it would have to be worth to matter.
    """
    w = np.zeros(len(STATS))
    for s in slots:
        if drop_unobservable and s["stat"] in UNOBSERVABLE:
            continue
        w[STAT_INDEX[s["stat"]]] += s["multiplier"]
    return w


def unscored_weight(slots):
    """How much of this banner's multiplier sits on a stat with no public per-player source."""
    tot = sum(s["multiplier"] for s in slots)
    lost = sum(s["multiplier"] for s in slots if s["stat"] in UNOBSERVABLE)
    return {"total_multiplier": round(tot, 4), "unscored_multiplier": round(lost, 4),
            "unscored_fraction": round(lost / tot, 4) if tot else None,
            "unscored_stats": sorted({s["stat"] for s in slots if s["stat"] in UNOBSERVABLE})}


def _emax_shrunk(pool, field, n, k):
    """E[max of n] from one pool, shrunk towards the event's field pool.

    field is (values, weights) with the weights already team-balanced; k <= 0 or a
    missing field gives the unshrunk estimator exactly.
    """
    if field is None or k <= 0 or not len(pool):
        return expected_max(pool, n)
    fv_, fw = field
    m = len(pool)
    lam = m / (m + k)
    values = np.concatenate([pool, fv_])
    weights = np.concatenate([np.full(m, lam / m), (1.0 - lam) * fw / fw.sum()])
    order = np.argsort(values, kind="stable")
    return expected_max_weighted(values[order], weights[order], n)


def period_bootstrap(entry, w, exposure, prefix=None, suffix=None, stacking="additive",
                     draws=400, seed=20260817, field=None, k=SHRINK_K):
    """Hierarchical bootstrap of the period score: resample event blocks, then series within.

    Two levels because there are two sources of variation and they are not the same size. Within an
    event, the series is the sampling unit. ACROSS events the whole tournament is the unit -- a
    different field, a different patch, a different bracket -- and with only five or six event
    blocks that outer level has very few distinct values to draw from, so the interval it produces
    is a coarse indication of between-tournament variation, not a precise interval. Stated here
    rather than implied by a tight-looking number.
    """
    S, sev = series_scores(entry, w, prefix, suffix, stacking)
    keys = [entry["events"][e] for e in range(entry["n_events"])]
    pools = [(keys[e], S[sev == e]) for e in range(entry["n_events"])]
    pools = [(k, p) for k, p in pools if len(p)]
    if not pools:
        return np.array([])
    rng = np.random.default_rng(seed)
    items = list(exposure.items())
    field = field or {}
    out = np.empty(draws)
    for b in range(draws):
        pick = rng.integers(0, len(pools), len(pools))
        vals = []
        for i in pick:
            key, p = pools[i]
            r = np.sort(rng.choice(p, size=len(p), replace=True))
            vals.append(sum(prob * _emax_shrunk(r, field.get(key), int(n), k)
                            for n, prob in items))
        out[b] = float(np.mean(vals))
    return out


def score(built, role, w, team, exposure, prefix=None, suffix=None, stacking="additive",
          teams=None, k=SHRINK_K):
    """THE production estimator. One call, one number: the shrunk expected period score.

    Every table in this module and every decision in the driver goes through here, so the estimator
    cannot differ between the headline ranking and the marginal that justifies a reroll.
    """
    teams = teams or sorted({key[0] for key in built["cache"] if key[1] == role})
    per_team, field = role_pools(built, role, w, teams, prefix, suffix, stacking)
    return period_score_shrunk(per_team.get(team, {}), field, exposure, k)


def rank_teams(built, role, slots, exposure_by_team, prefix=None, suffix=None,
               stacking="additive", teams=None, draws=400, seed=20260817, k=SHRINK_K):
    """Every candidate team scored on THIS banner. The banner is fixed; only the team varies."""
    w = banner_weights(slots)
    teams = sorted(teams or {key[0] for key in built["cache"]})
    per_team, field = role_pools(built, role, w, teams, prefix, suffix, stacking)
    rows = []
    for team in teams:
        entry = built["cache"].get((team, role))
        if entry is None:
            continue
        exp = exposure_by_team.get(team)
        if not exp:
            continue
        point = period_score_shrunk(per_team.get(team, {}), field, exp, k)
        unshrunk = period_score(entry, w, exp, prefix, suffix, stacking)
        bs = period_bootstrap(entry, w, exp, prefix, suffix, stacking, draws, seed,
                              field=field, k=k)
        rows.append({"organization": team, "expected_period_score": round(float(point), 1),
                     "unshrunk_period_score": round(float(unshrunk), 1),
                     "shrinkage_k": k,
                     "bootstrap_mean": round(float(bs.mean()), 1) if len(bs) else None,
                     "bootstrap_sd": round(float(bs.std(ddof=1)), 1) if len(bs) > 1 else None,
                     "ci90": [round(float(np.percentile(bs, 5)), 1),
                              round(float(np.percentile(bs, 95)), 1)] if len(bs) else None,
                     "_bs": bs,
                     "expected_series": round(sum(int(n) * p for n, p in exp.items()), 3),
                     "n_series_observed": int(entry["n_series"]),
                     "n_events": int(entry["n_events"])})
    rows.sort(key=lambda r: -r["expected_period_score"])
    best = rows[0]["expected_period_score"] if rows else None
    B = np.vstack([r["_bs"] for r in rows]) if rows and len(rows[0]["_bs"]) else None
    win = (B == B.max(axis=0)).mean(axis=1) if B is not None else None
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["regret_to_best"] = round(best - r["expected_period_score"], 1)
        r["regret_pct"] = round(100.0 * (best - r["expected_period_score"]) / best, 2) \
            if best else None
        r["p_is_best_bootstrap"] = round(float(win[i]), 4) if win is not None else None
        del r["_bs"]
    return rows


def stat_value_table(built, role, slots, team, exposure, prefix=None, suffix=None,
                     stacking="additive", teams=None):
    """For every legal stat of each colour: what it is worth in this slot, on this team.

    Reported as the exact period score with that stat substituted in, so the selection effects at
    the top-two and best-series steps are honoured rather than linearised away.
    """
    def sc(sl):
        return float(score(built, role, banner_weights(sl), team, exposure, prefix,
                           suffix, stacking, teams))
    base = sc(slots)
    out = {}
    for i, s in enumerate(slots):
        colour = s["colour"]
        cur = s["stat"]
        held = {x["stat"] for j, x in enumerate(slots) if j != i}
        rows = []
        for cand in BY_COLOUR[colour]:
            trial = [dict(x) for x in slots]
            trial[i]["stat"] = cand
            v = sc(trial)
            bump = [dict(x) for x in trial]
            bump[i]["multiplier"] = bump[i]["multiplier"] + 0.10
            v10 = sc(bump)
            rows.append({"stat": cand, "colour": colour,
                         "legal_here": cand not in held,   # no banner carries a duplicate stat
                         "observable": cand not in UNOBSERVABLE,
                         "period_score": round(float(v), 1),
                         "delta_vs_current": round(float(v - base), 1),
                         "value_per_plus_10pct": round(float(v10 - v), 1),
                         "is_current": cand == cur})
        rows.sort(key=lambda r: -r["period_score"])
        out[f"slot{i + 1}_{colour}"] = {"current_stat": cur,
                                        "current_multiplier": s["multiplier"], "options": rows}
    return {"base_period_score": round(float(base), 1), "slots": out}


def quality_trait_tables(built, role, slots, team, exposure, prefix=None, suffix=None,
                         stacking="additive", teams=None):
    """Exact marginal value of every tier and every trait, in every slot.

    Both recompute the WHOLE trait network, because a quality change can switch Fractal on or off
    for the entire banner and a trait change moves both neighbours. Nothing here is a per-slot
    lookup summed up afterwards.
    """
    from ti_predict.fantasy import banner_model as bm
    spec = [{"quality_tier": s["quality_tier"], "trait": s["trait"]} for s in slots]
    stats = [s["stat"] for s in slots]

    def sc(sp):
        ev = bm.evaluate(sp)
        trial = [{"slot": i + 1, "stat": stats[i], "colour": slots[i]["colour"],
                  "multiplier": ev[i]["multiplier"]} for i in range(len(sp))]
        return float(score(built, role, banner_weights(trial), team, exposure, prefix,
                           suffix, stacking, teams)), \
            [round(e["multiplier"], 4) for e in ev]

    base, base_mult = sc(spec)
    tiers = ("I", "II", "III", "IV", "V")
    q_out, t_out = {}, {}
    for i in range(len(slots)):
        rows = []
        for t in tiers:
            sp = [dict(x) for x in spec]
            sp[i]["quality_tier"] = t
            v, mult = sc(sp)
            rows.append({"tier": t, "period_score": round(v, 1),
                         "delta_vs_current": round(v - base, 1),
                         "resulting_multipliers": mult,
                         "is_current": t == spec[i]["quality_tier"]})
        q_out[f"slot{i + 1}"] = {"stat": stats[i], "current_tier": spec[i]["quality_tier"],
                                 "options": rows}
        rows = []
        for name in bm.TRAITS:
            sp = [dict(x) for x in spec]
            sp[i]["trait"] = name
            v, mult = sc(sp)
            rows.append({"trait": name, "period_score": round(v, 1),
                         "delta_vs_current": round(v - base, 1),
                         "resulting_multipliers": mult,
                         "is_current": name == spec[i]["trait"]})
        rows.sort(key=lambda r: -r["period_score"])
        t_out[f"slot{i + 1}"] = {"stat": stats[i], "current_trait": spec[i]["trait"],
                                 "options": rows}
    return {"base_period_score": round(base, 1), "base_multipliers": base_mult,
            "quality": q_out, "trait": t_out}


def coach_table(built, role, slots, team, exposure, stacking="additive", teams=None):
    """Every legal prefix x suffix pair, scored exactly. Changing a title costs no token."""
    w = banner_weights(slots)
    out = []
    for p in list(PREFIX_BONUS) + [None]:
        for s in list(SUFFIX_BONUS) + [None]:
            v = score(built, role, w, team, exposure, p, s, stacking, teams)
            out.append({"prefix": p, "suffix": s, "period_score": round(float(v), 1),
                        "prefix_evidence": PREFIX_FLAG[p][1] if p else "none",
                        "suffix_scoreable": (s not in SUFFIX_UNSCORED) if s else True})
    out.sort(key=lambda r: -r["period_score"])
    return out


def unobservable_breakpoints(slots, ranking):
    """How much MORE of an unscored stat the runner-up would need to overtake the leader.

    Exact, not simulated. Adding a constant k points per player-game to one team shifts its
    role-game score by k, its top-two series score by 2k and its best-series period score by 2k --
    the selection at both nonlinear steps is unchanged, because every one of that team's games
    moves together. So the flip condition is simply 2 * multiplier * coefficient * delta > gap.
    """
    un = [s for s in slots if s["stat"] in UNOBSERVABLE]
    if not un or len(ranking) < 2:
        return {"unscored_slots": [], "note": "no unscored stat on this banner"}
    lead = ranking[0]
    out = []
    for s in un:
        c = COEF[s["stat"]]
        per_unit = 2.0 * s["multiplier"] * c
        rows = [{"challenger": r["organization"],
                 "gap_points": round(lead["expected_period_score"]
                                     - r["expected_period_score"], 1),
                 "extra_per_player_game_needed":
                     round((lead["expected_period_score"] - r["expected_period_score"])
                           / per_unit, 3)}
                for r in ranking[1:4]]
        out.append({"slot": s["slot"], "stat": s["stat"], "multiplier": s["multiplier"],
                    "coefficient": c, "points_per_extra_unit_per_player_game": round(per_unit, 1),
                    "challengers": rows})
    return {"unscored_slots": out,
            "reading": "a challenger overtakes the leader only if its players average at least "
                       "this many MORE of that stat per player-game than the leader's do. The "
                       "stat has no public per-player source, so the sign of that difference is "
                       "not established either way."}
