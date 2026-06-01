"""Wilson-interval correctness checks."""

from __future__ import annotations

import math

import pytest

from reagent.stats import proportion, wilson_interval


def test_proportion_empty_returns_zero():
    assert proportion(0, 0) == 0.0
    assert proportion(5, 0) == 0.0


def test_wilson_empty_returns_unit_interval():
    ci = wilson_interval(0, 0)
    assert ci.low == 0.0 and ci.high == 1.0


def test_wilson_clamps_to_unit_interval():
    ci = wilson_interval(10, 10)
    assert ci.low >= 0.0 and ci.high <= 1.0
    assert ci.high == pytest.approx(1.0)
    # Not symmetric: lower bound should be < 1
    assert ci.low < 1.0


def test_wilson_known_value():
    # Reference (Wilson 1927): for x=43, n=47, the 95% CI is approximately
    # [0.806, 0.969]. Allow generous tolerance for the constant z chosen.
    ci = wilson_interval(43, 47)
    assert ci.low == pytest.approx(0.806, abs=0.01)
    assert ci.high == pytest.approx(0.969, abs=0.01)


def test_wilson_center_near_phat_for_large_n():
    ci = wilson_interval(500, 1000)
    center = (ci.low + ci.high) / 2
    assert math.isclose(center, 0.5, abs_tol=0.01)


def test_wilson_invalid_input():
    with pytest.raises(ValueError):
        wilson_interval(5, 2)
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
