# Tests R-P3-07, R-P3-01
from pace_engine import (
    base_pace,
    predict_period_possessions,
    score_state_factor,
    PERIOD_FACTORS,
)


def test_slower_team_dictates():
    """Teams (95, 105) → base ~99.0 not 100.0 (slower dictates 60%)."""
    bp = base_pace(95.0, 105.0)
    assert 98.5 < bp < 99.5, f"Expected ~99.0, got {bp}"
    # Symmetric
    bp2 = base_pace(105.0, 95.0)
    assert abs(bp - bp2) < 0.001


def test_period_factors():
    """Q1 > Q2 pace for same inputs (1.02 vs 0.97)."""
    q1 = predict_period_possessions(100.0, 100.0, 1, 0.0)
    q2 = predict_period_possessions(100.0, 100.0, 2, 0.0)
    assert q1 > q2, f"Q1 ({q1}) should be > Q2 ({q2})"


def test_blowout_slows_leader():
    """+20 diff → leading factor 0.88."""
    home_f, away_f = score_state_factor(20.0)
    assert home_f == 0.88, f"Leading team should have 0.88, got {home_f}"
    assert away_f == 1.05, f"Trailing team should have 1.05, got {away_f}"


def test_trailing_speeds_up():
    """-20 diff → home trailing speeds up."""
    home_f, away_f = score_state_factor(-20.0)
    assert home_f == 1.05, f"Trailing home should have 1.05, got {home_f}"
    assert away_f == 0.88, f"Leading away should have 0.88, got {away_f}"


def test_comfortable_lead():
    """+10 diff → factor 0.95 for leader."""
    home_f, away_f = score_state_factor(10.0)
    assert home_f == 0.95
    assert away_f == 1.02


def test_close_game_neutral():
    """+3 diff → factor 1.0 for both."""
    home_f, away_f = score_state_factor(3.0)
    assert home_f == 1.0
    assert away_f == 1.0


def test_ot_possessions():
    """OT yields ~10-12 possessions for average-pace teams."""
    ot_poss = predict_period_possessions(100.0, 100.0, 5, 0.0)
    assert 9.0 < ot_poss < 14.0, f"OT possessions should be ~10-12, got {ot_poss}"


def test_regulation_possessions():
    """Q possessions = pace/4 (approx) for neutral game."""
    poss = predict_period_possessions(100.0, 100.0, 3, 0.0)
    # Q3 has factor 1.00, close game = 1.0
    bp = base_pace(100.0, 100.0)
    expected = bp * PERIOD_FACTORS[3] / 4.0
    assert abs(poss - expected) < 0.1, f"Expected {expected}, got {poss}"


def test_predict_period_possessions_vec_shape_and_order():
    """R-P3-01: vec function returns shape (3,) and blowout states have fewer
    possessions than neutral (both symmetric blowout elements < neutral element 1)."""
    import numpy as np
    from pace_engine import predict_period_possessions_vec

    score_diffs = np.array([-30.0, 0.0, 30.0])
    result = predict_period_possessions_vec(100.0, 100.0, 4, score_diffs)

    assert result.shape == (3,), f"Expected shape (3,), got {result.shape}"
    # With equal-pace teams, ±30 are symmetric → [0]==[2], both < neutral [1].
    # (The leading team slows down at 0.88, trailing speeds up at 1.05; average=0.965<1.0)
    assert result[0] < result[1], (
        f"Blowout trailing ({result[0]:.3f}) should have < possessions than neutral ({result[1]:.3f})"
    )
    assert result[2] < result[1], (
        f"Blowout leading ({result[2]:.3f}) should have < possessions than neutral ({result[1]:.3f})"
    )


if __name__ == "__main__":
    test_slower_team_dictates()
    test_period_factors()
    test_blowout_slows_leader()
    test_trailing_speeds_up()
    test_comfortable_lead()
    test_close_game_neutral()
    test_ot_possessions()
    test_regulation_possessions()
    test_predict_period_possessions_vec_shape_and_order()
    print("All pace_engine tests passed.")
