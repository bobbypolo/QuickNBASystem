# Tests R-P6-01 through R-P6-06
from unittest.mock import MagicMock, patch


from game_data import GameEntry
from injury_feed import fetch_injuries, fetch_last10_ratings, update_with_live_ratings
from run_tonight import _make_teams


def _make_game_entry(**kwargs) -> GameEntry:
    """Minimal GameEntry for testing."""
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


def test_fetch_injuries_network_error():
    """R-P6-01: fetch_injuries returns empty list on network error, no exception."""
    with patch("injury_feed.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("network unreachable")
        result = fetch_injuries("LAL")
    assert result == [], f"Expected empty list, got {result}"


def test_fetch_injuries_http_error():
    """fetch_injuries returns empty list on HTTP error (5xx)."""
    with patch("injury_feed.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        mock_get.return_value = mock_resp
        result = fetch_injuries("LAL")
    assert result == []


def test_fetch_last10_ratings_api_failure():
    """R-P6-02: fetch_last10_ratings returns empty dict on nba_api failure."""
    with patch.dict(
        "sys.modules",
        {
            "nba_api": MagicMock(),
            "nba_api.stats": MagicMock(),
            "nba_api.stats.endpoints": MagicMock(
                side_effect=ImportError("nba_api not available")
            ),
        },
    ):
        # Force the import inside the function to fail
        with patch(
            "builtins.__import__", side_effect=ImportError("nba_api unavailable")
        ):
            result = fetch_last10_ratings(["LAL", "NOP"])
    assert result == {}, f"Expected empty dict, got {result}"


def test_fetch_last10_ratings_exception():
    """fetch_last10_ratings returns empty dict on any unexpected exception."""
    import sys

    mock_nba = MagicMock()
    mock_nba.stats.endpoints.LeagueDashTeamStats.side_effect = RuntimeError(
        "API timeout"
    )
    with patch.dict(
        sys.modules,
        {
            "nba_api": mock_nba,
            "nba_api.stats": mock_nba.stats,
            "nba_api.stats.endpoints": mock_nba.stats.endpoints,
        },
    ):
        result = fetch_last10_ratings(["LAL", "NOP"])
    assert result == {}


def test_recency_weighting_ortg():
    """R-P6-03: home_last10_ortg=120, home_ortg=115 → effective ortg = 118.0."""
    g = _make_game_entry(home_ortg=115.0, home_last10_ortg=120.0)
    home, _ = _make_teams(g)
    expected = 0.60 * 120.0 + 0.40 * 115.0  # 118.0
    assert abs(home.ortg - expected) < 0.001, (
        f"Expected ortg {expected}, got {home.ortg}"
    )


def test_recency_weighting_backward_compat():
    """R-P6-04: home_last10_ortg=None → same result as pre-Phase-6 (season-only)."""
    g_new = _make_game_entry(home_ortg=115.0, home_last10_ortg=None)
    g_old = _make_game_entry(home_ortg=115.0)
    home_new, _ = _make_teams(g_new)
    home_old, _ = _make_teams(g_old)
    assert abs(home_new.ortg - home_old.ortg) < 0.001


def test_gameentry_last10_fields():
    """R-P6-05: GameEntry accepts all six last10 fields with default None."""
    g = _make_game_entry()
    assert g.home_last10_ortg is None
    assert g.home_last10_drtg is None
    assert g.home_last10_pace is None
    assert g.away_last10_ortg is None
    assert g.away_last10_drtg is None
    assert g.away_last10_pace is None


def test_gameentry_last10_settable():
    """R-P6-05: last10 fields accept float values."""
    g = _make_game_entry(
        home_last10_ortg=118.0,
        home_last10_drtg=112.0,
        home_last10_pace=98.5,
        away_last10_ortg=116.0,
        away_last10_drtg=114.0,
        away_last10_pace=101.0,
    )
    assert g.home_last10_ortg == 118.0
    assert g.away_last10_pace == 101.0


def test_update_with_live_ratings_both_feeds_fail():
    """R-P6-06: update_with_live_ratings returns {success: False, coverage: 0.0} on total failure."""
    games = [_make_game_entry(home_abbr="LAL", away_abbr="NOP")]
    with patch("injury_feed.fetch_last10_ratings", return_value={}):
        result = update_with_live_ratings(games, min_coverage=0.80)
    assert result["success"] is False
    assert result["coverage"] == 0.0


if __name__ == "__main__":
    test_fetch_injuries_network_error()
    test_fetch_injuries_http_error()
    test_fetch_last10_ratings_api_failure()
    test_fetch_last10_ratings_exception()
    test_recency_weighting_ortg()
    test_recency_weighting_backward_compat()
    test_gameentry_last10_fields()
    test_gameentry_last10_settable()
    test_update_with_live_ratings_both_feeds_fail()
    print("All injury feed tests passed.")
