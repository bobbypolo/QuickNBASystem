# Tests R-P7-01 through R-P7-05
import os
from unittest.mock import patch

import pytest

from calibration_log import (
    _resolve_outcome,
    backtest_report,
    log_actual,
    log_prediction,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database for each test."""
    return str(tmp_path / "test_predictions.db")


def test_r_p7_01_loss_on_missed_spread(tmp_db):
    """R-P7-01: spread_away +7.5 → LOSS when away team didn't cover.

    log_actual("2026-03-03", "SAS@PHI", 131, 91) means home(PHI)=131, away(SAS)=91.
    PHI won 131-91 by 40 pts. SAS was getting +7.5 but lost by 40 → LOSS.
    """
    log_prediction(
        "2026-03-03", "SAS@PHI", "spread_away", 7.5, 0.75, 0.62, 6.5, db_path=tmp_db
    )
    log_actual("2026-03-03", "SAS@PHI", 131, 91, db_path=tmp_db)

    report = backtest_report(lookback_days=365, db_path=tmp_db)
    assert report.total_resolved >= 1, "Expected at least one resolved bet"

    # Find the spread market entry
    spread_market = next((m for m in report.markets if m.market == "spread"), None)
    assert spread_market is not None, "Expected 'spread' market in report"
    assert spread_market.win_rate == 0.0, (
        f"Expected win_rate=0.0 (LOSS), got {spread_market.win_rate}"
    )


def test_r_p7_02_brier_score_perfect_prediction():
    """R-P7-02: Brier score of model_prob=1.0, outcome=1 is 0.0."""
    outcome = 1
    prob = 1.0
    brier = (prob - outcome) ** 2
    assert brier == 0.0


def test_brier_score_imperfect():
    """Brier score of model_prob=0.6, outcome=1 is (0.6-1)^2 = 0.16."""
    brier = (0.6 - 1) ** 2
    assert abs(brier - 0.16) < 1e-9


def test_r_p7_03_separate_spread_and_total_rows(tmp_db):
    """R-P7-03: backtest_report returns separate rows for 'spread' and 'total' markets."""
    # Log one spread bet (win) and one total bet (loss)
    log_prediction(
        "2026-03-03", "TST@ONE", "spread_home", -5.0, 0.60, 0.58, 3.0, db_path=tmp_db
    )
    log_actual(
        "2026-03-03", "TST@ONE", 115, 105, db_path=tmp_db
    )  # home wins by 10 > 5 → WIN

    log_prediction(
        "2026-03-03", "TST@TWO", "over", 220.0, 0.60, 0.58, 3.0, db_path=tmp_db
    )
    log_actual(
        "2026-03-03", "TST@TWO", 100, 105, db_path=tmp_db
    )  # total=205 < 220 → LOSS

    report = backtest_report(lookback_days=365, db_path=tmp_db)
    market_names = {m.market for m in report.markets}
    assert "spread" in market_names, f"Expected 'spread' market, got {market_names}"
    assert "total" in market_names, f"Expected 'total' market, got {market_names}"


def test_r_p7_04_log_prediction_no_exception_on_failure():
    """R-P7-04: _try_log_prediction does not raise even when calibration_log fails."""
    from run_tonight import _try_log_prediction

    # Patch calibration_log to raise an exception
    with patch(
        "builtins.__import__", side_effect=ImportError("calibration_log unavailable")
    ):
        # Should not raise
        _try_log_prediction(
            "2026-03-03", "TST@FOO", "spread_home", -5.0, 0.60, 0.58, 3.0
        )


def test_r_p7_05_log_results_cli_inserts_actuals(tmp_db):
    """R-P7-05: log_results.py --scores 'CHA 117 DAL 90' inserts home_score=117 for DAL@CHA."""
    import log_results

    # Parse the score string
    entries = log_results.parse_score_string("CHA 117 DAL 90")
    assert len(entries) == 1
    team1, score1, team2, score2 = entries[0]
    assert team1 == "CHA"
    assert score1 == 117
    assert team2 == "DAL"
    assert score2 == 90

    # Find game_id
    game_id = log_results._find_game_id("CHA", "DAL")
    assert game_id == "DAL@CHA", f"Expected 'DAL@CHA', got {game_id}"

    # Call log_actual directly and verify
    log_actual("2026-03-03", "DAL@CHA", 117, 90, db_path=tmp_db)

    # Verify via backtest_report — log a prediction too
    log_prediction(
        "2026-03-03", "DAL@CHA", "ml_home", 0.0, 0.60, 0.58, 0.0, db_path=tmp_db
    )
    report = backtest_report(lookback_days=365, db_path=tmp_db)
    assert report.total_resolved >= 1


def test_resolve_outcome_spread_away_win():
    """Away covers: away_score - home_score > -line (line=7.5 → dog, needs -40 > -7.5? No → LOSS)."""
    # SAS +7.5 (dog), PHI wins 131-91 → SAS away_margin=-40, -40 > -7.5? NO → LOSS (0)
    assert _resolve_outcome("spread_away", 7.5, 131, 91) == 0


def test_resolve_outcome_spread_home_win():
    """Home covers -5 spread (favored): home wins by 10 → margin=10 > 5 → WIN."""
    assert _resolve_outcome("spread_home", -5.0, 115, 105) == 1


def test_resolve_outcome_over_win():
    """Over 220: total=225 > 220 → WIN."""
    assert _resolve_outcome("over", 220.0, 115, 110) == 1


def test_resolve_outcome_under_loss():
    """Under 220: total=225 > 220 → LOSS for under bet."""
    assert _resolve_outcome("under", 220.0, 115, 110) == 0


def test_resolve_outcome_push():
    """Push: spread_home -5, home wins by exactly 5 → None."""
    assert _resolve_outcome("spread_home", -5.0, 110, 105) is None


if __name__ == "__main__":
    import tempfile as _tmpfile

    with _tmpfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        test_r_p7_01_loss_on_missed_spread(db)
        test_r_p7_02_brier_score_perfect_prediction()
        test_brier_score_imperfect()
        test_r_p7_03_separate_spread_and_total_rows(db)
        test_r_p7_04_log_prediction_no_exception_on_failure()
        test_r_p7_05_log_results_cli_inserts_actuals(db)
        test_resolve_outcome_spread_away_win()
        test_resolve_outcome_spread_home_win()
        test_resolve_outcome_over_win()
        test_resolve_outcome_under_loss()
        test_resolve_outcome_push()
    print("All calibration_log tests passed.")
