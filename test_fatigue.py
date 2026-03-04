# Tests R-P5-05
from math import isclose
from fatigue import (
    ScheduleContext,
    compute_fatigue,
    B2B_BURDEN,
    THREE_IN_FOUR_BURDEN,
    PACE_BOUNDS,
    EFF_BOUNDS,
)


def test_no_fatigue_default():
    """Default context → all multipliers ~1.0."""
    ctx = ScheduleContext()
    mults = compute_fatigue(ctx)
    assert isclose(mults.pace_mult, 1.0, abs_tol=0.001)
    assert isclose(mults.ortg_mult, 1.0, abs_tol=0.001)
    assert isclose(mults.drtg_mult, 1.0, abs_tol=0.001)
    assert isclose(mults.burden_score, 0.0, abs_tol=0.001)


def test_b2b_penalizes_offense():
    """B2B → ortg_mult < 1.0."""
    ctx = ScheduleContext(is_b2b=True)
    mults = compute_fatigue(ctx)
    assert mults.ortg_mult < 1.0, (
        f"B2B ortg_mult should be < 1.0, got {mults.ortg_mult}"
    )


def test_b2b_worsens_defense():
    """B2B → drtg_mult > 1.0."""
    ctx = ScheduleContext(is_b2b=True)
    mults = compute_fatigue(ctx)
    assert mults.drtg_mult > 1.0, (
        f"B2B drtg_mult should be > 1.0, got {mults.drtg_mult}"
    )


def test_b2b_slows_pace():
    """B2B → pace_mult < 1.0."""
    ctx = ScheduleContext(is_b2b=True)
    mults = compute_fatigue(ctx)
    assert mults.pace_mult < 1.0, (
        f"B2B pace_mult should be < 1.0, got {mults.pace_mult}"
    )


def test_3in4_additive():
    """B2B + 3in4 → larger burden than B2B alone."""
    b2b_only = compute_fatigue(ScheduleContext(is_b2b=True))
    b2b_3in4 = compute_fatigue(ScheduleContext(is_b2b=True, is_3in4=True))
    assert b2b_3in4.burden_score > b2b_only.burden_score


def test_travel_scales():
    """2000 miles → larger burden than 500 miles."""
    short = compute_fatigue(ScheduleContext(travel_miles=500.0))
    long = compute_fatigue(ScheduleContext(travel_miles=2000.0))
    assert long.burden_score > short.burden_score


def test_rest_advantage_offsets():
    """3 rest days vs 1 → reduced burden."""
    rested = compute_fatigue(ScheduleContext(rest_days=3.0, opponent_rest_days=1.0))
    assert rested.burden_score < 0, (
        f"Rest advantage should give negative burden, got {rested.burden_score}"
    )


def test_bounds_enforced():
    """Extreme fatigue stays within bounds."""
    extreme = compute_fatigue(
        ScheduleContext(
            is_b2b=True,
            is_3in4=True,
            travel_miles=5000.0,
            rest_days=0.0,
            opponent_rest_days=5.0,
        )
    )
    assert PACE_BOUNDS[0] <= extreme.pace_mult <= PACE_BOUNDS[1]
    assert EFF_BOUNDS[0] <= extreme.ortg_mult <= EFF_BOUNDS[1]
    assert EFF_BOUNDS[0] <= extreme.drtg_mult <= EFF_BOUNDS[1]


def test_burden_constants_match():
    """B2B=0.70, 3in4=0.45 match production values."""
    assert B2B_BURDEN == 0.70
    assert THREE_IN_FOUR_BURDEN == 0.45


if __name__ == "__main__":
    test_no_fatigue_default()
    test_b2b_penalizes_offense()
    test_b2b_worsens_defense()
    test_b2b_slows_pace()
    test_3in4_additive()
    test_travel_scales()
    test_rest_advantage_offsets()
    test_bounds_enforced()
    test_burden_constants_match()
    print("All fatigue tests passed.")
