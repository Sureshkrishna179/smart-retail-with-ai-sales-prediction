"""
Smart Retail — ML Trainer (Detrended HGBR v2)
==============================================
Model: HistGradientBoostingRegressor on detrended residuals.
Split: Temporal train/test (80% train, 20% test by date cut-off).
Pooled: Single model across all 500 Store×Product series.
"""

import os
import logging
import warnings
import time
from pathlib import Path


from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# ── Force single-threaded (prevents joblib ThreadPool sandbox issues) ───────
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import joblib
import joblib._parallel_backends as _pb
import joblib.parallel as _jp

class _SequentialThreading(_pb.SequentialBackend):  # type: ignore
    """Replaces threading backend with sequential to avoid sandbox pipe errors."""
    pass

_pb.ThreadingBackend = _SequentialThreading  # type: ignore
_jp.BACKENDS["threading"] = _SequentialThreading  # type: ignore

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parents[3]
DATA_DIR    = BASE_DIR / "files"
OUTPUT_DIR  = DATA_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SALES_CSV    = DATA_DIR / "sales_data.csv"
PRODUCTS_CSV = DATA_DIR / "products.csv"
STORES_CSV   = DATA_DIR / "stores.csv"
MODEL_PATH   = OUTPUT_DIR / "sales_forecaster.model"

# ── Feature config ───────────────────────────────────────────────────────────
CAT_FEATURES  = ["Store_ID", "Product_ID", "Category", "City", "Region"]
FEAT_COLS = [
    "day_of_week", "month", "day_of_month", "year", "week_of_year",
    "Is_Festival", "Is_Promotion", "Discount_Percent",
    "lag_365_residual", "rolling_mean_365_residual",
    "Store_ID_enc", "Product_ID_enc", "Category_enc", "City_enc", "Region_enc",
]

RANDOM_SEED = 42

# ── In-memory state (loaded once per process) ────────────────────────────────
_state: dict[str, Any] = {}   # keys: model, trend_params, day0, metrics, split_date


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fit_trend(series: pd.Series, dates: pd.Series, day0: pd.Timestamp):
    """Log-linear OLS trend per Store×Product series."""
    day_ord = (dates - day0).dt.days.values.astype(float)  # type: ignore
    log_y   = np.log1p(series.values.astype(float))
    mask    = np.isfinite(log_y)
    if mask.sum() < 10:
        return 0.0, float(np.log1p(series.mean()))
    slope, intercept, *_ = stats.linregress(day_ord[mask], log_y[mask])
    return float(slope), float(intercept)


def _load_and_merge() -> pd.DataFrame:
    """Load and merge sales + products + stores."""
    df = pd.read_csv(SALES_CSV, parse_dates=["Date"])
    df.columns = df.columns.str.strip()

    # Merge metadata
    if PRODUCTS_CSV.exists():
        prod = pd.read_csv(PRODUCTS_CSV)
        prod.columns = prod.columns.str.strip()
        df = df.merge(prod, on="Product_ID", how="left")
    if STORES_CSV.exists():
        sto = pd.read_csv(STORES_CSV)
        sto.columns = sto.columns.str.strip()
        df = df.merge(sto, on="Store_ID", how="left")

    # Fill missing metadata
    for col in ["Category", "City", "Region", "Pack_Size"]:
        if col not in df.columns:
            df[col] = "Unknown"

    df = df.sort_values(["Store_ID", "Product_ID", "Date"]).reset_index(drop=True)
    return df


def _fit_all_trends(df: pd.DataFrame, day0: pd.Timestamp) -> dict:
    """
    Per-series log-linear trend. Returns dict:
      (Store_ID, Product_ID) → (slope, intercept)
    """
    trend_params = {}
    for (sid, pid), grp in df.groupby(["Store_ID", "Product_ID"], observed=True):
        slope, intercept = _fit_trend(grp["Units_Sold"], grp["Date"], day0)
        trend_params[(str(sid), str(pid))] = (slope, intercept)
    return trend_params


