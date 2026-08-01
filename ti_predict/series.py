"""Series-score distributions for esports best-of-N (odd N), from a single-map win prob.

A Dota 2 series is first-to-k in a Best-of-(2k-1): Bo1 -> k=1, Bo3 -> k=2, Bo5 -> k=3.
Assuming maps are i.i.d. with the favourite winning each map with probability p (a deliberate
simplification: it ignores draft adaptation, side selection and momentum), the probability of
the favourite closing the series exactly k:j (j losses, 0 <= j < k) is

    P(k:j) = C(k-1+j, j) * p**k * (1-p)**j

because the deciding map is a win and the preceding (k-1+j) maps hold exactly j losses. The
opponent's mirror scores j:k use (1-p). This is the esports analogue of the football "比分"
market and feeds the Swiss/bracket simulators.

Run `python -m ti_predict.series` for the self-test.
"""
from math import comb


def _k(best_of):
    if best_of < 1 or best_of % 2 == 0:
        raise ValueError(f"best_of must be a positive odd number, got {best_of}")
    return (best_of + 1) // 2


def series_score_distribution(p, best_of):
    """{"wins:losses": prob} over all terminal scores (favourite's perspective), summing to 1.

    p = favourite per-map win probability in [0,1]. Bo3 keys: "2:0","2:1","1:2","0:2".
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be in [0,1], got {p}")
    k = _k(best_of)
    dist = {}
    for j in range(k):                       # favourite wins k:j
        dist[f"{k}:{j}"] = comb(k - 1 + j, j) * p ** k * (1 - p) ** j
    for j in range(k):                       # favourite loses j:k
        dist[f"{j}:{k}"] = comb(k - 1 + j, j) * (1 - p) ** k * p ** j
    return dist


def series_win_prob(p, best_of):
    """Probability the favourite (per-map prob p) wins the Best-of-N series."""
    k = _k(best_of)
    return sum(comb(k - 1 + j, j) * p ** k * (1 - p) ** j for j in range(k))


def map_prob_for_series_prob(target_series_prob, best_of, tol=1e-12):
    """Invert series_win_prob: the per-map p giving a target series win prob (bisection).

    Lets you back a per-map edge out of a market series price, or vice-versa.
    """
    if not 0.0 <= target_series_prob <= 1.0:
        raise ValueError(f"target must be in [0,1], got {target_series_prob}")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if series_win_prob(mid, best_of) < target_series_prob:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


if __name__ == "__main__":
    # normalization + win-prob consistency across formats and probabilities
    for bo in (1, 3, 5, 7):
        for p in (0.0, 0.2, 0.5, 0.73, 1.0):
            d = series_score_distribution(p, bo)
            assert abs(sum(d.values()) - 1.0) < 1e-9, (bo, p)
            win_mass = sum(v for s, v in d.items()
                           if int(s.split(":")[0]) > int(s.split(":")[1]))
            assert abs(win_mass - series_win_prob(p, bo)) < 1e-9, (bo, p)
    # Bo3 / Bo5 closed forms
    p = 0.6
    d3 = series_score_distribution(p, 3)
    assert abs(d3["2:0"] - p ** 2) < 1e-12
    assert abs(d3["2:1"] - 2 * p ** 2 * (1 - p)) < 1e-12
    assert abs(series_win_prob(p, 3) - p ** 2 * (3 - 2 * p)) < 1e-12
    d5 = series_score_distribution(p, 5)
    assert abs(d5["3:0"] - p ** 3) < 1e-12
    assert abs(d5["3:1"] - 3 * p ** 3 * (1 - p)) < 1e-12
    assert abs(d5["3:2"] - 6 * p ** 3 * (1 - p) ** 2) < 1e-12
    # inversion round-trips
    for bo in (3, 5):
        for sp in (0.55, 0.7, 0.9):
            assert abs(series_win_prob(map_prob_for_series_prob(sp, bo), bo) - sp) < 1e-9
    for bo in (3, 5):
        d = series_score_distribution(0.65, bo)
        print(f"Bo{bo} p=0.65  win={series_win_prob(0.65, bo):.3f}  " +
              "  ".join(f"{s}={v:.3f}" for s, v in sorted(d.items(), reverse=True)))
    print("series.py self-test passed")
