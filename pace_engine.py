"""
Pace Engine — Quarter-level possession estimation with score-elastic adjustments.
Ported from nba-production-system/engine/pace_engine.py.
"""


# Period-specific pace multipliers (regulation Q1-Q4, overtime Q5+)
PERIOD_FACTORS: dict[int, float] = {1: 1.02, 2: 0.97, 3: 1.00, 4: 1.04, 5: 1.08}

# Score-state thresholds
BLOWOUT_MARGIN = 15
COMFORTABLE_MARGIN = 8


def base_pace(home_pace: float, away_pace: float) -> float:
    """Slower team dictates 60% of pace."""
    slow = min(home_pace, away_pace)
    fast = max(home_pace, away_pace)
    return slow * 0.6 + fast * 0.4


def score_state_factor(score_diff: float) -> tuple[float, float]:
    """Score-elastic pace factors from home perspective.

    Args:
        score_diff: home_score - away_score (positive = home leading)

    Returns:
        (home_factor, away_factor)
    """
    abs_diff = abs(score_diff)
    if abs_diff >= BLOWOUT_MARGIN:
        leading_f, trailing_f = 0.88, 1.05
    elif abs_diff >= COMFORTABLE_MARGIN:
        leading_f, trailing_f = 0.95, 1.02
    else:
        return 1.0, 1.0

    if score_diff > 0:
        # Home is leading
        return leading_f, trailing_f
    else:
        # Away is leading
        return trailing_f, leading_f


def predict_period_possessions(
    home_pace: float,
    away_pace: float,
    period: int,
    score_diff: float = 0.0,
) -> float:
    """Estimate possessions for a given period.

    Args:
        home_pace: Home team pace (possessions per 48 min)
        away_pace: Away team pace (possessions per 48 min)
        period: 1-4 for regulation, 5+ for overtime
        score_diff: home - away score entering this period

    Returns:
        Estimated possessions for this period (shared by both teams).
    """
    bp = base_pace(home_pace, away_pace)

    # Period factor (cap at 5 for any OT period)
    pf = PERIOD_FACTORS.get(min(period, 5), PERIOD_FACTORS[5])

    # Score-state adjustment — average the two team factors
    home_f, away_f = score_state_factor(score_diff)
    state_f = (home_f + away_f) / 2.0

    if period <= 4:
        # Regulation quarter: pace_48 / 4
        return bp * pf * state_f / 4.0
    else:
        # Overtime: 5 minutes out of 48
        return bp * pf * state_f * 5.0 / 48.0
