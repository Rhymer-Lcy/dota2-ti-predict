"""Market anomaly check (DIAGNOSTIC ONLY -- never fused into the model, never a promotion input).

Pulls the live champion market, normalizes the outright prices into implied probabilities, and
compares its ORDER with the frozen B-bt ordering. The purpose is to surface disagreements a human
should look at before locking a slate -- not to adjust anything. There is no timestamped historical
odds series in this repo, so no market signal has ever been validated out of sample, and the frozen
gate keeps it out of production for exactly that reason.

Its second use this round is a repricing check: if a roster event were widely judged to change a
team's strength materially, the market would move on it. That is evidence about the market, not
about the team, and it is reported as such.

Run: python -m backtest2.market_check [--cutoff ISO]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti_predict.contest_rules import GROUP_LOCK_UTC
from ti_predict.predict_ti15 import bt_strengths_for, load_teams, parse_cutoff

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENT = "the-international-2026-winner-20260629212545745"
GAMMA = f"https://gamma-api.polymarket.com/events?slug={EVENT}"
UA = {"User-Agent": "dota2-ti-predict/0.1 (market-diagnostic)"}
# market label -> canonical organization (the event brands several teams differently)
MARKET_ALIASES = {"BoomBoys": "BetBoom Team", "1w Team": "Tundra Esports", "TEAM VISION": "PARIVISION"}


def fetch_market(url=GAMMA):
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45).read()
    d = json.loads(raw)
    ev = d[0] if isinstance(d, list) and d else d
    out = {}
    for m in ev.get("markets", []):
        label = m.get("groupItemTitle") or ""
        prices = m.get("outcomePrices")
        if not label or not prices:
            continue
        p = float(json.loads(prices)[0] if isinstance(prices, str) else prices[0])
        out[MARKET_ALIASES.get(label, label)] = p
    return out, ev.get("updatedAt")


def spearman(a, b):
    """Rank correlation between two {key: value} maps over their shared keys."""
    keys = sorted(set(a) & set(b))
    ra = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -a[k]))}
    rb = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -b[k]))}
    n = len(keys)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in keys)
    return 1 - 6 * d2 / (n * (n * n - 1)), ra, rb


def main():
    ap = argparse.ArgumentParser(description="market anomaly check (diagnostic only)")
    ap.add_argument("--cutoff", default=GROUP_LOCK_UTC)
    ap.add_argument("--out", default=os.path.join(REPO, "predictions", "ti2026", "group-stage",
                                                  "research"))
    a = ap.parse_args()
    rows = load_teams()
    cut_ts, cut_iso = parse_cutoff(a.cutoff)
    strength, _, _, _, _ = bt_strengths_for(rows, cut_ts)

    raw, updated = fetch_market()
    teams = [t["team"] for t in rows]
    missing = [t for t in teams if t not in raw]
    if missing:
        print("WARNING: market has no line for " + ", ".join(missing))
    tot = sum(raw[t] for t in teams if t in raw)
    implied = {t: raw[t] / tot for t in teams if t in raw}       # de-vigged by normalization only

    rho, r_model, r_market = spearman(strength, implied)
    diverge = sorted(((abs(r_model[t] - r_market[t]), t) for t in implied), reverse=True)[:5]
    out = {"status": "DIAGNOSTIC ONLY - not fused, not a promotion input",
           "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "market": "polymarket outright champion, normalized", "market_updated_at": updated,
           "cutoff": cut_iso, "spearman_rho_vs_bt": round(rho, 4),
           "implied": {t: round(implied[t], 4) for t in sorted(implied, key=lambda x: -implied[x])},
           "model_rank": r_model, "market_rank": r_market,
           "largest_rank_divergences": [{"team": t, "model_rank": r_model[t] + 1,
                                         "market_rank": r_market[t] + 1} for _, t in diverge]}
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "market_diagnostic.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"market updated {updated} | Spearman rho vs B-bt = {rho:.3f}")
    for t in sorted(implied, key=lambda x: -implied[x]):
        print(f"  {t:<18} market {implied[t]*100:5.2f}%  (market rank {r_market[t]+1:>2}, "
              f"model rank {r_model[t]+1:>2})")
    print("wrote " + os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
