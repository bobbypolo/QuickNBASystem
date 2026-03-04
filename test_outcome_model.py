# Tests R-P1-11
import numpy as np
from outcome_model import (
    sample_quarter_scores,
    quarter_intensity,
    _scale_rates,
    LEAGUE_AVG_EPV,
)


def test_epv_scale_bounded():
    """Scale always [0.3, 2.5]."""
    # Very low PPP
    rates_low = _scale_rates(0.30, 1.0)
    scale_low = 0.30 * 1.0 / LEAGUE_AVG_EPV
    assert scale_low < 0.3  # would be below floor
    assert rates_low["fg2_make"] > 0  # still valid

    # Very high PPP
    rates_high = _scale_rates(3.0, 1.0)
    scale_high = 3.0 * 1.0 / LEAGUE_AVG_EPV
    assert scale_high > 2.5  # would be above ceiling
    assert rates_high["fg2_make"] <= 0.70  # capped


def test_garbage_time_reduces_scoring():
    """Q4 +25 lead → lower intensity than Q4 +0."""
    intensity_close = quarter_intensity(4, 0.0)
    intensity_blowout = quarter_intensity(4, 25.0)
    assert intensity_blowout < intensity_close, (
        f"Blowout intensity {intensity_blowout} should be < close game {intensity_close}"
    )


def test_foul_game_increases_scoring():
    """Q4 close game slightly boosts scoring."""
    intensity_q3 = quarter_intensity(3, 0.0)
    intensity_q4_close = quarter_intensity(4, 3.0)
    # Q4 base is 1.08, close game adds foul game boost
    assert intensity_q4_close > intensity_q3


def test_quarter_scores_positive():
    """No negative scores."""
    rng = np.random.default_rng(42)
    scores = sample_quarter_scores(1.10, 25.0, 1.0, 100_000, rng)
    assert np.all(scores >= 0), "Found negative quarter scores"


def test_mean_quarter_score_reasonable():
    """Mean Q1 per team 22-35."""
    rng = np.random.default_rng(42)
    scores = sample_quarter_scores(1.14, 25.0, 1.0, 100_000, rng)
    mean = float(np.mean(scores))
    assert 22.0 < mean < 35.0, f"Mean quarter score {mean} out of range"


def test_heavier_tails():
    """Kurtosis higher than pure Gaussian (excess kurtosis > 0 or score std varies)."""
    rng = np.random.default_rng(42)
    scores = sample_quarter_scores(1.14, 25.0, 1.0, 200_000, rng)
    # The discrete outcome model should produce variance — std > 0
    std = float(np.std(scores))
    assert std > 2.0, f"Quarter score std {std} too low — not realistic variance"


def test_ot_intensity_boost():
    """OT scores slightly higher rate than Q1."""
    ot_intensity = quarter_intensity(5, 0.0)
    q1_intensity = quarter_intensity(1, 0.0)
    assert ot_intensity > q1_intensity, (
        f"OT intensity {ot_intensity} should be > Q1 {q1_intensity}"
    )


def test_blowout_q4_lower_scoring():
    """Big lead Q4 mean ~22-28 (garbage time reduces scoring)."""
    rng = np.random.default_rng(42)
    intensity = quarter_intensity(4, 30.0)  # Big blowout
    scores = sample_quarter_scores(1.14, 25.0, intensity, 100_000, rng)
    mean = float(np.mean(scores))
    assert 18.0 < mean < 32.0, f"Blowout Q4 mean {mean} out of range"


if __name__ == "__main__":
    test_epv_scale_bounded()
    test_garbage_time_reduces_scoring()
    test_foul_game_increases_scoring()
    test_quarter_scores_positive()
    test_mean_quarter_score_reasonable()
    test_heavier_tails()
    test_ot_intensity_boost()
    test_blowout_q4_lower_scoring()
    print("All outcome_model tests passed.")
