"""Small statistics helpers on the standard library (provided).

- `t_cdf` and `t_quantile`: Student's t distribution, by numerical integration of its density.
- `binom_two_sided`: the exact two-sided binomial test at p = 0.5. It is Chapter 7's exact McNemar test
  (Equation 7.2) when given the discordant counts, and the exact sign test when given the numbers of
  positive and negative differences.
- `percentile`: linear interpolation between order statistics, as in Chapter 7's labs.
"""

from __future__ import annotations

import math


def _t_pdf(x: float, df: float) -> float:
    c = math.lgamma((df + 1) / 2) - math.lgamma(df / 2) - 0.5 * math.log(df * math.pi)
    return math.exp(c - (df + 1) / 2 * math.log1p(x * x / df))


def t_cdf(t: float, df: float, steps: int = 2000) -> float:
    """P(T <= t) for Student's t with df degrees of freedom (Simpson's rule on [0, |t|])."""
    a = abs(t)
    if a == 0:
        return 0.5
    h = a / steps
    s = _t_pdf(0, df) + _t_pdf(a, df)
    for i in range(1, steps):
        s += (4 if i % 2 else 2) * _t_pdf(i * h, df)
    area = s * h / 3
    return 0.5 + area if t > 0 else 0.5 - area


def t_quantile(p: float, df: float) -> float:
    """The t value with P(T <= t) = p, by bisection."""
    lo, hi = -60.0, 60.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if t_cdf(mid, df, steps=400) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def binom_two_sided(b: int, c: int) -> float:
    """Exact two-sided p-value for b successes against c failures at p = 0.5 (McNemar, or the sign test)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def percentile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        raise ValueError("no values")
    pos = (len(xs) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)
