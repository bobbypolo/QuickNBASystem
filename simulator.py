"""
NBA Monte Carlo Simulation Engine
Quarter-by-quarter simulation with pace engine, discrete outcome model,
fatigue adjustments, and correlated quarter noise.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from pace_engine import predict_period_possessions, predict_period_possessions_vec
from outcome_model import (
    quarter_intensity,
    quarter_intensity_vec,
    sample_quarter_scores,
)

# ── Constants ────────────────────────────────────────────────────────────────
HOME_COURT_ADVANTAGE = 2.5  # points added to home team score (total game)
N_SIMS = 10_000  # number of Monte Carlo iterations
QUARTER_CORRELATION = 0.20  # cross-team scoring correlation per quarter


# ── Data Structures ───────────────────────────────────────────────────────────
@dataclass
class TeamInput:
    """Input stats for one team in a game."""

    name: str
    abbr: str
    pace: float  # possessions per 48 min (NBA.com/stats Advanced)
    ortg: float  # offensive rating (pts per 100 possessions)
    drtg: float  # defensive rating (pts allowed per 100 possessions)
    injury_adj: float = (
        0.0  # points to SUBTRACT from ortg (star player out, use positive number)
    )
    # Fatigue multipliers (default 1.0 = no fatigue)
    pace_mult: float = 1.0
    ortg_mult: float = 1.0
    drtg_mult: float = 1.0


@dataclass
class SimResult:
    """Output of simulate_game(): score distributions + market probabilities."""

    game_id: str
    home: TeamInput
    away: TeamInput
    home_scores: np.ndarray  # shape (N_SIMS,) - simulated home scores
    away_scores: np.ndarray  # shape (N_SIMS,) - simulated away scores
    n_sims: int

    # ── Score distribution properties ────────────────────────────────────────
    @property
    def margin(self) -> np.ndarray:
        """Home margin per sim (positive = home wins)."""
        return self.home_scores - self.away_scores

    @property
    def total(self) -> np.ndarray:
        """Combined score per sim."""
        return self.home_scores + self.away_scores

    # ── Market probabilities ──────────────────────────────────────────────────
    @property
    def home_win_prob(self) -> float:
        return float(np.mean(self.home_scores > self.away_scores))

    @property
    def away_win_prob(self) -> float:
        return 1.0 - self.home_win_prob

    @property
    def model_spread(self) -> float:
        """Median margin from home perspective. Negative = away team favored."""
        return float(np.median(self.margin))

    @property
    def model_total(self) -> float:
        """Median combined score."""
        return float(np.median(self.total))

    def home_cover_prob(self, line: float) -> float:
        """P(home covers spread).
        line = sportsbook spread for home (e.g., -7.5 if home favored by 7.5).
        Home covers when margin > -line.
        """
        return float(np.mean(self.margin > -line))

    def away_cover_prob(self, line: float) -> float:
        """P(away covers spread).
        line = sportsbook spread for away (e.g., +7.5 if away is dog).
        Away covers when margin < line.
        """
        return float(np.mean(self.margin < line))

    def over_prob(self, line: float) -> float:
        """P(combined score > line)."""
        return float(np.mean(self.total > line))

    def under_prob(self, line: float) -> float:
        """P(combined score < line)."""
        return float(np.mean(self.total < line))

    def spread_cover_mask(self, home_line: float) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.margin > -home_line] = 1
        result[self.margin == -home_line] = 0
        return result

    def away_spread_mask(self, away_line: float) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.margin < away_line] = 1
        result[self.margin == away_line] = 0
        return result

    def over_mask(self, total_line: float) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.total > total_line] = 1
        result[self.total == total_line] = 0
        return result

    def under_mask(self, total_line: float) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.total < total_line] = 1
        result[self.total == total_line] = 0
        return result

    def home_ml_mask(self) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.home_scores > self.away_scores] = 1
        result[self.home_scores == self.away_scores] = 0
        return result

    def away_ml_mask(self) -> np.ndarray:
        """3-state array: 1 = Win, 0 = Push, -1 = Loss."""
        result = np.full(self.n_sims, -1, dtype=int)
        result[self.away_scores > self.home_scores] = 1
        result[self.home_scores == self.away_scores] = 0
        return result

    # ── Display helpers ───────────────────────────────────────────────────────
    def spread_label(self) -> str:
        m = self.model_spread
        if m > 0:
            return f"{self.home.name} -{m:.1f}"
        else:
            return f"{self.away.name} -{abs(m):.1f}"

    def home_ml_american(self) -> int:
        return _prob_to_american(self.home_win_prob)

    def away_ml_american(self) -> int:
        return _prob_to_american(self.away_win_prob)


# ── Core Simulation Function ──────────────────────────────────────────────────
def simulate_game(
    home: TeamInput,
    away: TeamInput,
    game_id: str = "",
    n_sims: int = N_SIMS,
    seed: Optional[int] = None,
) -> SimResult:
    """
    Run Monte Carlo simulation for a single NBA game.

    Quarter-by-quarter algorithm:
      1. Apply injury + fatigue adjustments to team ratings.
      2. For each quarter (1-4), compute possessions via PaceEngine,
         generate correlated noise, sample scores via discrete outcome model.
      3. Add HCA spread across quarters.
      4. Resolve ties with overtime (period=5 pace + OT intensity).

    Returns SimResult with full score distributions for parlay evaluation.
    """
    rng = np.random.default_rng(seed)

    # Apply injury adjustments and fatigue multipliers
    home_ortg = (home.ortg - home.injury_adj) * home.ortg_mult
    away_ortg = (away.ortg - away.injury_adj) * away.ortg_mult
    home_drtg = home.drtg * home.drtg_mult
    away_drtg = away.drtg * away.drtg_mult
    home_pace = home.pace * home.pace_mult
    away_pace = away.pace * away.pace_mult

    # Base points-per-possession for each team
    home_base_ppp = (home_ortg + away_drtg) / 200.0
    away_base_ppp = (away_ortg + home_drtg) / 200.0

    # HCA spread across 4 quarters
    hca_quarter = HOME_COURT_ADVANTAGE / 4.0

    # Accumulate scores quarter-by-quarter
    home_scores = np.zeros(n_sims)
    away_scores = np.zeros(n_sims)

    for period in range(1, 5):
        # Per-sim game-state tracking (fixes median-diff bug)
        per_sim_diffs = home_scores - away_scores

        possessions_vec = predict_period_possessions_vec(
            home_pace, away_pace, period, per_sim_diffs
        )
        intensity_vec = quarter_intensity_vec(period, per_sim_diffs)

        # Generate correlated noise (Phase 6)
        z1 = rng.standard_normal(n_sims)
        z2 = rng.standard_normal(n_sims)
        h_noise = z1
        a_noise = QUARTER_CORRELATION * z1 + np.sqrt(1 - QUARTER_CORRELATION**2) * z2

        home_q = sample_quarter_scores(
            home_base_ppp, possessions_vec, intensity_vec, n_sims, rng, noise=h_noise
        )
        away_q = sample_quarter_scores(
            away_base_ppp, possessions_vec, intensity_vec, n_sims, rng, noise=a_noise
        )

        home_scores += np.round(home_q + hca_quarter)
        away_scores += np.round(away_q)

    # Resolve ties with overtime logic
    ties = home_scores == away_scores

    while np.any(ties):
        n_ties = np.count_nonzero(ties)

        ot_poss = predict_period_possessions(home_pace, away_pace, 5, 0.0)
        ot_intensity = quarter_intensity(5, 0.0)

        # Correlated OT noise
        z1 = rng.standard_normal(n_ties)
        z2 = rng.standard_normal(n_ties)
        h_noise_ot = z1
        a_noise_ot = QUARTER_CORRELATION * z1 + np.sqrt(1 - QUARTER_CORRELATION**2) * z2

        ot_home = sample_quarter_scores(
            home_base_ppp, ot_poss, ot_intensity, n_ties, rng, noise=h_noise_ot
        )
        ot_away = sample_quarter_scores(
            away_base_ppp, ot_poss, ot_intensity, n_ties, rng, noise=a_noise_ot
        )

        # OT HCA proportional to 5/48 of full game
        ot_hca = HOME_COURT_ADVANTAGE * 5.0 / 48.0
        home_scores[ties] += np.round(ot_home + ot_hca)
        away_scores[ties] += np.round(ot_away)

        ties = home_scores == away_scores

    return SimResult(
        game_id=game_id,
        home=home,
        away=away,
        home_scores=home_scores,
        away_scores=away_scores,
        n_sims=n_sims,
    )


# ── Utility Functions ─────────────────────────────────────────────────────────
def _prob_to_american(prob: float) -> int:
    """Convert win probability to American moneyline odds."""
    prob = max(0.001, min(0.999, prob))
    if prob >= 0.5:
        return int(-prob / (1 - prob) * 100)
    else:
        return int((1 - prob) / prob * 100)


def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability (no vig removal)."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def devig_pair(p1_raw: float, p2_raw: float) -> tuple[float, float]:
    """Remove vig from a two-outcome market (proportional method)."""
    total = p1_raw + p2_raw
    return p1_raw / total, p2_raw / total


def format_american(odds: int) -> str:
    """Format American odds with sign."""
    if odds > 0:
        return f"+{odds}"
    return str(odds)
