"""
Smart Retail — ML Predictor (Detrended HGBR v2)
================================================
Runs inference for a given Store_ID × Product_ID × target_date.
Applies the per-series log-linear trend to the HGBR residual prediction.
"""

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from smartretail.ml.trainer import get_state, FEAT_COLS, CAT_FEATURES, load_model

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_row(
    store_id: str,
    product_id: str,
    target_date: date,
    is_festival: int = 0,
    is_promotion: int = 0,
    discount_pct: float = 0.0,
    lag_365_residual: float = np.nan,
    rolling_mean_365_residual: float = np.nan,
    cat_enc: dict | None = None,
) -> dict:
    """Build a single feature row for inference."""
    d = pd.Timestamp(target_date)
    row: dict[str, Any] = {
        "day_of_week":              d.dayofweek,
        "month":                    d.month,
        "day_of_month":             d.day,
        "year":                     d.year,
        "week_of_year":             d.isocalendar().week,
        "Is_Festival":              is_festival,
        "Is_Promotion":             is_promotion,
        "Discount_Percent":         discount_pct,
        "lag_365_residual":         lag_365_residual,
        "rolling_mean_365_residual": rolling_mean_365_residual,
    }
    # Category encodings (default 0 if unknown)
    enc = cat_enc or {}
    for col in CAT_FEATURES:
        row[col + "_enc"] = enc.get(col + "_enc", 0)
    return row


def _trend_value(store_id: str, product_id: str, target_date: date, state: dict) -> float:
    """Extrapolate the log-linear trend to target_date."""
    key = (store_id, product_id)
    params = state.get("trend_params", {})
    day0   = state.get("day0", pd.Timestamp("2021-01-01"))

    if key not in params:
        return 0.0

    slope, intercept = params[key]
    day_ord = (pd.Timestamp(target_date) - day0).days
    return max(0.0, float(np.expm1(intercept + slope * day_ord)))


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def predict(
    store_id: str,
    product_id: str,
    target_date: date | str,
    is_festival: int = 0,
    is_promotion: int = 0,
    discount_pct: float = 0.0,
    lag_365_residual: float = np.nan,
    rolling_mean_365_residual: float = np.nan,
    cat_enc: dict | None = None,
) -> dict:
    """
    Predict Units_Sold for a single Store×Product×Date.

    Returns
    -------
    dict with keys:
        store_id, product_id, date, forecast_units,
        trend_component, residual_component, model_version
    """
    state = get_state()
    if not state:
        state = load_model() or {}
    if "model" not in state:
        return {"error": "Model not loaded. Please train first."}

    if isinstance(target_date, str):
        target_date = pd.Timestamp(target_date).date()

    model      = state["model"]
    feat_cols  = state.get("feat_cols", FEAT_COLS)

    trend = _trend_value(store_id, product_id, target_date, state)

    row  = _build_row(
        store_id, product_id, target_date,
        is_festival, is_promotion, discount_pct,
        lag_365_residual, rolling_mean_365_residual,
        cat_enc,
    )
    X    = np.array([[row.get(c, 0) for c in feat_cols]], dtype=float)
    resid = float(model.predict(X)[0])
    units = max(0.0, trend + resid)

    return {
        "store_id":           store_id,
        "product_id":         product_id,
        "date":               str(target_date),
        "forecast_units":     round(units, 2),
        "trend_component":    round(trend, 2),
        "residual_component": round(resid, 2),
        "model_version":      state.get("version", "detrended-hgbr-v2"),
    }


def predict_range(
    store_id: str,
    product_id: str,
    start_date: date | str,
    end_date: date | str,
    is_festival: int = 0,
    is_promotion: int = 0,
    discount_pct: float = 0.0,
    cat_enc: dict | None = None,
) -> list[dict]:
    """
    Predict Units_Sold for every day in [start_date, end_date].
    Lag features are NaN (model handles it natively via HGBR NaN support).
    """
    if isinstance(start_date, str):
        start_date = pd.Timestamp(start_date).date()
    if isinstance(end_date, str):
        end_date = pd.Timestamp(end_date).date()

    results = []
    cur = start_date
    while cur <= end_date:
        results.append(predict(
            store_id, product_id, cur,
            is_festival, is_promotion, discount_pct,
            cat_enc=cat_enc,
        ))
        cur += timedelta(days=1)
    return results


def get_model_info() -> dict:
    """Return metadata about the loaded model."""
    state = get_state()
    if not state:
        return {"status": "not_loaded"}
    return {
        "status":       "loaded",
        "version":      state.get("version", "unknown"),
        "split_date":   str(state.get("split_date", "unknown")),
        "metrics":      state.get("metrics", {}),
        "n_series":     len(state.get("trend_params", {})),
        "feature_cols": state.get("feat_cols", []),
    }
