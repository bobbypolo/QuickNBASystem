"""
Probability Calibration — spread underdog cap and uncertainty haircuts.
Empirical NBA ATS data 2015-2024, ~15,000 games.
"""

import math

# (spread_threshold, historical_cover_cap)
# Iterates in order; first threshold that exceeds abs_spread determines the cap.
SPREAD_COVER_CAPS: list[tuple[float, float]] = [
    (7.5, 1.00),  # small spreads: no cap
    (10.0, 0.54),  # -7.5 to -10: modest cap
    (13.0, 0.52),  # -10 to -13: significant cap
    (float("inf"), 0.50),  # -13+: near fair value for underdog
]


def spread_underdog_cap(raw_prob: float, abs_spread: float) -> float:
    """Cap the underdog cover probability based on spread magnitude.

    Args:
        raw_prob: Model-estimated cover probability (0-1)
        abs_spread: Absolute spread value (e.g., 13.5 for -13.5 favorite)

    Returns:
        Capped probability; never exceeds the empirical cap for that spread bucket.
    """
    for threshold, cap in SPREAD_COVER_CAPS:
        if abs_spread < threshold:
            return min(raw_prob, cap)
    return min(raw_prob, SPREAD_COVER_CAPS[-1][1])


def haircut_prob(raw_prob: float, n_sims: int, k: float = 1.5) -> float:
    """Apply uncertainty haircut using binomial standard error.

    Computes a lower-confidence bound: prob - k * stderr.
    Prevents recommending borderline picks that may be noise.

    Args:
        raw_prob: Point estimate probability (0-1)
        n_sims: Number of simulations used to estimate the probability
        k: Confidence multiplier (default 1.5 ≈ one-sided 93% CI)

    Returns:
        Haircutted probability, floored at 0.0.
    """
    stderr = math.sqrt(raw_prob * (1.0 - raw_prob) / n_sims) if n_sims > 0 else 0.0
    return max(0.0, raw_prob - k * stderr)
