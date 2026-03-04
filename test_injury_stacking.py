# Tests R-P5-01 through R-P5-04
from game_data import GameEntry
from run_tonight import _make_teams, injury_stacking_multiplier


def test_stacking_zero():
    """R-P5-01: injury_stacking_multiplier(0) returns 1.0."""
    assert injury_stacking_multiplier(0) == 1.0


def test_stacking_one():
    """Single player out → no stacking (still 1.0)."""
    assert injury_stacking_multiplier(1) == 1.0


def test_stacking_four():
    """R-P5-02: injury_stacking_multiplier(4) returns 1.45."""
    assert injury_stacking_multiplier(4) == 1.45


def test_stacking_two():
    """n=2 → 1.15x."""
    assert injury_stacking_multiplier(2) == 1.15


def test_stacking_five():
    """n=5 → 1.60x."""
    assert injury_stacking_multiplier(5) == 1.60


def _make_game_entry(**kwargs) -> GameEntry:
    """Minimal GameEntry for testing — all non-default required fields filled."""
    defaults = dict(
        game_id="TST@TST",
        tip_off_et="7:00 PM ET",
        away_name="Away Team",
        away_abbr="AWA",
        away_pace=100.0,
        away_ortg=110.0,
        away_drtg=110.0,
        away_injury_adj=0.0,
        away_injury_notes="",
        home_name="Home Team",
        home_abbr="HOM",
        home_pace=100.0,
        home_ortg=110.0,
        home_drtg=110.0,
        home_injury_adj=0.0,
        home_injury_notes="",
        vegas_home_spread=-3.0,
        vegas_total=220.0,
    )
    defaults.update(kwargs)
    return GameEntry(**defaults)


def test_make_teams_stacking_applied():
    """R-P5-03: away n_key_out=4 + injury_adj=7.5 → effective ortg reduction > 10.5."""
    g = _make_game_entry(away_injury_adj=7.5, away_n_key_out=4)
    _, away = _make_teams(g)
    # multiplier(4) = 1.45 → effective adj = 7.5 * 1.45 = 10.875 > 10.5
    assert away.injury_adj > 10.5, f"Expected > 10.5, got {away.injury_adj}"


def test_gameentry_has_n_key_out_fields():
    """R-P5-04: GameEntry has home_n_key_out and away_n_key_out with default 0."""
    g = _make_game_entry()
    assert hasattr(g, "home_n_key_out")
    assert hasattr(g, "away_n_key_out")
    assert g.home_n_key_out == 0
    assert g.away_n_key_out == 0


def test_gameentry_n_key_out_settable():
    """R-P5-04: n_key_out fields accept non-zero values."""
    g = _make_game_entry(home_n_key_out=2, away_n_key_out=3)
    assert g.home_n_key_out == 2
    assert g.away_n_key_out == 3


if __name__ == "__main__":
    test_stacking_zero()
    test_stacking_one()
    test_stacking_four()
    test_stacking_two()
    test_stacking_five()
    test_make_teams_stacking_applied()
    test_gameentry_has_n_key_out_fields()
    test_gameentry_n_key_out_settable()
    print("All injury stacking tests passed.")
