# Tests R-P2-01 through R-P2-06
from datetime import datetime

from zoneinfo import ZoneInfo

from game_data import GameEntry
from parlay import ParlayLeg, evaluate_mg_parlay
from run_tonight import _classify_parlay, is_game_started
from simulator import SimResult, TeamInput, simulate_game

NBA_TZ = ZoneInfo("America/New_York")


def _make_minimal_game(tip_off_et: str) -> GameEntry:
    """Return a minimal GameEntry with a specific tip-off time."""
    return GameEntry(
        game_id="TEST",
        tip_off_et=tip_off_et,
        away_name="Away",
        away_abbr="AWA",
        away_pace=100.0,
        away_ortg=115.0,
        away_drtg=115.0,
        away_injury_adj=0.0,
        away_injury_notes="",
        home_name="Home",
        home_abbr="HOM",
        home_pace=100.0,
        home_ortg=115.0,
        home_drtg=115.0,
        home_injury_adj=0.0,
        home_injury_notes="",
        vegas_home_spread=-7.5,
        vegas_total=220.0,
    )


def _make_sim_results(n_games: int, n_sims: int = 1_000) -> dict:
    """Run one simulation and reuse scores across n fake games."""
    home = TeamInput(name="H", abbr="HOM", pace=100.0, ortg=115.0, drtg=115.0)
    away = TeamInput(name="A", abbr="AWA", pace=100.0, ortg=115.0, drtg=115.0)
    base = simulate_game(home, away, game_id="g0", n_sims=n_sims, seed=42)
    results = {}
    for i in range(n_games):
        gid = f"g{i}"
        results[gid] = SimResult(
            game_id=gid,
            home=base.home,
            away=base.away,
            home_scores=base.home_scores,
            away_scores=base.away_scores,
            n_sims=base.n_sims,
        )
    return results


# ── R-P2-01: is_game_started returns True when 10 min in the past ─────────────
def test_is_game_started_true():
    """R-P2-01: game started 10 min ago → True."""
    now_et = datetime(2026, 3, 4, 20, 10, tzinfo=NBA_TZ)  # 8:10 PM ET
    g = _make_minimal_game("8:00 PM ET")  # tipped off 10 min ago
    assert is_game_started(g, now_et) is True


# ── R-P2-02: is_game_started returns False when 30 min in the future ──────────
def test_is_game_started_false():
    """R-P2-02: game starts in 30 min → False."""
    now_et = datetime(2026, 3, 4, 20, 0, tzinfo=NBA_TZ)  # 8:00 PM ET
    g = _make_minimal_game("8:30 PM ET")  # tips off in 30 min
    assert is_game_started(g, now_et) is False


# ── R-P2-03: _classify_parlay classifications ─────────────────────────────────
def test_classify_parlay_standard():
    assert _classify_parlay(4) == "STANDARD"


def test_classify_parlay_high_risk():
    assert _classify_parlay(5) == "HIGH_RISK"


def test_classify_parlay_lottery():
    assert _classify_parlay(7) == "LOTTERY"


# ── R-P2-04: evaluate_mg_parlay 5 legs → is_lottery_grade True ───────────────
def test_mg_parlay_5_legs_is_lottery():
    """R-P2-04: 5-leg parlay has is_lottery_grade == True."""
    results = _make_sim_results(5)
    legs = [
        ParlayLeg(game_id=f"g{i}", bet_type="home_ml", line=0.0, description=f"Leg {i}")
        for i in range(5)
    ]
    pr = evaluate_mg_parlay(results, legs)
    assert pr.is_lottery_grade is True, (
        f"Expected is_lottery_grade=True, got {pr.is_lottery_grade}"
    )


# ── R-P2-05: evaluate_mg_parlay 3 legs → is_lottery_grade False ──────────────
def test_mg_parlay_3_legs_not_lottery():
    """R-P2-05: 3-leg parlay has is_lottery_grade == False."""
    results = _make_sim_results(3)
    legs = [
        ParlayLeg(game_id=f"g{i}", bet_type="home_ml", line=0.0, description=f"Leg {i}")
        for i in range(3)
    ]
    pr = evaluate_mg_parlay(results, legs)
    assert pr.is_lottery_grade is False, (
        f"Expected is_lottery_grade=False, got {pr.is_lottery_grade}"
    )
