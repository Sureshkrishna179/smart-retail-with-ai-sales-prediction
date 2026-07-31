"""
Detrended Gradient Boosting Sales Forecasting Pipeline  (v2.1)
===============================================================
Phases:
  1  – Load & merge sales_data, products, stores
  2  – Per-series log-linear trend decomposition  →  Trend_Value, Residual
  3  – Feature engineering (calendar + festival + promo + lag_365/rolling_365)
  4  – Train 4 models: Seasonal Naive, RF, Plain HGBR, Detrended HGBR
  5  – Validate on 2025 holdout → MAE / RMSE / WAPE / SMAPE
  6  – Build 2026 grid, impute promos, extrapolate trend, generate forecast
  7  – Save all outputs to files/output/

Uses sklearn.HistGradientBoostingRegressor (histogram-based gradient boosting
identical in principle to LightGBM — handles NaN natively, fast, no external deps).
Matplotlib used for charts if available; otherwise chart data saved as CSV.
"""

import os
import sys
import time
import warnings
import logging
import traceback

# ── Force single-threaded execution (sandbox blocks all IPC/threading) ─────
os.environ["LOKY_MAX_CPU_COUNT"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib
import joblib._parallel_backends as _pb
import joblib.parallel as _jp

# Replace the threading backend with sequential so HGBR's internal
# Parallel(backend="threading") calls don't spawn ThreadPool (which needs
# named pipes that the Windows sandbox blocks).
class _FakeThreadingBackend(_pb.SequentialBackend):
    """Drop-in sequential replacement for the threading backend."""
    pass

_pb.ThreadingBackend = _FakeThreadingBackend  # type: ignore
_jp.BACKENDS["threading"] = _FakeThreadingBackend  # type: ignore

warnings.filterwarnings("ignore")

# ── Optional matplotlib ────────────────────────────────────────────────────
try:
    import matplotlib  # type: ignore
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    import matplotlib.dates as mdates  # type: ignore
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
BASE   = r"c:\MY Projects\Project AI Sales"
FILES  = os.path.join(BASE, "files")
OUTPUT = os.path.join(FILES, "output")
os.makedirs(OUTPUT, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(OUTPUT, "run.log"), mode="w"),
    ],
)
log = logging.getLogger(__name__)

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# ─────────────────────────────────────────────
# PHASE 1 – Load & Merge
# ─────────────────────────────────────────────

def load_data():
    log.info("Phase 1 – Loading data …")
    t0 = time.time()

    sales = pd.read_csv(
        os.path.join(FILES, "sales_data.csv"),
        parse_dates=["Date"],
        dtype={
            "Store_ID":    "category",
            "Product_ID":  "category",
            "Is_Festival": "int8",
            "Is_Promotion":"int8",
        },
    )
    products = pd.read_csv(os.path.join(FILES, "products.csv"))
    stores   = pd.read_csv(os.path.join(FILES, "stores.csv"))
    cal26    = pd.read_csv(
        os.path.join(FILES, "tn_calendar_2026.csv"),
        parse_dates=["Date"],
        dtype={"Is_Holiday":"int8","Is_Shopping_Season":"int8","Is_Local_Festival":"int8"},
    )

    df = sales.merge(
        products[["Product_ID","Category","Pack_Size","Base_Price_2021_INR"]],
        on="Product_ID", how="left"
    )
    df = df.merge(stores[["Store_ID","City","Region"]], on="Store_ID", how="left")

    for col in ["Category","City","Region"]:
        df[col] = df[col].astype("category")

    log.info("  Rows: {:,}  |  Date range: {} – {}  |  elapsed {:.1f}s".format(
        len(df), df["Date"].min().date(), df["Date"].max().date(), time.time()-t0))
    return df, cal26


# ─────────────────────────────────────────────
# PHASE 2 – Trend Decomposition
# ─────────────────────────────────────────────

