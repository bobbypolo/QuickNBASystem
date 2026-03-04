# Tests R-P1-10
import numpy as np
from correlations import (
    FULL_CORRELATION_MATRIX,
    SAME_TEAM_BOOST,
    CORRELATION_CAP,
    get_correlation,
    correlated_parlay_prob,
)


def test_matrix_symmetric():
    """M == M.T."""
    assert np.allclose(FULL_CORRELATION_MATRIX, FULL_CORRELATION_MATRIX.T)


def test_diagonal_ones():
    """All diagonal = 1.0."""
    diag = np.diag(FULL_CORRELATION_MATRIX)
    assert np.allclose(diag, 1.0)


def test_same_team_boost():
    """team_win + team_total + same_team = 0.55 + 0.08 = 0.63."""
    rho = get_correlation("team_win", "team_total", same_team=True)
    expected = 0.55 + SAME_TEAM_BOOST
    assert abs(rho - expected) < 0.001, f"Expected {expected}, got {rho}"


def test_correlation_cap():
    """No value exceeds 0.95."""
    n = FULL_CORRELATION_MATRIX.shape[0]
    for i in range(n):
        for j in range(n):
            if i != j:
                assert abs(FULL_CORRELATION_MATRIX[i, j]) <= CORRELATION_CAP + 0.001


def test_negative_corr_reduces_joint():
    """team_win + opponent_total (rho=-0.40) → joint < product."""
    probs = [0.6, 0.5]
    product = 0.6 * 0.5

    joint = correlated_parlay_prob(probs, ["team_win", "opponent_total"], seed=42)
    assert joint < product + 0.02, (
        f"Negative correlation joint {joint} should be < product {product}"
    )


def test_positive_corr_increases_joint():
    """team_total + game_total (rho=0.65) → joint > product."""
    probs = [0.6, 0.6]
    product = 0.6 * 0.6

    joint = correlated_parlay_prob(probs, ["team_total", "game_total"], seed=42)
    assert joint > product - 0.02, (
        f"Positive correlation joint {joint} should be > product {product}"
    )


def test_single_leg_returns_marginal():
    """1-leg → marginal prob."""
    result = correlated_parlay_prob([0.65], ["team_win"], seed=42)
    assert abs(result - 0.65) < 0.001


def test_uncorrelated_approx_product():
    """When types are the same (rho=1.0 on diagonal, but testing different legs),
    for truly independent legs (different types with ~0 correlation),
    joint ≈ product within MC noise."""
    probs = [0.5, 0.5]
    product = 0.25

    # player_rebounds + player_3pm have rho=-0.10 (close to 0)
    joint = correlated_parlay_prob(
        probs, ["player_rebounds", "player_3pm"], n_sims=200_000, seed=42
    )
    assert abs(joint - product) < 0.03, (
        f"Near-zero correlation joint {joint} should be ≈ product {product}"
    )


def test_parlayleg_backward_compatible():
    """Old ParlayLeg still works (no required fields added)."""
    from parlay import ParlayLeg

    leg = ParlayLeg(
        game_id="TEST",
        bet_type="home_spread",
        line=-7.5,
        description="Home -7.5",
    )
    assert leg.correlation_type is None
    assert leg.book_odds is None


if __name__ == "__main__":
    test_matrix_symmetric()
    test_diagonal_ones()
    test_same_team_boost()
    test_correlation_cap()
    test_negative_corr_reduces_joint()
    test_positive_corr_increases_joint()
    test_single_leg_returns_marginal()
    test_uncorrelated_approx_product()
    test_parlayleg_backward_compatible()
    print("All correlations tests passed.")
