"""Unit tests for festival and demand multiplier logic."""

from datetime import datetime

from smartretail.api.handlers.ml import FESTIVALS, get_demand_multiplier, is_festival_period


def test_pongal_window_detected():
    d = datetime(2025, 1, 15)
    is_fest, name, mult = is_festival_period(d)
    assert is_fest is True
    assert name is not None
    assert mult >= 1.0


def test_regular_weekday_no_festival_boost_name():
    d = datetime(2025, 2, 10)
    is_fest, name, _ = is_festival_period(d)
    if not is_fest:
        assert name is None


def test_weekend_demand_multiplier():
    saturday = datetime(2025, 3, 8)
    mult, boosts = get_demand_multiplier(saturday)
    assert mult >= 1.15
    assert any("Weekend" in b for b in boosts)


def test_festival_catalog_not_empty():
    assert len(FESTIVALS) >= 20
    for entry in FESTIVALS[:3]:
        assert len(entry) == 6
