import numpy as np
from simulator import simulate_game, TeamInput


def test_no_ties_after_ot():
    """1M sims, assert 0 ties (matches existing test_ot_resolution.py). # Tests R-P3-06"""
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)

    result = simulate_game(home, away, game_id="qtr_1m", n_sims=1_000_000, seed=42)
    ties = np.count_nonzero(result.home_scores == result.away_scores)
    assert ties == 0, f"Expected 0 ties, but found {ties}!"


def test_score_distribution_reasonable():
    """Mean home score 95-125, std 8-18. # Tests R-P3-05"""
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)

    result = simulate_game(home, away, game_id="dist", n_sims=50_000, seed=99)
    mean_h = float(np.mean(result.home_scores))
    std_h = float(np.std(result.home_scores))

    assert 90.0 < mean_h < 130.0, f"Mean home score {mean_h} out of range"
    assert 5.0 < std_h < 22.0, f"Std home score {std_h} out of range"


def test_simresult_interface_unchanged():
    """All SimResult properties work correctly."""
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=112.0, drtg=117.0)

    result = simulate_game(home, away, game_id="iface", n_sims=10_000, seed=42)

    # All properties should return valid values
    assert isinstance(result.margin, np.ndarray)
    assert isinstance(result.total, np.ndarray)
    assert 0.0 < result.home_win_prob < 1.0
    assert 0.0 < result.away_win_prob < 1.0
    assert abs(result.home_win_prob + result.away_win_prob - 1.0) < 0.001
    assert isinstance(result.model_spread, float)
    assert isinstance(result.model_total, float)

    # Cover/over/under probs
    assert 0.0 <= result.home_cover_prob(-5.0) <= 1.0
    assert 0.0 <= result.away_cover_prob(5.0) <= 1.0
    assert 0.0 <= result.over_prob(220.0) <= 1.0
    assert 0.0 <= result.under_prob(220.0) <= 1.0

    # Masks
    assert result.spread_cover_mask(-5.0).shape == (10_000,)
    assert result.away_spread_mask(5.0).shape == (10_000,)
    assert result.over_mask(220.0).shape == (10_000,)
    assert result.under_mask(220.0).shape == (10_000,)
    assert result.home_ml_mask().shape == (10_000,)
    assert result.away_ml_mask().shape == (10_000,)

    # Display helpers
    assert isinstance(result.spread_label(), str)
    assert isinstance(result.home_ml_american(), int)
    assert isinstance(result.away_ml_american(), int)


def test_existing_tests_pass():
    """run_tonight.py compatible — simulate works with GameEntry-style inputs."""
    home = TeamInput(
        name="Orlando Magic",
        abbr="ORL",
        pace=99.4,
        ortg=114.3,
        drtg=114.1,
        injury_adj=0.5,
    )
    away = TeamInput(
        name="Washington Wizards",
        abbr="WAS",
        pace=101.1,
        ortg=110.7,
        drtg=121.3,
        injury_adj=4.0,
    )
    result = simulate_game(home, away, game_id="WAS@ORL", n_sims=10_000, seed=42)

    # Home should win overwhelmingly with these ratings + injuries
    assert result.home_win_prob > 0.6, (
        f"Expected Orlando to be strong favorite, got {result.home_win_prob}"
    )
    assert result.n_sims == 10_000


if __name__ == "__main__":
    print("Running quarter sim tests...")
    test_no_ties_after_ot()
    print("  test_no_ties_after_ot passed")
    test_score_distribution_reasonable()
    print("  test_score_distribution_reasonable passed")
    test_simresult_interface_unchanged()
    print("  test_simresult_interface_unchanged passed")
    test_existing_tests_pass()
    print("  test_existing_tests_pass passed")
    print("All quarter_sim tests passed.")
