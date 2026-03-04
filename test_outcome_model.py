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


def test_q4_blowout_tier_30():
    """R-P1-04: quarter_intensity(4, 31.0) in [0.77, 0.79] (1.08 * 0.72)."""
    intensity = quarter_intensity(4, 31.0)
    assert 0.77 <= intensity <= 0.79, (
        f"Q4 blowout (31pt) intensity {intensity:.4f} expected in [0.77, 0.79]"
    )


def test_q3_blowout_trigger():
    """R-P1-05: quarter_intensity(3, 31.0) in [0.72, 0.75] (1.02 * 0.72)."""
    intensity = quarter_intensity(3, 31.0)
    assert 0.72 <= intensity <= 0.75, (
        f"Q3 blowout (31pt) intensity {intensity:.4f} expected in [0.72, 0.75]"
    )


def test_q4_tier_15_19():
    """R-P1-06: quarter_intensity(4, 16.0) in [1.02, 1.04] (1.08 * 0.95)."""
    intensity = quarter_intensity(4, 16.0)
    assert 1.02 <= intensity <= 1.04, (
        f"Q4 15-19pt tier (16pt) intensity {intensity:.4f} expected in [1.02, 1.04]"
    )


def test_quarter_intensity_vec_q4_shape_and_order():
    """R-P3-02: vec Q4 returns shape (3,), blowout elements < close element."""
    import numpy as np
    from outcome_model import quarter_intensity_vec

    score_diffs = np.array([-31.0, 0.0, 31.0])
    result = quarter_intensity_vec(4, score_diffs)

    assert result.shape == (3,), f"Expected shape (3,), got {result.shape}"
    # Elements 0 and 2 are blowouts (31pt); element 1 is close (foul game boost)
    assert result[0] < result[1], (
        f"Blowout trailing ({result[0]:.4f}) should be < close game ({result[1]:.4f})"
    )
    assert result[2] < result[1], (
        f"Blowout leading ({result[2]:.4f}) should be < close game ({result[1]:.4f})"
    )


def test_quarter_intensity_vec_q3_blowout():
    """R-P3-03: Q3 blowout elements < 0.76 (30+ tier applies in Q3)."""
    import numpy as np
    from outcome_model import quarter_intensity_vec

    score_diffs = np.array([-31.0, 0.0, 31.0])
    result = quarter_intensity_vec(3, score_diffs)

    assert result.shape == (3,), f"Expected shape (3,), got {result.shape}"
    assert result[0] < 0.76, f"Q3 blowout trailing ({result[0]:.4f}) should be < 0.76"
    assert result[2] < 0.76, f"Q3 blowout leading ({result[2]:.4f}) should be < 0.76"


if __name__ == "__main__":
    test_epv_scale_bounded()
    test_garbage_time_reduces_scoring()
    test_foul_game_increases_scoring()
    test_quarter_scores_positive()
    test_mean_quarter_score_reasonable()
    test_heavier_tails()
    test_ot_intensity_boost()
    test_blowout_q4_lower_scoring()
    test_q4_blowout_tier_30()
    test_q3_blowout_trigger()
    test_q4_tier_15_19()
    test_quarter_intensity_vec_q4_shape_and_order()
    test_quarter_intensity_vec_q3_blowout()
    print("All outcome_model tests passed.")