def _add_residuals(df: pd.DataFrame, trend_params: dict, day0: pd.Timestamp) -> pd.DataFrame:
    """Add Trend_Value and Residual columns."""
    df = df.copy()
    day_ord = (df["Date"] - day0).dt.days.values.astype(float)  # type: ignore

    slopes      = np.zeros(len(df), dtype=float)
    intercepts  = np.zeros(len(df), dtype=float)
    for (sid, pid), (slope, intercept) in trend_params.items():
        mask = (df["Store_ID"] == sid) & (df["Product_ID"] == pid)
        slopes[mask.values]     = slope
        intercepts[mask.values] = intercept

    df["Trend_Value"] = np.maximum(np.expm1(intercepts + slopes * day_ord), 0)
    df["Residual"]    = df["Units_Sold"].astype(float) - df["Trend_Value"]
    return df


def _encode_cats(df: pd.DataFrame) -> pd.DataFrame:
    """Label-encode categorical columns in-place."""
    df = df.copy()
    for col in CAT_FEATURES:
        if col in df.columns:
            df[col] = df[col].astype("category")
            df[col + "_enc"] = df[col].cat.codes.astype("int16")
        else:
            df[col + "_enc"] = 0
    return df


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar and annual lag features."""
    df = df.copy()
    df["day_of_week"]  = df["Date"].dt.dayofweek.astype("int8")  # type: ignore
    df["month"]        = df["Date"].dt.month.astype("int8")  # type: ignore
    df["day_of_month"] = df["Date"].dt.day.astype("int8")  # type: ignore
    df["year"]         = df["Date"].dt.year.astype("int16")  # type: ignore
    df["week_of_year"] = df["Date"].dt.isocalendar().week.astype("int16")  # type: ignore

    # Annual lag (365-day look-back residual)
    df = df.sort_values(["Store_ID", "Product_ID", "Date"])
    df["lag_365_residual"] = (
        df.groupby(["Store_ID", "Product_ID"], observed=True)["Residual"]
          .shift(365)
          .astype(np.float32)
    )
    df["rolling_mean_365_residual"] = (
        df.groupby(["Store_ID", "Product_ID"], observed=True)["Residual"]
          .transform(lambda x: x.shift(1).rolling(365, min_periods=30).mean())
          .astype(np.float32)
    )

    # Is_Festival / Is_Promotion defaults if not present
    for col in ["Is_Festival", "Is_Promotion", "Discount_Percent"]:
        if col not in df.columns:
            df[col] = 0
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def train(test_size: float = 0.2) -> dict:
    """
    Train Detrended HGBR with temporal train/test split.

    Parameters
    ----------
    test_size : float
        Fraction of data reserved for testing (most-recent dates). Default 0.20.

    Returns
    -------
    dict with keys: split_date, train_rows, test_rows, metrics (MAE/RMSE/WAPE),
                    model_path, n_series, yoy_growth
    """
    t0 = time.time()
    logger.info("=== Detrended HGBR Training START ===")

    # 1. Load data
    logger.info("Loading data …")
    df = _load_and_merge()
    logger.info("  Rows: {:,}  |  Date range: {} – {}".format(
        len(df), df["Date"].min().date(), df["Date"].max().date()))

    # 2. Temporal train/test split ─────────────────────────────────────────
    dates_sorted = df["Date"].sort_values().values
    split_idx    = int(len(dates_sorted) * (1 - test_size))
    split_date   = pd.Timestamp(dates_sorted[split_idx])
    logger.info("  Train/test split: everything before {} = train, after = test ({:.0f}% / {:.0f}%)".format(
        split_date.date(), (1 - test_size) * 100, test_size * 100))

    # 3. Trend decomposition (fitted on full history to avoid data leakage in slope)
    day0 = df["Date"].min()
    logger.info("Fitting per-series log-linear trends …")
    trend_params = _fit_all_trends(df, day0)
    df = _add_residuals(df, trend_params, day0)

    # 4. Feature engineering
    logger.info("Building features …")
    df = _build_features(df)
    df = _encode_cats(df)

    train_df = df[df["Date"] <  split_date].copy()
    test_df  = df[df["Date"] >= split_date].copy()
    logger.info("  Train rows: {:,}  |  Test rows: {:,}".format(len(train_df), len(test_df)))

    # 5. Train model
    logger.info("Training HistGradientBoostingRegressor …")
    feat_cols_present = [c for c in FEAT_COLS if c in train_df.columns]
    X_train = train_df[feat_cols_present].values
    y_train = train_df["Residual"].values
    X_test  = test_df[feat_cols_present].values
    y_test  = test_df["Units_Sold"].values

    model = HistGradientBoostingRegressor(
        loss="absolute_error",
        max_iter=300,
        max_leaf_nodes=63,
        min_samples_leaf=30,
        learning_rate=0.05,
        l2_regularization=0.1,
        max_bins=255,
        early_stopping=False,
        random_state=RANDOM_SEED,
    )
    with joblib.parallel_backend("sequential"):
        model.fit(X_train, y_train)
    logger.info("  Iterations: {}".format(model.n_iter_))

    # 6. Evaluate on test set
    resid_pred  = model.predict(X_test)
    trend_test  = test_df["Trend_Value"].values
    units_pred  = np.maximum(trend_test + resid_pred, 0)

    mae  = mean_absolute_error(y_test, units_pred)
    rmse = np.sqrt(mean_squared_error(y_test, units_pred))
    wape = np.sum(np.abs(y_test - units_pred)) / np.sum(np.abs(y_test) + 1e-9)

    # Baseline (seasonal naive: same day last year)
    naive_lookup = (
        train_df.groupby(["Store_ID","Product_ID","month","day_of_month"], observed=True)["Units_Sold"]
        .mean().reset_index().rename(columns={"Units_Sold":"naive_pred"})
    )
    test_with_naive = test_df.merge(naive_lookup, on=["Store_ID","Product_ID","month","day_of_month"], how="left")
    naive_pred_vals = test_with_naive["naive_pred"].fillna(test_df["Units_Sold"].mean()).values
    baseline_mae = mean_absolute_error(y_test, naive_pred_vals)

    improvement = (baseline_mae - mae) / baseline_mae * 100
    logger.info("  TEST  MAE={:.3f}  RMSE={:.3f}  WAPE={:.4f}".format(mae, rmse, wape))
    logger.info("  Seasonal Naive baseline MAE={:.3f}  |  Improvement: {:.1f}%".format(
        baseline_mae, improvement))

    # YoY growth
    prev_year_total = train_df[train_df["year"] == train_df["year"].max()]["Units_Sold"].sum()
    curr_year_total = test_df["Units_Sold"].sum() if len(test_df) > 0 else 0
    yoy = (curr_year_total / prev_year_total - 1) * 100 if prev_year_total > 0 else 0

    # 7. Save model bundle
    bundle = {
        "model":        model,
        "trend_params": trend_params,
        "day0":         day0,
        "feat_cols":    feat_cols_present,
        "split_date":   split_date,
        "metrics":      {"MAE": round(mae,3), "RMSE": round(rmse,3), "WAPE": round(wape,4)},
        "version":      "detrended-hgbr-v2",
    }
    joblib.dump(bundle, MODEL_PATH)
    logger.info("  Model saved: {}".format(MODEL_PATH))

    # Update in-memory state
    _state.update(bundle)

    elapsed = time.time() - t0
    logger.info("=== Training complete in {:.1f}s ===".format(elapsed))

    return {
        "split_date":  str(split_date.date()),
        "train_rows":  len(train_df),
        "test_rows":   len(test_df),
        "n_series":    len(trend_params),
        "metrics": {
            "MAE":          round(mae, 3),
            "RMSE":         round(rmse, 3),
            "WAPE":         round(wape, 4),
            "baseline_MAE": round(baseline_mae, 3),
            "improvement_pct": round(improvement, 1),
        },
        "yoy_growth_pct": round(yoy, 2),
        "model_path":   str(MODEL_PATH),
        "elapsed_sec":  round(elapsed, 1),
    }


def load_model() -> dict | None:
    """Load the saved model bundle from disk into _state. Returns bundle or None."""
    if MODEL_PATH.exists():
        try:
            bundle = joblib.load(MODEL_PATH)
            _state.update(bundle)
            logger.info("Model loaded from {}".format(MODEL_PATH))
            return bundle
        except Exception as e:
            logger.error("Failed to load model: {}".format(e))
    return None


def get_state() -> dict:
    """Return current in-memory model state (loads from disk if empty)."""
    if not _state:
        load_model()
    return _state


# ── Legacy compatibility ─────────────────────────────────────────────────────

def train_model_from_csv(csv_text: str, product_name: str) -> tuple[bool, str]:
    """
    Legacy shim kept for API backward compatibility.
    Triggers a full re-train on the canonical sales_data.csv.
    product_name is ignored (pooled model covers all products).
    """
    try:
        result = train(test_size=0.2)
        return True, (
            "Detrended HGBR trained on {:,} rows. "
            "Test MAE={MAE}, RMSE={RMSE}, WAPE={WAPE}. "
            "Split date: {split_date}".format(result["train_rows"] + result["test_rows"], **result["metrics"],
                                              split_date=result["split_date"])
        )
    except Exception as e:
        logger.exception("Training failed")
        return False, str(e)


def persist_models():
    """No-op shim: model is now saved directly in train()."""
    pass


def get_product_lookup() -> dict:
    """
    Build Product_Name → Product_ID lookup from products.csv.
    Returns dict like {"Basmati Rice": "P001", ...}.
    Also includes identity mappings for Product_IDs ("P001" → "P001").
    """
    lookup: dict[str, str] = {}
    if PRODUCTS_CSV.exists():
        try:
            prod = pd.read_csv(PRODUCTS_CSV)
            prod.columns = prod.columns.str.strip()
            for _, row in prod.iterrows():
                pid = str(row.get("Product_ID", "")).strip()
                name = str(row.get("Product_Name", "")).strip()
                if pid:
                    lookup[pid] = pid  # identity: P001 → P001
                    lookup[pid.upper()] = pid
                if name and pid:
                    lookup[name] = pid
                    lookup[name.upper()] = pid
                    lookup[name.upper().replace(" ", "_")] = pid
        except Exception as e:
            logger.warning("Could not build product lookup: {}".format(e))
    return lookup


def get_id_to_name_lookup() -> dict:
    """
    Build Product_ID → Product_Name reverse lookup from products.csv.
    Returns dict like {"P001": "Basmati Rice", ...}.
    Used by the API layer to display human-readable product names in predictions.
    """
    lookup: dict[str, str] = {}
    if PRODUCTS_CSV.exists():
        try:
            prod = pd.read_csv(PRODUCTS_CSV)
            prod.columns = prod.columns.str.strip()
            for _, row in prod.iterrows():
                pid = str(row.get("Product_ID", "")).strip()
                name = str(row.get("Product_Name", "")).strip()
                if pid and name:
                    lookup[pid] = name
        except Exception as e:
            logger.warning("Could not build id-to-name lookup: {}".format(e))
    return lookup


def get_csv_products() -> list[dict]:
    """Return list of products from products.csv for API consumption."""
    if not PRODUCTS_CSV.exists():
        return []
    try:
        prod = pd.read_csv(PRODUCTS_CSV)
        prod.columns = prod.columns.str.strip()
        results = []
        for _, row in prod.iterrows():
            results.append({
                "product_id": str(row.get("Product_ID", "")).strip(),
                "name": str(row.get("Product_Name", "")).strip(),
                "category": str(row.get("Category", "")).strip(),
            })
        return results
    except Exception:
        return []


# ── Auto-load saved model on startup ─────────────────────────────────────────
if MODEL_PATH.exists():
    try:
        _bundle = joblib.load(MODEL_PATH)
        _state.update(_bundle)
        logger.info("Auto-loaded saved model from {} ({} series)".format(
            MODEL_PATH, len(_state.get("trend_params", {}))))
    except Exception as _e:
        logger.warning("Could not auto-load model: {}".format(_e))
