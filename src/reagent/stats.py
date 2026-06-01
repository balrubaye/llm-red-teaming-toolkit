"""Statistical helpers — kept stdlib-only so we don't pull in scipy."""

from __future__ import annotations

import math

from reagent.models import IntervalCI

# z for 95% CI. We hard-code rather than depending on scipy.stats.norm.ppf.
_Z_95 = 1.959963984540054


def wilson_interval(successes: int, trials: int, z: float = _Z_95) -> IntervalCI:
    """Wilson score interval for a binomial proportion.

    Reference: Wilson, E.B. (1927). "Probable inference, the law of succession,
    and statistical inference." J. American Statistical Association, 22, 209-212.

    Wilson is preferred over the normal approximation because it stays inside
    [0, 1] at extreme rates and small N. With trials == 0 we conservatively
    return [0, 1] rather than raising — callers may still want to render an
    interval for empty buckets.
    """
    if trials < 0 or successes < 0:
        raise ValueError("successes and trials must be non-negative")
    if successes > trials:
        raise ValueError("successes cannot exceed trials")
    if trials == 0:
        return IntervalCI(low=0.0, high=1.0)

    n = trials
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    half = (z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * n)) / n)) / denom
    return IntervalCI(low=max(0.0, center - half), high=min(1.0, center + half))


def proportion(successes: int, trials: int) -> float:
    """Safe proportion — returns 0.0 when trials == 0 (vs. ZeroDivisionError)."""
    if trials <= 0:
        return 0.0
    return successes / trials


__all__ = ["proportion", "wilson_interval"]
