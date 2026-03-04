"""
Discrete Outcome Scoring Model — Analytically computes scoring moments from
possession outcome probabilities, then samples from Normal with those moments.
Ported from nba-production-system/engine/sequencer.py + epv_model.py.
"""

import numpy as np

# League-average base rates
FG2_ATTEMPT_RATE = 0.47
FG2_MAKE_RATE = 0.490
FG3_ATTEMPT_RATE = 0.35
FG3_MAKE_RATE = 0.350
FREE_THROW_RATE = 0.22
FT_MAKE_RATE = 0.78
TURNOVER_RATE = 0.13
OREB_RATE = 0.27
LEAGUE_AVG_EPV = 1.14

# Shooting caps
MAX_FG2_MAKE = 0.70
MAX_FG3_MAKE = 0.50
MIN_TO_RATE = 0.05

# Quarter intensity multipliers
QUARTER_INTENSITY: dict[int, float] = {1: 1.00, 2: 0.98, 3: 1.02, 4: 1.08}
OT_INTENSITY = 1.12

# Game-state modifiers for Q4
GARBAGE_TIME_MARGIN = 25
GARBAGE_MULTIPLIER = 0.90
FOUL_GAME_MARGIN = 8
FOUL_GAME_TIME = 120  # seconds
FOUL_GAME_MULTIPLIER = 1.20
REGULATION_QUARTER_SECONDS = 720


def _scale_rates(team_ppp: float, intensity: float) -> dict[str, float]:
    """Scale base shooting rates by team efficiency and quarter intensity.

    Returns dict with adjusted rates for expected value calculation.
    """
    scale = np.clip(team_ppp * intensity / LEAGUE_AVG_EPV, 0.3, 2.5)

    fg2_make = min(FG2_MAKE_RATE * scale, MAX_FG2_MAKE)
    fg3_make = min(FG3_MAKE_RATE * scale, MAX_FG3_MAKE)
    to_rate = max(TURNOVER_RATE / scale, MIN_TO_RATE)
    ft_make = FT_MAKE_RATE  # FT% doesn't scale with team strength

    return {
        "fg2_att": FG2_ATTEMPT_RATE,
        "fg2_make": fg2_make,
        "fg3_att": FG3_ATTEMPT_RATE,
        "fg3_make": fg3_make,
        "ft_rate": FREE_THROW_RATE,
        "ft_make": ft_make,
        "to_rate": to_rate,
        "oreb_rate": OREB_RATE,
    }


def _compute_moments(rates: dict[str, float]) -> tuple[float, float]:
    """Compute E[pts_per_possession] and Var[pts_per_possession] from discrete outcomes."""
    p_fg2 = rates["fg2_att"] * rates["fg2_make"]
    p_fg3 = rates["fg3_att"] * rates["fg3_make"]
    # Average 1.4 pts per FT trip (mix of 1-and-1, 2-shot, 3-shot fouls)
    p_ft_pts = rates["ft_rate"] * rates["ft_make"] * 1.4

    # Expected points per possession
    e_pts = 2.0 * p_fg2 + 3.0 * p_fg3 + p_ft_pts

    # E[X^2] for variance: Var = E[X^2] - E[X]^2
    e_pts_sq = (
        4.0 * p_fg2 + 9.0 * p_fg3 + (1.4**2) * rates["ft_rate"] * rates["ft_make"]
    )
    var_pts = max(e_pts_sq - e_pts**2, 0.01)

    return e_pts, var_pts


def quarter_intensity(period: int, score_diff: float) -> float:
    """Get intensity multiplier for a quarter.

    Args:
        period: 1-4 for regulation, 5+ for OT
        score_diff: home - away score entering this period

    Returns:
        Intensity multiplier for scoring rate.
    """
    if period >= 5:
        return OT_INTENSITY

    base = QUARTER_INTENSITY.get(period, 1.0)

    if period == 4:
        abs_diff = abs(score_diff)
        if abs_diff >= GARBAGE_TIME_MARGIN:
            base *= GARBAGE_MULTIPLIER
        elif abs_diff < FOUL_GAME_MARGIN:
            # Foul game: fractionally apply boost weighted by time fraction
            foul_fraction = FOUL_GAME_TIME / REGULATION_QUARTER_SECONDS
            base *= 1.0 + (FOUL_GAME_MULTIPLIER - 1.0) * foul_fraction

    return base


def sample_quarter_scores(
    team_ppp: float,
    possessions: float,
    intensity: float,
    n_sims: int,
    rng: np.random.Generator,
    noise: np.ndarray | None = None,
) -> np.ndarray:
    """Sample quarter scores for n_sims using analytical moments.

    Args:
        team_ppp: Team's base points-per-possession
        possessions: Number of possessions this quarter
        intensity: Quarter intensity multiplier
        n_sims: Number of simulations
        rng: Numpy random generator
        noise: Optional pre-generated standard normal noise for correlation

    Returns:
        Array of shape (n_sims,) with integer quarter scores.
    """
    rates = _scale_rates(team_ppp, intensity)
    e_pts, var_pts = _compute_moments(rates)

    # Account for OREBs extending possessions
    effective_poss = possessions * (
        1.0 + rates["oreb_rate"] * (1.0 - rates["to_rate"]) * 0.3
    )

    mean_quarter = e_pts * effective_poss
    std_quarter = np.sqrt(var_pts * effective_poss)

    if noise is not None:
        scores = mean_quarter + std_quarter * noise
    else:
        scores = rng.normal(mean_quarter, std_quarter, n_sims)

    return np.maximum(scores, 0.0)
