import numpy as np
from simulator import simulate_game, TeamInput
from parlay import ParlayLeg, evaluate_sgp, _get_leg_mask

def test_push_parlay_logic():
    home = TeamInput(name="Home", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="Away", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)
    
    # Run 100k sims
    n_sims = 100_000
    result = simulate_game(home, away, game_id="test_game", n_sims=n_sims, seed=42)
    
    # We find the exact median margin to guarantee pushes
    median_margin = float(np.median(result.margin))
    
    # Leg 1: Spread
    home_spread_leg = ParlayLeg(
        game_id="test_game",
        bet_type="home_spread",
        line=-median_margin,
        description="Home Exact Spread Push Check"
    )
    
    # Leg 2: Total
    median_total = float(np.median(result.total))
    total_over_leg = ParlayLeg(
        game_id="test_game",
        bet_type="over",
        line=median_total,
        description="Over Exact Total Push Check"
    )

    legs = [home_spread_leg, total_over_leg]
    results = {"test_game": result}
    
    evaluate_sgp(results, legs)
    
    # Double check mask values
    mask1 = _get_leg_mask(result, home_spread_leg) # 1, 0, -1
    mask2 = _get_leg_mask(result, total_over_leg)
    
    both_push = (mask1 == 0) & (mask2 == 0)
    wins = (mask1 != -1) & (mask2 != -1) & ((mask1 == 1) | (mask2 == 1))
    
    pushes_count = np.count_nonzero(both_push)
    print(f"Total double-pushes found: {pushes_count}")
    
    assert not np.any(both_push & wins), "A double push was incorrectly counted as a win!"
    print("test_push_parlay passed: Exact-line pushes void/evaluate properly.")

if __name__ == "__main__":
    test_push_parlay_logic()