def fit_trends(df):
    """
    Per Store×Product:
      fit OLS on log(Units_Sold+1) vs ordinal day  →  log-linear growth trend
      Trend_Value = expm1(fitted_log)
      Residual    = Units_Sold − Trend_Value
    Returns df + trend_params dict for 2026 extrapolation.
    """
    log.info("Phase 2 – Trend decomposition …")
    t0 = time.time()

    df = df.sort_values(["Store_ID","Product_ID","Date"]).copy()
    df["log_units"] = np.log1p(df["Units_Sold"].clip(lower=0))

    day0 = df["Date"].min()
    df["day_ord"] = (df["Date"] - day0).dt.days.astype(np.float32)

    trend_vals  = np.empty(len(df), dtype=np.float32)
    trend_params = {}

    for (store, prod), grp in df.groupby(["Store_ID","Product_ID"], observed=True):
        x = grp["day_ord"].values
        y = grp["log_units"].values

        if len(x) < 30:
            slope, intercept = 0.0, float(y.mean())
        else:
            slope, intercept, *_ = stats.linregress(x, y)

        fitted_log   = intercept + slope * x
        fitted_units = np.expm1(fitted_log)

        idx = grp.index
        trend_vals[df.index.get_indexer(idx)] = fitted_units
        trend_params[(store, prod)] = (slope, intercept, day0)

    df["Trend_Value"] = trend_vals.clip(min=0)
    df["Residual"]    = (df["Units_Sold"] - df["Trend_Value"]).astype(np.float32)

    log.info("  Trend fitted for {:,} series  |  elapsed {:.1f}s".format(
        len(trend_params), time.time()-t0))
    return df, trend_params


# ─────────────────────────────────────────────
# PHASE 3 – Feature Engineering
# ─────────────────────────────────────────────

CAT_FEATURES = ["Store_ID","Product_ID","Category","Region"]

def build_features(df, include_short_lags=False):
    log.info("  Building features (short_lags={}) …".format(include_short_lags))
    t0 = time.time()

    df = df.sort_values(["Store_ID","Product_ID","Date"]).copy()

    # Calendar
    df["day_of_week"]  = df["Date"].dt.dayofweek.astype("int8")
    df["month"]        = df["Date"].dt.month.astype("int8")
    df["day_of_month"] = df["Date"].dt.day.astype("int8")
    df["year"]         = df["Date"].dt.year.astype("int16")
    df["week_of_year"] = df["Date"].dt.isocalendar().week.astype("int8")

    # Annual lag/rolling — always anchored to real history, never recursive
    grp = df.groupby(["Store_ID","Product_ID"], observed=True)["Residual"]
    df["lag_365_residual"] = grp.shift(365).astype(np.float32)
    df["rolling_mean_365_residual"] = (
        grp.transform(lambda s: s.shift(365).rolling(365, min_periods=30).mean())
        .astype(np.float32)
    )

    if include_short_lags:
        for lag in [7, 14, 30]:
            df[f"lag_{lag}_residual"] = (
                df.groupby(["Store_ID","Product_ID"], observed=True)["Residual"]
                .shift(lag).astype(np.float32)
            )
        for window in [7, 30]:
            df[f"rolling_mean_{window}_residual"] = (
                df.groupby(["Store_ID","Product_ID"], observed=True)["Residual"]
                .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
                .astype(np.float32)
            )

    log.info("  Features built  |  elapsed {:.1f}s".format(time.time()-t0))
    return df


def encode_cats(df):
    for col in CAT_FEATURES:
        # Re-cast to category if sort/copy demoted it to object
        if df[col].dtype.name != "category":
            df[col] = df[col].astype("category")
        df[col+"_enc"] = df[col].cat.codes.astype("int16")
    return df


def get_feature_cols(df, include_short_lags=False):
    base = [
        "day_of_week","month","day_of_month","year","week_of_year",
        "Is_Festival","Is_Promotion","Discount_Percent",
        "lag_365_residual","rolling_mean_365_residual",
    ]
    if include_short_lags:
        short = [c for c in df.columns
                 if (c.startswith("lag_") or c.startswith("rolling_mean_"))
                 and c not in base]
        base = base + short
    enc = [c+"_enc" for c in CAT_FEATURES if c+"_enc" in df.columns]
    return base + enc


# ─────────────────────────────────────────────
# PHASE 4 – Models
# ─────────────────────────────────────────────

def wape(y_true, y_pred):
    denom = np.abs(y_true).sum()
    return np.nan if denom == 0 else np.abs(y_true - y_pred).sum() / denom

