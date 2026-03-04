# Tests R-P4-07
from math import isclose
from market_blender import (
    blend_probability,
    prob_to_logit,
    logit_to_prob,
)


def test_logit_roundtrip():
    """logit_to_prob(prob_to_logit(p)) == p."""
    for p in [0.1, 0.25, 0.5, 0.75, 0.9]:
        roundtrip = logit_to_prob(prob_to_logit(p))
        assert isclose(roundtrip, p, abs_tol=1e-10), (
            f"Roundtrip failed for {p}: got {roundtrip}"
        )


def test_weight_1_returns_market():
    """weight=1.0 → p_market."""
    result = blend_probability(0.78, 0.63, weight_override=1.0)
    assert isclose(result.p_blended, 0.63, abs_tol=1e-6)


def test_weight_0_returns_model():
    """weight=0.0 → p_model."""
    result = blend_probability(0.78, 0.63, weight_override=0.0)
    assert isclose(result.p_blended, 0.78, abs_tol=1e-6)


def test_blended_between_inputs():
    """Result always between p_model and p_market."""
    result = blend_probability(0.78, 0.63, "moneyline")
    assert 0.63 <= result.p_blended <= 0.78, (
        f"Blended {result.p_blended} not between 0.63 and 0.78"
    )


def test_overconfident_shrinks():
    """Model 0.78, market 0.63 → blended ~0.65-0.75."""
    result = blend_probability(0.78, 0.63, "moneyline")
    assert 0.63 < result.p_blended < 0.78
    # With 30% market weight, should pull toward market
    assert result.p_blended < 0.76


def test_spread_weight_035():
    """Default spread weight lookup correct."""
    result = blend_probability(0.60, 0.50, "spread")
    assert result.weight == 0.35


def test_symmetric():
    """blend(0.7, 0.5) equidistant from 0.5 as blend(0.3, 0.5) from 0.5."""
    r1 = blend_probability(0.7, 0.5, weight_override=0.35)
    r2 = blend_probability(0.3, 0.5, weight_override=0.35)
    # Due to logit symmetry around 0.5
    assert isclose(r1.p_blended + r2.p_blended, 1.0, abs_tol=1e-6)


def test_extreme_no_error():
    """p=0.01 and p=0.99 don't crash."""
    r1 = blend_probability(0.01, 0.50, "spread")
    r2 = blend_probability(0.99, 0.50, "spread")
    assert 0.0 < r1.p_blended < 1.0
    assert 0.0 < r2.p_blended < 1.0


if __name__ == "__main__":
    test_logit_roundtrip()
    test_weight_1_returns_market()
    test_weight_0_returns_model()
    test_blended_between_inputs()
    test_overconfident_shrinks()
    test_spread_weight_035()
    test_symmetric()
    test_extreme_no_error()
    print("All market_blender tests passed.")
