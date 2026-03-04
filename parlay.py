"""
Parlay Evaluator — Uses simulation matrix for correlated probability.

Same-Game Parlay (SGP): Both legs come from the same simulation run,
so their correlation is naturally captured by the joint mask.

Multi-Game Parlay (MG): Games are independent, so joint prob = product
of individual probabilities (no copula needed).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from simulator import SimResult, american_to_implied_prob, format_american
from correlations import BET_TYPE_TO_LABEL, correlated_parlay_prob


# ── Data Structures ───────────────────────────────────────────────────────────
@dataclass
class ParlayLeg:
    """One leg of a parlay bet."""

    game_id: str
    bet_type: (
        str  # "home_spread" | "away_spread" | "over" | "under" | "home_ml" | "away_ml"
    )
    line: float  # spread/total line value (ignored for ML bets)
    description: str  # human-readable label
    book_odds: Optional[int] = None  # American odds from sportsbook (optional)
    correlation_type: Optional[str] = None  # override correlation label


@dataclass
class ParlayResult:
    """Output of parlay evaluation."""

    legs: List[ParlayLeg]
    leg_probs: List[float]  # individual probability per leg
    true_joint_prob: float  # true correlated probability (from sims)
    independence_prob: float  # naive product of individual probs (for comparison)
    true_american: int  # true odds in American format
    correlation_factor: float  # true / independence (>1 = positive correlation)
    parlay_type: str  # "SGP" or "MG"
    book_odds: Optional[int] = None  # sportsbook's offered price
    edge: Optional[float] = None  # true_prob - book_implied_prob


# ── Leg Evaluation ────────────────────────────────────────────────────────────
def _get_leg_mask(result: SimResult, leg: ParlayLeg) -> np.ndarray:
    """Return 3-state array: 1 = Win, 0 = Push, -1 = Loss."""
    if leg.bet_type == "home_spread":
        # home_line negative = home favored. Home covers if margin > -line.
        return result.spread_cover_mask(leg.line)
    elif leg.bet_type == "away_spread":
        return result.away_spread_mask(leg.line)
    elif leg.bet_type == "over":
        return result.over_mask(leg.line)
    elif leg.bet_type == "under":
        return result.under_mask(leg.line)
    elif leg.bet_type == "home_ml":
        return result.home_ml_mask()
    elif leg.bet_type == "away_ml":
        return result.away_ml_mask()
    else:
        raise ValueError(f"Unknown bet_type: {leg.bet_type}")


def _prob_to_american(prob: float) -> int:
    prob = max(0.001, min(0.999, prob))
    if prob >= 0.5:
        return int(-prob / (1 - prob) * 100)
    return int((1 - prob) / prob * 100)


# ── SGP Evaluator ─────────────────────────────────────────────────────────────
def evaluate_sgp(
    results: Dict[str, SimResult],
    legs: List[ParlayLeg],
    book_odds: Optional[int] = None,
) -> ParlayResult:
    """
    Evaluate a Same-Game Parlay using simulation matrix.
    All legs MUST be from the same game_id.
    Correlation is captured because both legs index the same sim rows.
    """
    game_ids = {leg.game_id for leg in legs}
    if len(game_ids) != 1:
        raise ValueError(f"SGP requires all legs from same game. Got: {game_ids}")

    game_id = next(iter(game_ids))
    result = results[game_id]

    masks = np.array([_get_leg_mask(result, leg) for leg in legs])
    leg_probs = [float(np.mean(m == 1)) for m in masks]

    # Joint mask: all conditions must be true simultaneously
    # A parlay hits if no legs are -1 (Loss), and at least one is 1 (Win)
    no_losses = np.all(masks != -1, axis=0)
    at_least_one_win = np.any(masks == 1, axis=0)
    joint_win_mask = no_losses & at_least_one_win

    true_joint_prob = float(np.mean(joint_win_mask))
    independence_prob = float(np.prod(leg_probs))
    corr_factor = (
        (true_joint_prob / independence_prob) if independence_prob > 0 else 0.0
    )

    edge = None
    if book_odds is not None:
        book_implied = american_to_implied_prob(book_odds)
        edge = true_joint_prob - book_implied

    return ParlayResult(
        legs=legs,
        leg_probs=leg_probs,
        true_joint_prob=true_joint_prob,
        independence_prob=independence_prob,
        true_american=_prob_to_american(true_joint_prob),
        correlation_factor=corr_factor,
        parlay_type="SGP",
        book_odds=book_odds,
        edge=edge,
    )


# ── Multi-Game Parlay Evaluator ───────────────────────────────────────────────
def evaluate_mg_parlay(
    results: Dict[str, SimResult],
    legs: List[ParlayLeg],
    book_odds: Optional[int] = None,
) -> ParlayResult:
    """
    Evaluate a Multi-Game Parlay.
    Uses Gaussian copula for cross-game correlation when applicable.
    """
    leg_win_probs = []
    for leg in legs:
        result = results[leg.game_id]
        mask = _get_leg_mask(result, leg)
        leg_win_probs.append(float(np.mean(mask == 1)))

    leg_probs = leg_win_probs
    independence_prob = float(np.prod(leg_probs))

    # Map legs to correlation labels
    leg_types = [
        leg.correlation_type or BET_TYPE_TO_LABEL.get(leg.bet_type, "team_win")
        for leg in legs
    ]

    # For MG parlays, different games → same_team=False for all pairs
    correlated_prob = correlated_parlay_prob(
        marginal_probs=leg_probs,
        leg_types=leg_types,
        same_team_flags=None,
        n_sims=50_000,
    )

    true_joint_prob = correlated_prob
    corr_factor = (
        (true_joint_prob / independence_prob) if independence_prob > 0 else 0.0
    )

    edge = None
    if book_odds is not None:
        book_implied = american_to_implied_prob(book_odds)
        edge = true_joint_prob - book_implied

    return ParlayResult(
        legs=legs,
        leg_probs=leg_probs,
        true_joint_prob=true_joint_prob,
        independence_prob=independence_prob,
        true_american=_prob_to_american(true_joint_prob),
        correlation_factor=corr_factor,
        parlay_type="MG",
        book_odds=book_odds,
        edge=edge,
    )


# ── Display ───────────────────────────────────────────────────────────────────
def print_parlay_result(pr: ParlayResult) -> None:
    """Pretty-print a parlay evaluation result."""
    tag = f"[{pr.parlay_type}]"
    print(f"\n  {tag} {len(pr.legs)}-Leg Parlay")
    print(f"  {'─' * 50}")
    for leg, prob in zip(pr.legs, pr.leg_probs):
        print(f"    Leg: {leg.description:40s} p={prob:.1%}")
    print(f"  {'─' * 50}")
    print(f"    True Joint Prob   : {pr.true_joint_prob:.1%}")
    print(f"    True Odds (model) : {format_american(pr.true_american)}")
    if pr.parlay_type == "SGP":
        print(
            f"    Independence Prob : {pr.independence_prob:.1%}  (corr factor: {pr.correlation_factor:.3f})"
        )
    if pr.book_odds is not None:
        book_imp = american_to_implied_prob(pr.book_odds)
        edge_str = (
            f"+{pr.edge:.1%}"
            if pr.edge and pr.edge > 0
            else f"{pr.edge:.1%}"
            if pr.edge
            else "N/A"
        )
        verdict = (
            "✅ +EV BET"
            if pr.edge and pr.edge > 0.02
            else ("⚠️  MARGINAL" if pr.edge and pr.edge > 0 else "❌ NO VALUE")
        )
        print(
            f"    Book Odds         : {format_american(pr.book_odds)}  (implied {book_imp:.1%})"
        )
        print(f"    Edge              : {edge_str}  {verdict}")
