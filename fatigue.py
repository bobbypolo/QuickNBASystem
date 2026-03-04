"""
Fatigue & Schedule Context — Rest days, B2B, travel as multipliers on pace/ortg/drtg.
Ported from nba-production-system/engine/schedule_topology_fatigue.py.
"""

from dataclasses import dataclass

# Multiplier bounds
PACE_BOUNDS = (0.94, 1.03)
EFF_BOUNDS = (0.96, 1.04)

# Burden score component weights
B2B_BURDEN = 0.70
THREE_IN_FOUR_BURDEN = 0.45
TRAVEL_MAX_BURDEN = 0.60
TRAVEL_DIVISOR = 3000.0
REST_ADVANTAGE_RATE = 0.10
REST_ADVANTAGE_MAX = 0.35
BURDEN_MIN = -0.40
BURDEN_MAX = 2.00

# Multiplier coefficients
PACE_BURDEN_COEFF = 0.025
PACE_REST_COEFF = 0.006
ORTG_BURDEN_COEFF = 0.018
ORTG_REST_COEFF = 0.005
DRTG_BURDEN_COEFF = 0.016
DRTG_REST_COEFF = 0.004


@dataclass
class ScheduleContext:
    """Schedule context for one team in a game."""

    is_b2b: bool = False
    is_3in4: bool = False
    rest_days: float = 1.0
    opponent_rest_days: float = 1.0
    travel_miles: float = 0.0


@dataclass
class FatigueMultipliers:
    """Multipliers to apply to team pace/ortg/drtg."""

    pace_mult: float = 1.0
    ortg_mult: float = 1.0
    drtg_mult: float = 1.0
    burden_score: float = 0.0


def _compute_burden(ctx: ScheduleContext) -> float:
    """Compute fatigue burden score from schedule context."""
    burden = 0.0

    if ctx.is_b2b:
        burden += B2B_BURDEN
    if ctx.is_3in4:
        burden += THREE_IN_FOUR_BURDEN

    # Travel fatigue (scales linearly up to max)
    burden += min(
        TRAVEL_MAX_BURDEN, ctx.travel_miles / TRAVEL_DIVISOR * TRAVEL_MAX_BURDEN
    )

    # Rest advantage/disadvantage
    rest_delta = ctx.rest_days - ctx.opponent_rest_days
    if rest_delta > 0:
        burden -= min(REST_ADVANTAGE_MAX, rest_delta * REST_ADVANTAGE_RATE)
    elif rest_delta < 0:
        burden += min(REST_ADVANTAGE_MAX, abs(rest_delta) * REST_ADVANTAGE_RATE)

    return max(BURDEN_MIN, min(BURDEN_MAX, burden))


def compute_fatigue(ctx: ScheduleContext) -> FatigueMultipliers:
    """Compute fatigue multipliers from schedule context.

    Returns multipliers that should be applied to team ratings:
    - pace_mult: Applied to team pace
    - ortg_mult: Applied to team offensive rating
    - drtg_mult: Applied to team defensive rating (>1.0 = worse defense)
    """
    burden = _compute_burden(ctx)
    rest_delta = ctx.rest_days - ctx.opponent_rest_days

    # Raw multipliers
    raw_pace = (
        1.0
        - PACE_BURDEN_COEFF * max(0.0, burden)
        + PACE_REST_COEFF * max(0.0, rest_delta)
    )
    raw_ortg = (
        1.0
        - ORTG_BURDEN_COEFF * max(0.0, burden)
        + ORTG_REST_COEFF * max(0.0, rest_delta)
    )
    raw_drtg = (
        1.0
        + DRTG_BURDEN_COEFF * max(0.0, burden)
        - DRTG_REST_COEFF * max(0.0, rest_delta)
    )

    # Clamp to bounds
    pace_mult = max(PACE_BOUNDS[0], min(PACE_BOUNDS[1], raw_pace))
    ortg_mult = max(EFF_BOUNDS[0], min(EFF_BOUNDS[1], raw_ortg))
    drtg_mult = max(EFF_BOUNDS[0], min(EFF_BOUNDS[1], raw_drtg))

    return FatigueMultipliers(
        pace_mult=pace_mult,
        ortg_mult=ortg_mult,
        drtg_mult=drtg_mult,
        burden_score=burden,
    )
