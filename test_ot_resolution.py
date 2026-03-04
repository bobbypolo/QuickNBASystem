import numpy as np
from simulator import simulate_game, TeamInput

def test_ot_resolution_no_ties():
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)
    
    # 1 million iterations
    n_sims = 1_000_000
    
    print(f"Running {n_sims} simulations to verify zero ties...")
    result = simulate_game(home, away, game_id="sim_1m", n_sims=n_sims, seed=42)
    
    ties = np.count_nonzero(result.home_scores == result.away_scores)
    
    print(f"Total simulations: {n_sims}")
    print(f"Total ties found: {ties}")
    
    assert ties == 0, f"Expected 0 ties, but found {ties}!"
    print("test_ot_resolution passed: Zero ties occurred over 1M iterations.")

if __name__ == "__main__":
    test_ot_resolution_no_ties()
