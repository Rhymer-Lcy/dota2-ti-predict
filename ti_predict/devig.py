"""De-vigging: convert bookmaker decimal odds into outcome probabilities.

Reused verbatim from the archived odds-pipeline (soccer) project — the math is
sport-agnostic, so it applies unchanged to Dota 2 match-winner / series-score odds.

Every function takes decimal odds as a 2D array ``(n_events, n_outcomes)`` and
returns normalized probabilities of the same shape (each row sums to 1). They
differ only in how the bookmaker margin (overround) is removed:

- ``proportional``: naive normalization ``p_i = (1/o_i) / sum(1/o_j)``. Simple,
  but inherits the favorite-longshot bias baked into the raw book.
- ``shin``: Shin (1992) model. Removes the margin assuming a fraction ``z`` of
  turnover comes from insiders; shrinks longshots and lifts favorites, which in
  practice improves calibration.
- ``power``: solves ``p_i = (1/o_i) ** k`` for the ``k`` that makes the
  probabilities sum to 1.

The Shin/power solvers use vectorized bisection so they run over the whole
dataset at once.
"""
import numpy as np


def _raw(odds):
    odds = np.asarray(odds, dtype=np.float64)
    if odds.ndim == 1:
        odds = odds[None, :]
    return 1.0 / odds


def proportional(odds):
    r = _raw(odds)
    return r / r.sum(axis=1, keepdims=True)


def shin(odds, n_iter=60):
    """Shin (1992) de-vig. Recovers true probs q_i from raw implied p_i=1/o_i:

        q_i(z) = [sqrt(z^2 + 4(1-z) p_i^2 / B) - z] / [2(1-z)],   B = sum_j p_j

    with z (insider fraction) chosen so sum_i q_i = 1. sum_i q_i decreases in z,
    so a simple bisection on z in [0, 1) converges.
    """
    r = _raw(odds)
    B = r.sum(axis=1, keepdims=True)
    lo = np.zeros((r.shape[0], 1))
    hi = np.full((r.shape[0], 1), 0.99)

    def q_of(z):
        return (np.sqrt(z ** 2 + 4.0 * (1.0 - z) * r ** 2 / B) - z) / (2.0 * (1.0 - z))

    for _ in range(n_iter):
        z = 0.5 * (lo + hi)
        s = q_of(z).sum(axis=1, keepdims=True)
        too_high = s > 1.0  # need a larger z to bring the sum down
        lo = np.where(too_high, z, lo)
        hi = np.where(too_high, hi, z)
    q = q_of(0.5 * (lo + hi))
    return q / q.sum(axis=1, keepdims=True)


def power(odds, n_iter=60):
    """Power de-vig: q_i = (1/o_i)**k, with k>=1 chosen so sum_i q_i = 1."""
    r = _raw(odds)
    logr = np.log(r)
    lo = np.ones((r.shape[0], 1))
    hi = np.full((r.shape[0], 1), 10.0)
    for _ in range(n_iter):
        k = 0.5 * (lo + hi)
        s = np.exp(k * logr).sum(axis=1, keepdims=True)
        too_high = s > 1.0  # need a larger k to bring the sum down
        lo = np.where(too_high, k, lo)
        hi = np.where(too_high, hi, k)
    q = np.exp(0.5 * (lo + hi) * logr)
    return q / q.sum(axis=1, keepdims=True)


METHODS = {"proportional": proportional, "shin": shin, "power": power}