def smape(y_true, y_pred):
    mask = (np.abs(y_true) + np.abs(y_pred)) > 0
    if mask.sum() == 0:
        return np.nan
    return 2 * np.abs(y_true[mask]-y_pred[mask]).sum() / (
        np.abs(y_true[mask]) + np.abs(y_pred[mask])
    ).sum()

def evaluate(name, y_true, y_pred):
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    mae_   = mean_absolute_error(y_true, y_pred)
    rmse_  = np.sqrt(mean_squared_error(y_true, y_pred))
    wape_  = wape(y_true, y_pred)
    smape_ = smape(y_true, y_pred)
    log.info("  {:35s}  MAE={:.3f}  RMSE={:.3f}  WAPE={:.4f}  SMAPE={:.4f}".format(
        name, mae_, rmse_, wape_, smape_))
    return {"model":name, "MAE":mae_, "RMSE":rmse_, "WAPE":wape_, "SMAPE":smape_}

# ── Seasonal Naive ─────────────────────────────────────────────────────────

def seasonal_naive(train, val):
    log.info("  Training Seasonal Naive …")
    t = train.copy()
    t["month"] = t["Date"].dt.month
    t["dom"]   = t["Date"].dt.day

    lookup = (
        t.groupby(["Store_ID","Product_ID","month","dom"], observed=True)["Units_Sold"]
        .mean().reset_index().rename(columns={"Units_Sold":"naive_pred"})
    )
    fallback = (
        t.groupby(["Store_ID","Product_ID","month"], observed=True)["Units_Sold"]
        .mean().reset_index().rename(columns={"Units_Sold":"naive_fallback"})
    )

    v = val.copy()
    v["month"] = v["Date"].dt.month
    v["dom"]   = v["Date"].dt.day
    v = v.merge(lookup,   on=["Store_ID","Product_ID","month","dom"], how="left")
    v = v.merge(fallback, on=["Store_ID","Product_ID","month"],       how="left")
    v["naive_pred"] = (v["naive_pred"]
                       .fillna(v["naive_fallback"])
                       .fillna(v["Units_Sold"].mean()))
    return v["naive_pred"].values

# ── HistGradientBoostingRegressor helpers ──────────────────────────────────

def train_hgbr(X_train, y_train, X_val=None, y_val=None, **extra_params):
    """Histogram-based GB — same algorithm as LightGBM. Forced single-threaded."""
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
    log.info("    -> {} iterations done".format(model.n_iter_))
    return model



# ─────────────────────────────────────────────
# Charting (matplotlib optional)
# ─────────────────────────────────────────────

def plot_validation(val_df, pred_det):
    if not HAS_MPL:
        # Save daily aggregated data as CSV instead
        daily = val_df.copy()
        daily["pred"] = pred_det
        out_csv = os.path.join(OUTPUT, "validation_actual_vs_predicted.csv")
        daily.groupby("Date")[["Units_Sold","pred"]].sum().to_csv(out_csv)
        log.info("  matplotlib not available — chart data saved: {}".format(out_csv))
        return

    log.info("  Generating validation chart …")
    daily = val_df.copy()
    daily["pred"] = pred_det
    daily = daily.groupby("Date")[["Units_Sold","pred"]].sum().reset_index()

    fig, ax = plt.subplots(figsize=(18, 6))
    ax.plot(daily["Date"], daily["Units_Sold"], lw=1.5, color="#2196F3", label="Actual 2025")
    ax.plot(daily["Date"], daily["pred"],       lw=1.5, color="#FF5722", alpha=0.85,
            label="Detrended HGBR Forecast")

    for d in val_df[val_df["Is_Festival"]==1]["Date"].unique():
        ax.axvline(d, color="green", alpha=0.15, lw=1)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)
    ax.set_title("2025 Validation — Actual vs. Forecast (all stores × products)", fontsize=14)
    ax.set_ylabel("Total Daily Units Sold")
    ax.legend(); ax.grid(True, alpha=0.3); fig.tight_layout()
    out = os.path.join(OUTPUT, "validation_actual_vs_predicted.png")
    fig.savefig(out, dpi=150); plt.close()
    log.info("  Saved: {}".format(out))


