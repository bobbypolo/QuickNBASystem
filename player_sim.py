import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional
from simulator import SimResult

@dataclass
class PlayerInput:
    player_id: int
    name: str
    team_id: int
    usg_pct: float
    ts_pct: float
    pts_per_game: float

def simulate_player_props(
    sim_result: SimResult,
    home_players: List[PlayerInput],
    away_players: List[PlayerInput],
    seed: Optional[int] = None
) -> Dict[int, np.ndarray]:
    """
    Simulate player props (points) for all players based on team scores.
    Distributes team volume using USG% and TS%, then applies Poisson distribution for scoring.
    
    Returns:
        Dict mapping player_id -> np.ndarray of shape (n_sims,)
    """
    rng = np.random.default_rng(seed)
    
    player_sims = {}
    
    def simulate_team_players(team_scores: np.ndarray, players: List[PlayerInput]):
        if not players:
            return
            
        # Calculate raw volume share based on USG% and TS%
        weights = np.array([p.usg_pct * p.ts_pct for p in players])
        sum_weights = np.sum(weights)
        
        if sum_weights > 0:
            shares = weights / sum_weights
        else:
            shares = np.ones(len(players)) / len(players)
            
        for i, p in enumerate(players):
            # The player's expected points in each simulation is their share of the simulated team score
            expected_pts = team_scores * shares[i]
            
            # Poisson takes a rate parameter (lambda), must be >= 0
            lam = np.maximum(expected_pts, 0.0)
            
            # Sample from Poisson distribution
            simulated_pts = rng.poisson(lam)
            player_sims[p.player_id] = simulated_pts
            
    simulate_team_players(sim_result.home_scores, home_players)
    simulate_team_players(sim_result.away_scores, away_players)
    
    return player_sims
