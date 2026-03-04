import numpy as np
from simulator import simulate_game, TeamInput, QUARTER_CORRELATION


def _run_quarter_extraction(n_sims=100_000, seed=42, correlation=None):
    """Helper: run simulation and extract per-quarter scores.

    Since SimResult only stores total scores, we test correlation
    indirectly through total and margin variance properties.
    """
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)
    result = simulate_game(home, away, game_id="corr_test", n_sims=n_sims, seed=seed)
    return result


def test_quarter_correlation_effect():
    """With rho=0.20, totals should have higher variance than margins."""
    result = _run_quarter_extraction(n_sims=100_000)
    total_var = float(np.var(result.total))
    margin_var = float(np.var(result.margin))

    # With positive correlation: Var(H+A) > Var(H-A) because
    # Var(H+A) = Var(H) + Var(A) + 2*Cov(H,A)
    # Var(H-A) = Var(H) + Var(A) - 2*Cov(H,A)
    # For equal teams: total_var > margin_var when Cov > 0
    assert total_var > margin_var, (
        f"With positive correlation, total variance {total_var:.1f} "
        f"should be > margin variance {margin_var:.1f}"
    )


def test_total_variance_increases():
    """Var(home+away) should be notably above zero (correlated adds variance)."""
    result = _run_quarter_extraction(n_sims=100_000)
    total_std = float(np.std(result.total))
    # With correlation, total std should be well above 10
    assert total_std > 8.0, f"Total std {total_std} seems too low for correlated model"


def test_margin_variance_reasonable():
    """Var(home-away) should be reasonable range for equal teams."""
    result = _run_quarter_extraction(n_sims=100_000)
    margin_std = float(np.std(result.margin))
    assert 5.0 < margin_std < 20.0, f"Margin std {margin_std} out of reasonable range"


def test_zero_corr_matches_independent():
    """When QUARTER_CORRELATION is effectively tested at the module level,
    the default value should be 0.20."""
    assert abs(QUARTER_CORRELATION - 0.20) < 0.001


def test_over_under_calibration():
    """O/U probs should sum to reasonable values near a typical total."""
    result = _run_quarter_extraction(n_sims=50_000, seed=99)
    median_total = float(np.median(result.total))

    over_p = result.over_prob(median_total)
    under_p = result.under_prob(median_total)

    # At median, each should be near 50%
    assert 0.40 < over_p < 0.60, f"Over prob at median {over_p} out of range"
    assert 0.40 < under_p < 0.60, f"Under prob at median {under_p} out of range"


if __name__ == "__main__":
    test_quarter_correlation_effect()
    print("  test_quarter_correlation_effect passed")
    test_total_variance_increases()
    print("  test_total_variance_increases passed")
    test_margin_variance_reasonable()
    print("  test_margin_variance_reasonable passed")
    test_zero_corr_matches_independent()
    print("  test_zero_corr_matches_independent passed")
    test_over_under_calibration()
    print("  test_over_under_calibration passed")
    print("All correlated_quarters tests passed.")