def plot_forecast_spikes(forecast_df, cal26):
    if not HAS_MPL:
        out_csv = os.path.join(OUTPUT, "forecast_2026_spikes.csv")
        forecast_df.groupby("Date")["Forecast_Units"].sum().to_csv(out_csv)
        log.info("  matplotlib not available — spike data saved: {}".format(out_csv))
        return

    log.info("  Generating 2026 forecast spike chart …")
    daily = forecast_df.groupby("Date")["Forecast_Units"].sum().reset_index()
    cal_m = cal26[["Date","Is_Shopping_Season","Is_Local_Festival","Is_Holiday"]].copy()
    daily = daily.merge(cal_m, on="Date", how="left").fillna(0)

    fig, ax = plt.subplots(figsize=(20, 6))
    ax.plot(daily["Date"], daily["Forecast_Units"], lw=1.5, color="#9C27B0",
            label="2026 Forecast (all series)")

    in_season = False
    start = None
    for _, row in daily.iterrows():
        if row["Is_Shopping_Season"] == 1 and not in_season:
            start = row["Date"]; in_season = True
        elif row["Is_Shopping_Season"] == 0 and in_season:
            ax.axvspan(start, row["Date"], alpha=0.12, color="gold", label="Shopping Season")
            in_season = False
    if in_season and start is not None:
        ax.axvspan(start, daily["Date"].iloc[-1], alpha=0.12, color="gold")

    for d in daily[daily["Is_Local_Festival"]==1]["Date"]:
        ax.axvline(d, color="red", alpha=0.25, lw=1.5)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)
    ax.set_title("2026 Sales Forecast — All Stores × Products (Detrended HGBR)", fontsize=14)
    ax.set_ylabel("Total Daily Units Sold")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(dict(zip(labels, handles)).values(), dict(zip(labels, handles)).keys())
    ax.grid(True, alpha=0.3); fig.tight_layout()
    out = os.path.join(OUTPUT, "forecast_2026_spikes.png")
    fig.savefig(out, dpi=150); plt.close()
    log.info("  Saved: {}".format(out))


# ─────────────────────────────────────────────
# PHASE 6 – 2026 Forecast Grid
# ─────────────────────────────────────────────

def compute_promo_rates(df):
    """
    Per (Category, is_festival_str): (promo_rate, avg_discount_when_promoted)
    """
    df = df.copy()
    df["fest_key"] = df["Is_Festival"].astype(str)
    rates = {}
    for (cat, fk), g in df.groupby(["Category","fest_key"], observed=True):
        rate = float(g["Is_Promotion"].mean())
        avg  = g.loc[g["Is_Promotion"]==1, "Discount_Percent"].mean()
        rates[(str(cat), fk)] = (rate, 0.0 if np.isnan(avg) else float(avg))

    for fk in ["0","1"]:
        sub  = df[df["fest_key"]==fk]
        rate = float(sub["Is_Promotion"].mean()) if len(sub)>0 else 0.0
        avg  = sub.loc[sub["Is_Promotion"]==1, "Discount_Percent"].mean()
        rates[("__all__", fk)] = (rate, 0.0 if np.isnan(avg) else float(avg))
    return rates


def _lookup_promo(cat_str, fest_str, rates):
    v = rates.get((cat_str, fest_str)) or rates.get(("__all__", fest_str), (0.0, 0.0))
    return v  # always a tuple


