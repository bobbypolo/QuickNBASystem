# Tests R-P4-01 through R-P4-05
from calibration import haircut_prob, spread_underdog_cap


def test_spread_cap_large_spread():
    """R-P4-01: spread_underdog_cap(0.70, 13.5) returns exactly 0.50."""
    assert spread_underdog_cap(0.70, 13.5) == 0.50


def test_spread_cap_medium_spread():
    """R-P4-02: spread_underdog_cap(0.70, 10.5) returns exactly 0.52."""
    assert spread_underdog_cap(0.70, 10.5) == 0.52


def test_spread_cap_small_spread_no_cap():
    """R-P4-03: spread_underdog_cap(0.58, 5.0) returns 0.58 (no cap)."""
    assert spread_underdog_cap(0.58, 5.0) == 0.58


def test_spread_cap_zero_spread_no_cap():
    """Zero spread: no cap applied."""
    assert spread_underdog_cap(0.65, 0.0) == 0.65


def test_spread_cap_prob_already_low():
    """Large spread but prob already below cap: unchanged."""
    assert spread_underdog_cap(0.45, 15.0) == 0.45


def test_haircut_standard():
    """R-P4-04: haircut_prob(0.60, 10_000, k=1.5) returns value in [0.585, 0.595]."""
    result = haircut_prob(0.60, 10_000, k=1.5)
    assert 0.585 < result < 0.595, f"Expected ~0.593, got {result}"


def test_haircut_zero_prob():
    """R-P4-05: haircut_prob(0.0, 10_000) returns 0.0 (floor enforced)."""
    assert haircut_prob(0.0, 10_000) == 0.0


def test_haircut_one_prob():
    """haircut_prob(1.0, 10_000): stderr=0, returns 1.0."""
    assert haircut_prob(1.0, 10_000) == 1.0


def test_haircut_reduces_prob():
    """Haircut is always <= raw prob for p in (0, 1)."""
    for p in [0.51, 0.55, 0.60, 0.65, 0.70]:
        assert haircut_prob(p, 10_000) <= p


if __name__ == "__main__":
    test_spread_cap_large_spread()
    test_spread_cap_medium_spread()
    test_spread_cap_small_spread_no_cap()
    test_spread_cap_zero_spread_no_cap()
    test_spread_cap_prob_already_low()
    test_haircut_standard()
    test_haircut_zero_prob()
    test_haircut_one_prob()
    test_haircut_reduces_prob()
    print("All calibration tests passed.")
