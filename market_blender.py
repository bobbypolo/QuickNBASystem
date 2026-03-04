"""
Market Blender — Logit-space blending of model and market probabilities.
Ported from nba-production-system/markets/market_blender.py.
"""

from dataclasses import dataclass
from math import exp, log
from typing import Optional

# Market weights by bet type (how much weight the market gets)
MARKET_WEIGHTS: dict[str, float] = {
    "spread": 0.35,
    "total": 0.40,
    "moneyline": 0.30,
}

# Numerical safety bounds
PROB_CLAMP_MIN = 1e-6
PROB_CLAMP_MAX = 1.0 - 1e-6


@dataclass
class BlendResult:
    """Result of probability blending."""

    p_model: float
    p_market: float
    p_blended: float
    weight: float
    market_type: str


def _clamp_prob(p: float) -> float:
    """Clamp probability to avoid log(0)."""
    return max(PROB_CLAMP_MIN, min(PROB_CLAMP_MAX, p))


def prob_to_logit(p: float) -> float:
    """Convert probability to logit (log-odds)."""
    p = _clamp_prob(p)
    return log(p / (1.0 - p))


def logit_to_prob(logit: float) -> float:
    """Convert logit back to probability."""
    return 1.0 / (1.0 + exp(-logit))


def blend_probability(
    p_model: float,
    p_market: float,
    market_type: str = "spread",
    weight_override: Optional[float] = None,
) -> BlendResult:
    """Blend model and market probabilities in logit space.

    The market weight w determines how much the market pulls the final
    probability. w=0.35 for spread means: 35% market, 65% model.

    Args:
        p_model: Model-derived probability
        p_market: Market-implied probability (after de-vigging)
        market_type: One of "spread", "total", "moneyline"
        weight_override: Override the default market weight

    Returns:
        BlendResult with blended probability
    """
    w = (
        weight_override
        if weight_override is not None
        else MARKET_WEIGHTS.get(market_type, 0.35)
    )
    w = max(0.0, min(1.0, w))

    L_model = prob_to_logit(p_model)
    L_market = prob_to_logit(p_market)

    # Blend in logit space: w is market weight, (1-w) is model weight
    L_final = (1.0 - w) * L_model + w * L_market

    p_blended = logit_to_prob(L_final)

    return BlendResult(
        p_model=p_model,
        p_market=p_market,
        p_blended=p_blended,
        weight=w,
        market_type=market_type,
    )