def build_2026_grid(df, cal26, trend_params, promo_rates):
    log.info("Phase 6 – Building 2026 forecast grid …")
    t0 = time.time()

    dates_2026 = pd.date_range("2026-01-01","2026-12-31", freq="D")
    stores   = df["Store_ID"].unique().tolist()
    products = df["Product_ID"].unique().tolist()

    grid = pd.MultiIndex.from_product(
        [dates_2026, stores, products], names=["Date","Store_ID","Product_ID"]
    ).to_frame(index=False)
    grid["Store_ID"]   = grid["Store_ID"].astype("category")
    grid["Product_ID"] = grid["Product_ID"].astype("category")

    # Calendar
    grid = grid.merge(
        cal26[["Date","Is_Holiday","Is_Shopping_Season","Is_Local_Festival",
               "Holiday_Name","Shopping_Season_Name","Local_Festival_Name"]],
        on="Date", how="left"
    )
    grid["Is_Festival"] = (
        (grid["Is_Shopping_Season"]==1) | (grid["Is_Local_Festival"]==1)
    ).astype("int8")

    # Metadata
    prod_meta  = df[["Product_ID","Category","Pack_Size"]].drop_duplicates()
    store_meta = df[["Store_ID","City","Region"]].drop_duplicates()
    grid = grid.merge(prod_meta,  on="Product_ID", how="left")
    grid = grid.merge(store_meta, on="Store_ID",   how="left")
    for col in ["Category","City","Region"]:
        grid[col] = grid[col].astype("category")

    # Promo imputation (vectorized)
    cat_s  = grid["Category"].astype(str).values
    fest_s = grid["Is_Festival"].astype(str).values
    prates = np.array([_lookup_promo(c,f,promo_rates)[0] for c,f in zip(cat_s, fest_s)], dtype=np.float32)
    pdisc  = np.array([_lookup_promo(c,f,promo_rates)[1] for c,f in zip(cat_s, fest_s)], dtype=np.float32)
    grid["Is_Promotion"]   = np.round(prates).astype(np.int8)
    grid["Discount_Percent"] = pdisc

    # Calendar features
    grid["day_of_week"]  = grid["Date"].dt.dayofweek.astype("int8")  # type: ignore
    grid["month"]        = grid["Date"].dt.month.astype("int8")  # type: ignore
    grid["day_of_month"] = grid["Date"].dt.day.astype("int8")  # type: ignore
    grid["year"]         = grid["Date"].dt.year.astype("int16")  # type: ignore
    grid["week_of_year"] = grid["Date"].dt.isocalendar().week.astype("int8")  # type: ignore

    # Lag features from REAL 2025 data (no recursion)
    hist = df[df["Date"].dt.year==2025][["Date","Store_ID","Product_ID","Residual"]].copy()

    grid["lag_date"] = grid["Date"] - pd.Timedelta(days=365)
    grid = grid.merge(
        hist.rename(columns={"Date":"lag_date","Residual":"lag_365_residual"}),
        on=["lag_date","Store_ID","Product_ID"], how="left"
    )
    grid["lag_365_residual"] = grid["lag_365_residual"].astype(np.float32)

    roll365 = (
        hist.groupby(["Store_ID","Product_ID"], observed=True)["Residual"]
        .mean().reset_index()
        .rename(columns={"Residual":"rolling_mean_365_residual"})
    )
    grid = grid.merge(roll365, on=["Store_ID","Product_ID"], how="left")
    grid["rolling_mean_365_residual"] = grid["rolling_mean_365_residual"].astype(np.float32)
    grid.drop(columns=["lag_date"], inplace=True)

    # Trend extrapolation (vectorized via merge)
    day0 = df["Date"].min()
    grid["day_ord"] = (grid["Date"] - day0).dt.days.astype(np.float32)

    tp_records = [
        {"Store_ID":s, "Product_ID":p, "_slope":slope, "_intercept":intercept}
        for (s,p),(slope,intercept,_) in trend_params.items()
    ]
    tp_df = pd.DataFrame(tp_records)
    tp_df["Store_ID"]   = tp_df["Store_ID"].astype("category")
    tp_df["Product_ID"] = tp_df["Product_ID"].astype("category")

    grid = grid.merge(tp_df, on=["Store_ID","Product_ID"], how="left")
    fitted_log = grid["_intercept"].values + grid["_slope"].values * grid["day_ord"].values
    grid["Trend_Value_2026"] = np.maximum(np.expm1(fitted_log), 0).astype(np.float32)
    grid.drop(columns=["_slope","_intercept"], inplace=True)

    # Categorical encoding (re-cast after merges which may demote dtype)
    for col in CAT_FEATURES:
        if col in grid.columns and grid[col].dtype.name != "category":
            grid[col] = grid[col].astype("category")
        if col in grid.columns:
            grid[col+"_enc"] = grid[col].cat.codes.astype("int16")

    log.info("  Grid: {:,} rows  |  elapsed {:.1f}s".format(len(grid), time.time()-t0))
    return grid


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    log.info("="*70)
    log.info("Detrended Gradient Boosting Sales Forecasting Pipeline — START")
    log.info("matplotlib available: {}".format(HAS_MPL))
    log.info("="*70)
    t_start = time.time()

    # Phase 1
    df, cal26 = load_data()

    # Phase 2
    df, trend_params = fit_trends(df)

    # Promo rates
    promo_rates = compute_promo_rates(df)

    # Phase 3
    log.info("Phase 3 – Feature engineering …")
    df_full = build_features(df, include_short_lags=True)
    df_full = encode_cats(df_full)

    # Train/Val split
    log.info("Splitting train (2021-2024) / val (2025) …")
    train_df = df_full[df_full["Date"].dt.year <= 2024].copy()
    val_df   = df_full[df_full["Date"].dt.year == 2025].copy()
    results  = []

    # ── Model 1: Seasonal Naive ───────────────────────────────────────────
    log.info("Phase 4 – Model 1: Seasonal Naive …")
    naive_pred = seasonal_naive(train_df, val_df)
    results.append(evaluate("Seasonal Naive", val_df["Units_Sold"].values, naive_pred))

    feat_short = get_feature_cols(df_full, include_short_lags=True)
    y_val      = val_df["Units_Sold"].values

    # ── Model 3: Plain HGBR on raw Units_Sold (using annual lags only) ──────
    log.info("Phase 4 – Model 3: Plain HGBR (raw Units_Sold) …")
    feat_det = get_feature_cols(df_full, include_short_lags=False)
    plain_hgbr = train_hgbr(
        train_df[feat_det].values, train_df["Units_Sold"].values,
        val_df[feat_det].values,   val_df["Units_Sold"].values,
    )
    plain_pred = plain_hgbr.predict(val_df[feat_det].values)
    results.append(evaluate("Plain HGBR (raw)", y_val, plain_pred))

    # ── Model 4: Detrended HGBR (residual target) ────────────────────────────
    log.info("Phase 4 – Model 4: Detrended HGBR (residual) …")
    det_hgbr = train_hgbr(
        train_df[feat_det].values, train_df["Residual"].values,
        val_df[feat_det].values,   val_df["Residual"].values,
    )

    resid_pred    = det_hgbr.predict(val_df[feat_det].values)
    det_pred_units = np.maximum(val_df["Trend_Value"].values + resid_pred, 0)
    results.append(evaluate("Detrended HGBR", y_val, det_pred_units))

    # YoY growth sanity
    total_2024 = train_df[train_df["Date"].dt.year==2024]["Units_Sold"].sum()
    total_2025 = val_df["Units_Sold"].sum()
    growth_rate = (total_2025/total_2024 - 1)*100 if total_2024>0 else 0
    log.info("  2024 total: {:,.0f}  |  2025 total: {:,.0f}  |  YoY: {:.1f}%".format(
        total_2024, total_2025, growth_rate))

    # ── Evaluation report ─────────────────────────────────────────────────
    log.info("Phase 5 – Writing evaluation_report.txt …")
    results_df = pd.DataFrame(results)
    report_path = os.path.join(OUTPUT, "evaluation_report.txt")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("="*78+"\n")
        f.write("  AI Sales Forecasting — Model Comparison Report\n")
        f.write("  Train: 2021-2024   |   Validation: 2025   |   Forecast: 2026\n")
        f.write("  {:,} Store×Product series   |   {:,} validation rows\n".format(
            len(trend_params), len(val_df)))
        f.write("="*78+"\n\n")
        hdr = f"{'Model':<35}  {'MAE':>8}  {'RMSE':>9}  {'WAPE':>7}  {'SMAPE':>8}"
        f.write(hdr+"\n"+"-"*len(hdr)+"\n")
        for _, row in results_df.iterrows():
            f.write(f"{row['model']:<35}  {row['MAE']:>8.3f}  {row['RMSE']:>9.3f}"
                    f"  {row['WAPE']:>7.4f}  {row['SMAPE']:>8.4f}\n")

        f.write("\nNotes:\n")
        f.write("  WAPE  = Weighted Absolute Percentage Error (robust to zero actuals)\n")
        f.write("  SMAPE = Symmetric MAPE\n")
        f.write("  HGBR  = HistGradientBoostingRegressor (sklearn histogram GB, ≡ LightGBM)\n")
        f.write(f"\n  2024→2025 YoY Growth Rate: {growth_rate:.2f}%\n")
        best = results_df.loc[results_df["MAE"].idxmin(),"model"]
        f.write(f"  Best model by MAE: {best}\n")
        det_row   = results_df[results_df["model"]=="Detrended HGBR"]
        plain_row = results_df[results_df["model"]=="Plain HGBR (raw)"]
        if not det_row.empty and not plain_row.empty:
            imp = (plain_row["MAE"].values[0]-det_row["MAE"].values[0])/plain_row["MAE"].values[0]*100
            f.write(f"  Detrending improvement over Plain HGBR: {imp:.2f}% MAE reduction\n")

    log.info("  Saved: {}".format(report_path))
    with open(report_path) as f:
        print(f.read())

    # Validation chart / CSV
    plot_validation(val_df, det_pred_units)

    # ── Phase 6: 2026 Forecast ────────────────────────────────────────────
    log.info("Phase 6 – Generating 2026 forecast …")
    grid = build_2026_grid(df, cal26, trend_params, promo_rates)

    X_2026           = grid[feat_det].values
    resid_2026       = det_hgbr.predict(X_2026)
    grid["Residual_2026"]   = resid_2026.astype(np.float32)
    grid["Forecast_Units"]  = np.maximum(
        grid["Trend_Value_2026"] + grid["Residual_2026"], 0
    )

    # Trend sanity: compare plain vs detrended 2026 totals (both use feat_det)
    plain_2026_pred  = np.maximum(plain_hgbr.predict(grid[feat_det].values), 0)
    total_det_2026   = grid["Forecast_Units"].sum()
    total_plain_2026 = plain_2026_pred.sum()
    log.info("  2025 actual total:             {:>15,.0f}".format(total_2025))
    log.info("  2026 Detrended HGBR total:     {:>15,.0f}  ({:+.1f}% vs 2025)".format(
        total_det_2026, (total_det_2026/total_2025-1)*100))
    log.info("  2026 Plain HGBR total:         {:>15,.0f}  ({:+.1f}% vs 2025)".format(
        total_plain_2026, (total_plain_2026/total_2025-1)*100))
    log.info("  Historical YoY growth rate:    {:>+15.1f}%".format(growth_rate))

    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n"+"="*78+"\n")
        f.write("  Trend Sanity Check (2026 vs 2025 totals)\n")
        f.write("="*78+"\n")
        f.write(f"  2025 actual total units:       {total_2025:>15,.0f}\n")
        f.write(f"  2026 Detrended HGBR:           {total_det_2026:>15,.0f}  "
                f"({(total_det_2026/total_2025-1)*100:+.1f}%)\n")
        f.write(f"  2026 Plain HGBR:               {total_plain_2026:>15,.0f}  "
                f"({(total_plain_2026/total_2025-1)*100:+.1f}%)\n")
        f.write(f"  Historical YoY growth rate:    {growth_rate:>+15.1f}%\n")

    # ── Phase 7: Save outputs ─────────────────────────────────────────────
    log.info("Phase 7 – Saving outputs …")

    # Save model (sklearn joblib)
    import joblib
    model_path = os.path.join(OUTPUT, "sales_forecaster.model")
    joblib.dump(det_hgbr, model_path)
    log.info("  Saved: {}".format(model_path))

    # Forecast CSV
    forecast_cols = [
        "Date","Store_ID","Product_ID","Category","Region","City",
        "Is_Holiday","Is_Shopping_Season","Is_Local_Festival",
        "Holiday_Name","Shopping_Season_Name","Local_Festival_Name",
        "Is_Festival","Is_Promotion","Discount_Percent",
        "Trend_Value_2026","Residual_2026","Forecast_Units",
    ]
    forecast_out = os.path.join(OUTPUT, "forecast_2026.csv")
    grid[forecast_cols].to_csv(forecast_out, index=False, float_format="%.3f")
    log.info("  Saved: {}  ({:,} rows)".format(forecast_out, len(grid)))

    # Spike chart / CSV
    plot_forecast_spikes(grid, cal26)

    elapsed = time.time()-t_start
    log.info("="*70)
    log.info("Pipeline complete in {:.1f}s ({:.1f} min)".format(elapsed, elapsed/60))
    log.info("Outputs in: {}".format(OUTPUT))
    log.info("="*70)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("FATAL ERROR:\n"+traceback.format_exc())
        sys.exit(1)
