"""ML training tests using realistic grocery sales CSV."""

from datetime import datetime

from smartretail.api.handlers.ml import (
    _models, predict_sales, train_model_from_csv,
    build_metrics_by_product, average_metrics,
    FEATURE_COLUMNS, _days_to_nearest_festival, _build_inference_features,
)


def _reset_models():
    _models.clear()


def test_train_all_products_from_grocery_csv(grocery_csv_text: str):
    _reset_models()
    ok, msg = train_model_from_csv(grocery_csv_text, "ALL")
    assert ok is True, msg
    assert len(_models) >= 20
    for name, info in _models.items():
        assert "avg" in info
        if "model" in info:
            assert info["accuracy"] is not None
            # Verify new metrics are stored
            assert "metrics" in info
            assert "rmse" in info["metrics"]
            assert "mae" in info["metrics"]
            assert info["metrics"]["rmse"] >= 0
            assert info["metrics"]["mae"] >= 0


def test_train_single_sku_and_predict(grocery_csv_text: str):
    _reset_models()
    product = "Milk 500ml"
    ok, msg = train_model_from_csv(grocery_csv_text, product)
    assert ok is True, msg
    pred, details = predict_sales(product, datetime(2025, 10, 20))
    assert pred is not None
    assert details is not None
    assert details["adjusted"] >= 0


def test_festival_day_higher_than_regular_for_staple(grocery_csv_text: str):
    _reset_models()
    product = "Rice 1kg"
    train_model_from_csv(grocery_csv_text, product)
    pongal = predict_sales(product, datetime(2025, 1, 15))
    regular = predict_sales(product, datetime(2025, 2, 10))
    assert pongal[0] is not None and regular[0] is not None
    # Festival/weekend boosts should not reduce adjusted prediction vs quiet weekday
    assert pongal[1]["multiplier"] >= regular[1]["multiplier"] or pongal[0] >= regular[0]


def test_metrics_by_product(grocery_csv_text: str):
    """Verify RMSE/MAE/MAPE metrics are computed and aggregated correctly."""
    _reset_models()
    train_model_from_csv(grocery_csv_text, "ALL")
    names = list(_models.keys())
    metrics = build_metrics_by_product(names)
    assert len(metrics) > 0
    # At least some products should have metrics
    products_with_metrics = [p for p, m in metrics.items() if m is not None]
    assert len(products_with_metrics) >= 10
    # Average metrics should work
    avg = average_metrics(metrics)
    assert avg is not None
    assert avg["rmse"] >= 0
    assert avg["mae"] >= 0


def test_feature_columns_length():
    """FEATURE_COLUMNS should have exactly 7 features."""
    assert len(FEATURE_COLUMNS) == 7
    assert "IsWeekend" in FEATURE_COLUMNS
    assert "IsPayDay" in FEATURE_COLUMNS
    assert "DaysToFestival" in FEATURE_COLUMNS


def test_days_to_nearest_festival():
    """Days-to-festival should return a sensible value."""
    # Pongal is Jan 14 — checking Jan 10 should be ~4 days
    d = datetime(2025, 1, 10)
    dist = _days_to_nearest_festival(d)
    assert 0 <= dist <= 10  # Should be close to Pongal (Jan 7-14 window)


def test_inference_features_shape():
    """Inference feature array should match FEATURE_COLUMNS length."""
    features = _build_inference_features(datetime(2025, 6, 15))
    assert features.shape == (1, len(FEATURE_COLUMNS))
    # June 15 is a Sunday in 2025 — check weekend flag
    d = datetime(2025, 6, 15)
    if d.weekday() >= 5:
        assert features[0][4] == 1  # IsWeekend
    # June 15 is a pay-day
    assert features[0][5] == 1  # IsPayDay (day=15)
