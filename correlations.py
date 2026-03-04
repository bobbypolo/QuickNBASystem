"""
Correlation Matrix + Gaussian Copula for Multi-Game Parlays.
Ported from nba-production-system/risk/correlations.py + config/settings.py.
"""

import numpy as np
from scipy.stats import norm

# 8x8 research-backed correlation matrix
CORRELATION_LABELS = [
    "team_win",
    "game_total",
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_3pm",
    "team_total",
    "opponent_total",
]

FULL_CORRELATION_MATRIX = np.array(
    [
        # tw     gt     pp     pr     pa     p3     tt     ot
        [1.00, 0.15, 0.20, 0.10, 0.15, 0.12, 0.55, -0.40],  # team_win
        [0.15, 1.00, 0.30, 0.20, 0.25, 0.22, 0.65, 0.65],  # game_total
        [0.20, 0.30, 1.00, 0.15, 0.35, 0.45, 0.40, 0.10],  # player_points
        [0.10, 0.20, 0.15, 1.00, 0.10, -0.10, 0.15, 0.15],  # player_rebounds
        [0.15, 0.25, 0.35, 0.10, 1.00, 0.15, 0.30, 0.10],  # player_assists
        [0.12, 0.22, 0.45, -0.10, 0.15, 1.00, 0.25, 0.08],  # player_3pm
        [0.55, 0.65, 0.40, 0.15, 0.30, 0.25, 1.00, 0.10],  # team_total
        [-0.40, 0.65, 0.10, 0.15, 0.10, 0.08, 0.10, 1.00],  # opponent_total
    ]
)

SAME_TEAM_BOOST = 0.08
CORRELATION_CAP = 0.95

# Map bet_type strings to correlation label indices
BET_TYPE_TO_LABEL: dict[str, str] = {
    "home_spread": "team_win",
    "away_spread": "team_win",
    "home_ml": "team_win",
    "away_ml": "team_win",
    "over": "game_total",
    "under": "game_total",
}

_LABEL_TO_IDX = {label: i for i, label in enumerate(CORRELATION_LABELS)}


def get_correlation(type1: str, type2: str, same_team: bool = False) -> float:
    """Look up base correlation between two bet types.

    Args:
        type1: Correlation label (e.g., "team_win", "game_total")
        type2: Correlation label
        same_team: Whether both legs are on the same team

    Returns:
        Correlation coefficient, clipped to [-CORRELATION_CAP, CORRELATION_CAP]
    """
    idx1 = _LABEL_TO_IDX.get(type1)
    idx2 = _LABEL_TO_IDX.get(type2)
    if idx1 is None or idx2 is None:
        return 0.0

    rho = FULL_CORRELATION_MATRIX[idx1, idx2]

    # Add same-team boost if legs are on the same team but different types
    if same_team and type1 != type2:
        rho += SAME_TEAM_BOOST

    return float(np.clip(rho, -CORRELATION_CAP, CORRELATION_CAP))


def _ensure_positive_definite(matrix: np.ndarray) -> np.ndarray:
    """Enforce positive definiteness via eigenvalue floor."""
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    eigenvalues = np.maximum(eigenvalues, 1e-6)
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T


def correlated_parlay_prob(
    marginal_probs: list[float],
    leg_types: list[str],
    same_team_flags: list[list[bool]] | None = None,
    n_sims: int = 50_000,
    seed: int | None = None,
) -> float:
    """Compute joint probability of a parlay using Gaussian copula.

    Args:
        marginal_probs: List of marginal win probabilities per leg
        leg_types: List of correlation labels per leg (e.g., ["team_win", "game_total"])
        same_team_flags: NxN matrix of same-team flags (None = all False)
        n_sims: Number of Monte Carlo simulations for copula
        seed: Random seed

    Returns:
        Joint probability that all legs hit.
    """
    n = len(marginal_probs)
    if n == 0:
        return 0.0
    if n == 1:
        return marginal_probs[0]

    # Build NxN correlation submatrix
    corr_matrix = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            same_team = same_team_flags[i][j] if same_team_flags is not None else False
            rho = get_correlation(leg_types[i], leg_types[j], same_team=same_team)
            corr_matrix[i, j] = rho
            corr_matrix[j, i] = rho

    # Ensure positive definiteness
    corr_matrix = _ensure_positive_definite(corr_matrix)

    # Cholesky decomposition
    L = np.linalg.cholesky(corr_matrix)

    # Draw correlated standard normals
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_sims, n))
    correlated_z = z @ L.T  # shape (n_sims, n)

    # Convert to correlated uniforms via CDF
    u = norm.cdf(correlated_z)

    # Check if all legs hit: u[i] < marginal_prob[i]
    all_hit = np.all(u < np.array(marginal_probs), axis=1)

    return float(np.mean(all_hit))
