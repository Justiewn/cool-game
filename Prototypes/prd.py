"""Pseudo-random distribution (PRD) — Dota-style variance-compressed proc.

Instead of an independent p-chance roll each attempt, the per-attempt
probability ramps linearly with the number of attempts since the last
success: `p_n = min(1, n * C)`, where C is chosen so the *long-run*
success rate equals the intended `p`.

Effect: streaks compress. You can't miss 10 crits in a row at 25%, and
you rarely land three in a row. Long-run rate is unchanged.

Public API:
    C_for(p)         -> the C constant for target rate p in [0, 1]
    roll(unit, key, pct) -> bool. Ramps state on `unit._prd_counters[key]`.
"""

import math
import random


_C_CACHE = {}


def _expected_rate(C, max_iter=200):
    """Given ramp constant C, compute the long-run per-attempt success rate.

    E[N] = sum_{n=1..∞} n * P(first proc on trial n)
         where P(first proc on trial n) = (∏_{i<n}(1 - iC)) * min(1, nC).
    Long-run rate = 1 / E[N].
    """
    if C <= 0:
        return 0.0
    p_none_yet = 1.0
    E_N = 0.0
    max_n = min(max_iter, int(math.ceil(1.0 / C)) + 1)
    for n in range(1, max_n + 1):
        p_this = min(1.0, n * C)
        E_N += n * p_none_yet * p_this
        p_none_yet *= (1.0 - p_this)
        if p_none_yet <= 1e-12:
            break
    return 0.0 if E_N == 0 else 1.0 / E_N


def C_for(p):
    """Ramp constant that yields long-run success rate `p`. Cached."""
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    key = round(p, 4)
    if key in _C_CACHE:
        return _C_CACHE[key]
    # Binary search: rate(C) is monotone increasing in C on (0, p].
    lo, hi = 0.0, p
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        rate = _expected_rate(mid)
        if rate < p:
            lo = mid
        else:
            hi = mid
    C = 0.5 * (lo + hi)
    _C_CACHE[key] = C
    return C


def roll(unit, key, pct):
    """PRD roll on `unit` for stat `key` at target percentage `pct` (0–100).

    Maintains a per-unit counter `unit._prd_counters[key]`. Returns True on
    success and resets the counter; returns False and increments otherwise.
    Falls back to a plain roll if the unit lacks the counter attribute.
    """
    p = max(0.0, min(1.0, pct / 100.0))
    if p <= 0:
        return False
    if p >= 1:
        return True
    counters = getattr(unit, "_prd_counters", None)
    if counters is None:
        # Graceful fallback — shouldn't happen once Unit.__init__ is updated,
        # but keeps this callable in tests that build bare objects.
        return random.random() < p
    n = counters.get(key, 0) + 1
    C = C_for(p)
    if random.random() < min(1.0, n * C):
        counters[key] = 0
        return True
    counters[key] = n
    return False


if __name__ == "__main__":
    # Verify long-run rates match the target.
    for target in (0.05, 0.15, 0.25, 0.40, 0.60):
        C = C_for(target)
        rate = _expected_rate(C)
        assert abs(rate - target) < 1e-4, (target, rate)

    # Sample-based sanity: run 200_000 rolls per target, expect within ±0.5%.
    class _U:
        def __init__(self):
            self._prd_counters = {}
    random.seed(1)
    for pct in (5, 15, 25, 40):
        u = _U()
        hits = sum(1 for _ in range(200_000) if roll(u, "CRIT", pct))
        observed = hits / 200_000
        assert abs(observed - pct / 100) < 0.005, (pct, observed)

    # Variance sanity: with PRD, max gap between successes should be ~2/p on
    # average, dramatically tighter than geometric (which has fat tails).
    u = _U()
    gaps = []
    since = 0
    for _ in range(200_000):
        since += 1
        if roll(u, "CRIT", 25):
            gaps.append(since)
            since = 0
    max_gap = max(gaps)
    # Under 25% independent rolls, we'd routinely see gaps of 25+.
    # Under PRD, gaps are hard-capped near ceil(1/C) ≈ 12.
    assert max_gap <= 15, max_gap
    print(f"prd.py self-check OK  (25% PRD max gap observed: {max_gap})")
