# Tests R-P1-07, R-P1-08, R-P1-09
from run_tonight import _spread_confidence_cap


def test_cap_large_spread():
    """R-P1-07: abs_spread >= 13 caps at 0.50."""
    result = _spread_confidence_cap(0.75, 13.5)
    assert result == 0.50, f"Expected 0.50, got {result}"


def test_cap_medium_spread():
    """R-P1-08: abs_spread in [10, 13) caps at 0.52."""
    result = _spread_confidence_cap(0.75, 10.5)
    assert result == 0.52, f"Expected 0.52, got {result}"


def test_no_cap_small_spread():
    """R-P1-09: abs_spread < 8 → no cap, returns raw_prob."""
    result = _spread_confidence_cap(0.58, 6.0)
    assert result == 0.58, f"Expected 0.58, got {result}"


def test_cap_boundary_13():
    """Exactly 13.0 → hard cap at 0.50."""
    result = _spread_confidence_cap(0.70, 13.0)
    assert result == 0.50


def test_cap_boundary_10():
    """Exactly 10.0 → cap at 0.52."""
    result = _spread_confidence_cap(0.70, 10.0)
    assert result == 0.52


def test_cap_boundary_8():
    """Exactly 8.0 → cap at 0.56."""
    result = _spread_confidence_cap(0.70, 8.0)
    assert result == 0.56


def test_no_cap_below_threshold():
    """prob already below cap → returns raw_prob unchanged."""
    result = _spread_confidence_cap(0.45, 14.0)
    assert result == 0.45
