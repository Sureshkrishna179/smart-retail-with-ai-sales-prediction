import io
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, cast, Optional, TypedDict
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

logger = logging.getLogger(__name__)

# Model storage for in-memory / CSV models
_models: dict[str, Any] = {}

# ── Product Tokenizer (Two-Way ID ↔ Name Mapper) ────────────────────────────
# Encodes user raw product names → clean surrogate IDs for ML training,
# then decodes back to original names for dashboard display.
# Zero external API calls. 100% on-premise. O(1) lookup.
from smartretail.ml.product_tokenizer import ProductTokenizer
_csv_tokenizer = ProductTokenizer(prefix="UP")  # UP = User Product

# New Detrended HGBR model
from smartretail.ml.trainer import train as hgbr_train, get_state, get_product_lookup, get_id_to_name_lookup
from smartretail.ml.predictor import predict as hgbr_predict, get_model_info

# Build product name ↔ Product_ID lookups at import time
_product_lookup: dict[str, str] = get_product_lookup()
_id_to_name_lookup: dict[str, str] = get_id_to_name_lookup()

from smartretail.db.connection import db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.utils import read_json_body
from smartretail.api.validators.core import validate_train, validate_predict


def _resolve_product_id(product_name: str) -> str:
    """Resolve a product display name to its Product_ID for the HGBR model."""
    if not product_name or product_name == "ALL":
        return product_name
    # Direct match (e.g. "P001")
    if product_name in _product_lookup:
        return _product_lookup[product_name]
    # Uppercase match
    upper = product_name.upper()
    if upper in _product_lookup:
        return _product_lookup[upper]
    # Underscore match (e.g. "BASMATI_RICE")
    underscore = upper.replace(" ", "_")
    if underscore in _product_lookup:
        return _product_lookup[underscore]
    # Fallback: return as-is
    return product_name.upper().replace(" ", "_")

FESTIVALS = [
    # Tamil Nadu
    ("Pongal", 1, 14, 1, 17, 1.5), ("Thai Poosam", 1, 25, 1, 25, 1.3),
    ("Masi Magam", 2, 24, 2, 24, 1.2), ("Panguni Uthiram", 3, 25, 3, 25, 1.2),
    ("Chithirai Festival", 4, 14, 4, 28, 1.4), ("Aadi Perukku", 7, 18, 7, 18, 1.3),
    ("Vinayagar Chaturthi", 9, 7, 9, 7, 1.4), ("Navaratri", 10, 3, 10, 12, 1.5),
    ("Karthigai Deepam", 11, 25, 11, 25, 1.4),
    # National
    ("Republic Day", 1, 26, 1, 26, 1.2), ("Holi", 3, 14, 3, 14, 1.3),
    ("Ram Navami", 4, 6, 4, 6, 1.2), ("Independence Day", 8, 15, 8, 15, 1.2),
    ("Janmashtami", 8, 26, 8, 26, 1.3), ("Gandhi Jayanti", 10, 2, 10, 2, 1.1),
    ("Dussehra", 10, 12, 10, 12, 1.4), ("Diwali", 10, 24, 11, 3, 1.5),
    ("Christmas", 12, 24, 12, 25, 1.3), ("New Year", 12, 31, 1, 2, 1.4),
    ("Eid ul-Fitr", 4, 10, 4, 12, 1.4), ("Eid ul-Adha", 6, 17, 6, 19, 1.3),
    ("Onam", 9, 5, 9, 5, 1.3), ("Raksha Bandhan", 8, 9, 8, 9, 1.3),
    ("Makar Sankranti", 1, 14, 1, 14, 1.3), ("Guru Nanak Jayanti", 11, 15, 11, 15, 1.2),
    # Shopping Seasons
    ("Wedding Season Summer", 4, 15, 6, 15, 1.3),
    ("Wedding Season Winter", 11, 15, 12, 15, 1.3),
    ("Back to School", 6, 1, 6, 15, 1.2),
    ("Deepavali Shopping", 10, 15, 10, 28, 1.5),
    ("Pongal Shopping", 1, 7, 1, 14, 1.4),
]

FESTIVAL_WINDOW = 5

# ── 7-feature pipeline constants & helpers (used by CSV RandomForest) ────────
FEATURE_COLUMNS = [
    "Year", "Month", "Day", "DayOfWeek",
    "IsWeekend", "IsPayDay", "DaysToFestival",
]

# ── Core B extended feature pipeline (7 calendar + 3 historical demand signals) ──
CORE_B_FEATURE_COLUMNS = FEATURE_COLUMNS + [
    "lag_1", "rolling_3_mean", "rolling_7_mean",
]


def _days_to_nearest_festival(dt: datetime) -> int:
    """Return the number of days to the nearest festival date."""
    min_dist = 365
    for _name, sm, sd, em, ed, _mult in FESTIVALS:
        try:
            start = datetime(dt.year, sm, sd)
        except ValueError:
            continue
        dist = abs((start - dt).days)
        if dist < min_dist:
            min_dist = dist
        # Also check the previous / next year edges
        for offset in (-1, 1):
            try:
                alt = datetime(dt.year + offset, sm, sd)
                d = abs((alt - dt).days)
                if d < min_dist:
                    min_dist = d
            except ValueError:
                pass
    return min_dist


def _build_inference_features(dt: datetime) -> np.ndarray:
    """Build a (1, 7) numpy array matching FEATURE_COLUMNS for a given date."""
    row = [
        dt.year,
        dt.month,
        dt.day,
        dt.weekday(),
        1 if dt.weekday() >= 5 else 0,                    # IsWeekend
        1 if dt.day in (1, 15, 28, 29, 30, 31) else 0,    # IsPayDay
        _days_to_nearest_festival(dt),                     # DaysToFestival
    ]
    return np.array([row], dtype=float)


def _build_core_b_inference_row(dt: datetime, lag_1: float, rolling_3_mean: float, rolling_7_mean: float) -> pd.DataFrame:
    """Build a (1, 10) DataFrame for Core B inference with current calendar and rolling lag features."""
    row = {
        "Year": dt.year,
        "Month": dt.month,
        "Day": dt.day,
        "DayOfWeek": dt.weekday(),
        "IsWeekend": 1 if dt.weekday() >= 5 else 0,
        "IsPayDay": 1 if dt.day in (1, 15, 28, 29, 30, 31) else 0,
        "DaysToFestival": _days_to_nearest_festival(dt),
        "lag_1": float(lag_1),
        "rolling_3_mean": float(rolling_3_mean),
        "rolling_7_mean": float(rolling_7_mean),
    }
    return pd.DataFrame([row], columns=CORE_B_FEATURE_COLUMNS)


def _build_feature_df(prod_data: pd.DataFrame) -> pd.DataFrame:
    """Build a 10-column feature DataFrame for Core B training (calendar + lag/rolling demand)."""
    dt_accessor = cast(Any, prod_data['Date'].dt)
    base_dict = {
        'Year':           dt_accessor.year,
        'Month':          dt_accessor.month,
        'Day':            dt_accessor.day,
        'DayOfWeek':      dt_accessor.dayofweek,
        'IsWeekend':      (dt_accessor.dayofweek >= 5).astype(int),
        'IsPayDay':       prod_data['Date'].apply(
                              lambda d: 1 if d.day in (1, 15, 28, 29, 30, 31) else 0),
        'DaysToFestival': prod_data['Date'].apply(
                              lambda d: _days_to_nearest_festival(d)),
    }
    if 'Sales_Qty' in prod_data.columns and len(prod_data) > 0:
        s = prod_data['Sales_Qty'].astype(float)
        mean_val = float(s.mean())
        base_dict['lag_1'] = s.shift(1).bfill().fillna(mean_val)
        base_dict['rolling_3_mean'] = s.shift(1).rolling(window=3, min_periods=1).mean().bfill().fillna(mean_val)
        base_dict['rolling_7_mean'] = s.shift(1).rolling(window=7, min_periods=1).mean().bfill().fillna(mean_val)
    else:
        base_dict['lag_1'] = 0.0
        base_dict['rolling_3_mean'] = 0.0
        base_dict['rolling_7_mean'] = 0.0
    return pd.DataFrame(base_dict, columns=CORE_B_FEATURE_COLUMNS)


def build_metrics_by_product(
    product_names: list[str],
) -> dict[str, Optional[dict[str, float]]]:
    """Return per-product {rmse, mae} metrics from _models store."""
    result: dict[str, Optional[dict[str, float]]] = {}
    for name in product_names:
        info = _models.get(name)
        if info and "metrics" in info:
            result[name] = info["metrics"]
        else:
            result[name] = None
    return result


def average_metrics(
    metrics_by_product: dict[str, Optional[dict[str, float]]],
) -> Optional[dict[str, float]]:
    """Return average rmse/mae across products that have metrics."""
    rmse_vals = []
    mae_vals = []
    for m in metrics_by_product.values():
        if m is not None:
            rmse_vals.append(m["rmse"])
            mae_vals.append(m["mae"])
    if not rmse_vals:
        return None
    return {
        "rmse": round(sum(rmse_vals) / len(rmse_vals), 4),
        "mae":  round(sum(mae_vals) / len(mae_vals), 4),
    }


def is_festival_period(target_date):
    for name, sm, sd, em, ed, mult in FESTIVALS:
        try:
            start = datetime(target_date.year, sm, sd) - timedelta(days=FESTIVAL_WINDOW)
            end = datetime(target_date.year, em, ed) + timedelta(days=FESTIVAL_WINDOW)
            if start <= target_date <= end:
                return True, name, mult
        except ValueError:
            continue
    return False, None, 1.0

def get_demand_multiplier(target_date):
    multiplier = 1.0
    boosts = []
    if target_date.weekday() >= 5:
        multiplier *= 1.15
        boosts.append("Weekend Boost (+15%)")
    is_fest, fest_name, fest_mult = is_festival_period(target_date)
    if is_fest:
        multiplier *= fest_mult
        boosts.append(f"{fest_name} ({fest_mult}x)")
    return round(multiplier, 2), boosts

class SalesPredictionDetails(TypedDict):
    base: float
    multiplier: float
    boosts: list[str]
    adjusted: float


def train_model_from_csv(csv_text, product_name):
    """Train a RandomForest model from uploaded CSV text.
    
    Auto-detects column formats and normalizes to: Date, Product, Sales_Qty.
    Uses ProductTokenizer to encode raw product names into clean surrogate
    IDs (UP001, UP002, ...) for internal ML processing, then decodes back
    to original names when returning results to the dashboard.
    """
    try:
        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = df.columns.str.strip()
        
        # Auto-detect column format and normalize to: Date, Product, Sales_Qty
        if 'Product_ID' in df.columns and 'Units_Sold' in df.columns:
            df = df.rename(columns={'Product_ID': 'Product', 'Units_Sold': 'Sales_Qty'})
            logger.info("CSV auto-detected as Format B (Product_ID/Units_Sold)")
        elif 'Product' in df.columns and 'Sales_Qty' in df.columns:
            logger.info("CSV auto-detected as Format A (Product/Sales_Qty)")
        else:
            # Flexible detection for any grocery dataset
            date_col = next((c for c in df.columns if any(k in c.lower() for k in ['date', 'time', 'day'])), None)
            prod_col = next((c for c in df.columns if any(k in c.lower() for k in ['product', 'item', 'desc', 'name', 'sku', 'title'])), None)
            qty_col = next((c for c in df.columns if any(k in c.lower() for k in ['qty', 'quantity', 'units', 'sold', 'sales', 'volume', 'count'])), None)
            
            if date_col and prod_col and qty_col:
                df = df.rename(columns={date_col: 'Date', prod_col: 'Product', qty_col: 'Sales_Qty'})
                logger.info("CSV auto-detected via flexible matching: Date=%s, Product=%s, Sales_Qty=%s", date_col, prod_col, qty_col)
            else:
                return False, (
                    "CSV must contain Date, Product, and Sales_Qty columns. "
                    f"Found columns: {', '.join(df.columns.tolist())}"
                )
        
        if 'Date' not in df.columns:
            return False, "CSV must contain a 'Date' column."
            
        df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Sales_Qty'] = pd.to_numeric(df['Sales_Qty'], errors='coerce').fillna(0)
        
        target_products = [product_name]
        if product_name == "ALL":
            target_products = [str(p).strip() for p in df['Product'].dropna().unique().tolist() if str(p).strip()]
            if not target_products:
                return False, "No products found in CSV."
            
            # Clear previous CSV models so fresh dataset does not mix with older ones
            csv_keys = [k for k, v in _models.items() if v.get("source") == "csv"]
            for k in csv_keys:
                del _models[k]

        # ── Step 1: ENCODE — build surrogate ID map for uploaded products ──
        _csv_tokenizer.encode(target_products)
                
        total_trained = 0
        trained_names = []
        for p_name in target_products:
            prod_data = df[df['Product'] == p_name].copy()
            if len(prod_data) == 0:
                continue

            # 1. Daily Aggregation: group by Date and sum Sales_Qty to consolidate multiple daily transactions
            prod_data = prod_data.groupby('Date', as_index=False)['Sales_Qty'].sum()
            prod_data = prod_data.sort_values(by='Date').reset_index(drop=True)

            if len(prod_data) < 5:
                if product_name != "ALL":
                    return False, f"Not enough data for '{p_name}'. Need 5 records."
                continue
                
            assert isinstance(prod_data, pd.DataFrame)

            # 2. Add Lag & Rolling Features
            X = _build_feature_df(prod_data)
            y = prod_data['Sales_Qty'].astype(float)

            # 3. Prevent Per-SKU Overfitting: constrained hyperparameters
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X, y)

            y_pred = model.predict(X)
            rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
            mae  = float(mean_absolute_error(y, y_pred))
            
            r2_score = model.score(X, y)
            accuracy = max(0.0, min(100.0, round(r2_score * 100, 1)))
            
            avg = float(cast(Any, y.mean()))
            surrogate_id = _csv_tokenizer.get_id(p_name) or p_name
            recent_sales = list(prod_data['Sales_Qty'].astype(float).tail(14))
            _models[p_name] = {
                "model": model, "avg": avg, "accuracy": accuracy, "source": "csv",
                "product_id": surrogate_id,
                "metrics": {"rmse": round(rmse, 4), "mae": round(mae, 4)},
                "recent_sales": recent_sales,
                "rec_count": len(prod_data),
            }
            total_trained += 1
            trained_names.append(p_name)
            
        if total_trained == 0:
            return False, "Not enough data to train any model."
            
        if product_name == "ALL":
            summary = f"Trained {total_trained} models from CSV: {', '.join(trained_names[:10])}"
            if len(trained_names) > 10:
                summary += f" and {len(trained_names) - 10} more"
            return True, summary
        else:
            info = _models.get(product_name, {})
            prod_data = df[df['Product'] == product_name]
            rec_count = len(prod_data)
            avg_val = info.get('avg', 0.0)
            return True, f"Trained on {rec_count} records from your CSV (avg: {avg_val:.1f} units/day)"
    except Exception as e:
        return False, str(e)


# ── Legacy shim ─────────────────────────────────────────────────────────────
def train_model_from_db(product_name):
    """Triggers a full Detrended HGBR retrain from sales_data.csv."""
    return train_model_from_csv("", product_name)

def build_accuracy_by_product(product_names):
    info = get_model_info()
    mae  = info.get("metrics", {}).get("MAE", None)
    return {p: round(100 - mae * 3, 1) if mae else None for p in product_names}

def average_accuracy(accuracy_by_product):
    values = [v for v in accuracy_by_product.values() if v is not None]
    return round(sum(values) / len(values), 1) if values else None

def predict_sales(product_name: str, target_date: datetime):
    """Predict for a product_name on a given date using the HGBR model or Core B CSV model."""
    if product_name in _models and _models[product_name].get("source") == "csv":
        info = _models[product_name]
        model = info["model"]
        avg = info.get("avg", 0.0)
        history = list(info.get("recent_sales", [avg]))
        lag_1 = history[-1] if history else avg
        r3 = float(np.mean(history[-3:])) if history else avg
        r7 = float(np.mean(history[-7:])) if history else avg
        X = _build_core_b_inference_row(target_date, lag_1, r3, r7)
        base_pred = float(model.predict(X)[0])
        mult, boosts = get_demand_multiplier(target_date)
        adjusted = round(max(0.0, base_pred * mult), 1)
        details: SalesPredictionDetails = {
            "base": round(base_pred, 1),
            "multiplier": mult,
            "boosts": boosts,
            "adjusted": adjusted,
        }
        return adjusted, details

    pid = _resolve_product_id(product_name)
    result = hgbr_predict(
        store_id="ST01",
        product_id=pid,
        target_date=target_date.date(),
    )
    if "error" in result:
        return None, None
    base_pred = result["forecast_units"]
    mult, boosts = get_demand_multiplier(target_date)
    adjusted = round(base_pred, 1)
    details: SalesPredictionDetails = {
        "base": round(base_pred, 1),
        "multiplier": 1.0,
        "boosts": [],
        "adjusted": adjusted,
    }
    return adjusted, details

def predict_range(product_name, start_date, end_date):
    """Date-range prediction using HGBR or custom CSV RandomForest model.
    
    When product_name is 'ALL':
      - If CSV models exist in _models, predict across ALL uploaded products
        and decode surrogate IDs back to original names via _csv_tokenizer.
      - Otherwise, fall through to the pre-trained HGBR model.
    """
    # ── ALL products from uploaded CSV ──────────────────────────────────
    csv_products = [k for k, v in _models.items() if v.get('source') == 'csv']
    if product_name == "ALL" and csv_products:
        results_by_date: dict[str, float] = {}
        daily_breakdowns: dict[str, dict[str, float]] = {}
        breakdown: dict[str, float] = {}
        accuracy_by_product: dict[str, float] = {}
        
        for p_name in csv_products:
            info = _models[p_name]
            model = info['model']
            acc = info.get('accuracy', 85.0)
            avg = info.get('avg', 0.0)
            history = list(info.get('recent_sales', [avg]))
            product_total = 0.0
            curr = start_date
            while curr <= end_date:
                lag_1 = history[-1] if history else avg
                r3 = float(np.mean(history[-3:])) if history else avg
                r7 = float(np.mean(history[-7:])) if history else avg
                X = _build_core_b_inference_row(curr, lag_1, r3, r7)
                base_pred = float(model.predict(X)[0])
                history.append(base_pred)  # autoregressive update
                
                mult, boosts = get_demand_multiplier(curr)
                adj = round(max(0.0, base_pred * mult), 1)
                d_str = curr.strftime('%Y-%m-%d')
                results_by_date[d_str] = results_by_date.get(d_str, 0.0) + adj
                if d_str not in daily_breakdowns:
                    daily_breakdowns[d_str] = {}
                # ── Step 3: DECODE — user's real product name in the daily breakdown ──
                daily_breakdowns[d_str][p_name] = round(
                    daily_breakdowns[d_str].get(p_name, 0.0) + adj, 1)
                product_total += adj
                curr += timedelta(days=1)
            breakdown[p_name] = round(product_total, 1)
            accuracy_by_product[p_name] = acc
        
        results = [{'date': d, 'day': pd.Timestamp(d).strftime('%A'),
                    'predicted_qty': round(v, 1), 'base_qty': round(v, 1),
                    'multiplier': 1.0, 'boosts': [],
                    'daily_breakdown': daily_breakdowns.get(d, {})}
                   for d, v in sorted(results_by_date.items())]
        avg_acc = round(sum(accuracy_by_product.values()) / len(accuracy_by_product), 1) if accuracy_by_product else 85.0
        return results, breakdown, avg_acc, accuracy_by_product
    
    # ── Single product from uploaded CSV ────────────────────────────────
    if product_name in _models:
        info = _models[product_name]
        model = info["model"]
        avg = info.get('avg', 0.0)
        history = list(info.get('recent_sales', [avg]))
        curr = start_date
        results = []
        while curr <= end_date:
            lag_1 = history[-1] if history else avg
            r3 = float(np.mean(history[-3:])) if history else avg
            r7 = float(np.mean(history[-7:])) if history else avg
            X = _build_core_b_inference_row(curr, lag_1, r3, r7)
            base_pred = float(model.predict(X)[0])
            history.append(base_pred)
            
            mult, boosts = get_demand_multiplier(curr)
            adj = round(max(0.0, base_pred * mult), 1)
            d_str = curr.strftime("%Y-%m-%d")
            results.append({
                "date": d_str,
                "day": curr.strftime("%A"),
                "predicted_qty": adj,
                "base_qty": round(base_pred, 1),
                "multiplier": mult,
                "boosts": boosts,
                "daily_breakdown": {product_name: adj}
            })
            curr += timedelta(days=1)
        acc = info.get("accuracy", 85.0)
        breakdown = {product_name: round(sum(r["predicted_qty"] for r in results), 1)}
        return results, breakdown, acc, {product_name: acc}

    from smartretail.ml.predictor import predict_range as hgbr_range
    store_id = "ST01"
    pid = _resolve_product_id(product_name)
    if product_name == "ALL":
        # Return aggregate across all stores
        store_ids = ["ST01","ST02","ST03","ST04","ST05"]
        state = get_state()
        pids  = list({k[1] for k in state.get("trend_params", {}).keys()}) if state else []
        if not pids:
            return [], {}, None, {}
        results_by_date = {}
        daily_breakdowns = {}
        breakdown_raw: dict[str, float] = {}
        for sid in store_ids:
            for p in pids:
                disp_name = _id_to_name_lookup.get(p, p)
                for r in hgbr_range(sid, p, start_date.date(), end_date.date()):
                    d = r["date"]
                    qty = r["forecast_units"]
                    results_by_date[d] = results_by_date.get(d, 0.0) + qty
                    breakdown_raw[p] = breakdown_raw.get(p, 0.0) + qty
                    
                    if d not in daily_breakdowns:
                        daily_breakdowns[d] = {}
                    daily_breakdowns[d][disp_name] = round(daily_breakdowns[d].get(disp_name, 0.0) + qty, 1)

        results = [{"date": d, "day": pd.Timestamp(d).strftime("%A"),
                    "predicted_qty": round(v, 1), "base_qty": round(v, 1),
                    "multiplier": 1.0, "boosts": [],
                    "daily_breakdown": daily_breakdowns.get(d, {})}
                   for d, v in sorted(results_by_date.items())]
        breakdown_named: dict = {}
        accuracy_by_product: dict = {}
        info = get_model_info()
        mae  = info.get("metrics", {}).get("MAE", 0)
        accuracy = round(max(0, 100 - mae * 3), 1)

        for p_id, total_qty in breakdown_raw.items():
            disp_name = _id_to_name_lookup.get(p_id, p_id)
            breakdown_named[disp_name] = round(total_qty, 1)
            accuracy_by_product[disp_name] = accuracy

        return results, breakdown_named, accuracy, accuracy_by_product
    else:
        rows = hgbr_range(store_id, pid, start_date.date(), end_date.date())
        if not rows:
            # Try all 5 stores — product may only exist in specific stores
            for sid in ["ST02","ST03","ST04","ST05"]:
                rows = hgbr_range(sid, pid, start_date.date(), end_date.date())
                if rows:
                    break
        disp_name = _id_to_name_lookup.get(pid, product_name)
        results = [{"date": r["date"], "day": pd.Timestamp(r["date"]).strftime("%A"),
                    "predicted_qty": r["forecast_units"], "base_qty": r["forecast_units"],
                    "multiplier": 1.0, "boosts": [], "daily_breakdown": {disp_name: r["forecast_units"]}}
                   for r in rows]
        breakdown = {disp_name: round(sum(r["forecast_units"] for r in rows), 1)}
        info = get_model_info()
        mae  = info.get("metrics", {}).get("MAE", 0)
        accuracy = round(max(0, 100 - mae * 3), 1)
        return results, breakdown, accuracy, {disp_name: accuracy}


@require_auth()
def handle_train(request):
    """Train model on custom CSV data or Detrended HGBR dataset."""
    try:
        body = read_json_body(request)
        ok, err = validate_train(body)
        if not ok:
            return json_response(request, {"error": err}, 400)

        csv_data = body.get("csv_data", "")
        product = body.get("product", "ALL") or "ALL"
        
        # Small uploaded CSV (inline text) — train custom RandomForest model
        if csv_data and csv_data != "__use_server_file__":
            success, msg = train_model_from_csv(csv_data, product)
            if not success:
                return json_response(request, {"error": msg}, 400)
            trained_products = _csv_tokenizer.get_all_names()
            if not trained_products:
                trained_products = [k for k, v in _models.items() if v.get("source") == "csv"]
            return json_response(request, {
                "success": True,
                "message": msg,
                "source": "uploaded_csv",
                "trained_products": trained_products,
                "tokenizer_map": _csv_tokenizer.get_name_to_id_map(),
            })

        # Full HGBR training on server-side sales_data.csv
        test_size = float(body.get("test_size", 0.20))
        result    = hgbr_train(test_size=test_size)
        metrics   = result["metrics"]

        # Refresh product lookups after training
        global _product_lookup, _id_to_name_lookup
        _product_lookup = get_product_lookup()
        _id_to_name_lookup = get_id_to_name_lookup()

        return json_response(request, {
            "success":      True,
            "message":      (
                f"Detrended HGBR trained on {result['train_rows']:,} rows. "
                f"Test set ({result['test_rows']:,} rows, split {result['split_date']}): "
                f"MAE={metrics['MAE']}, RMSE={metrics['RMSE']}, WAPE={metrics['WAPE']}. "
                f"Improvement over seasonal naive: {metrics['improvement_pct']}%"
            ),
            "source":       "sales_data.csv (detrended-hgbr-v2)",
            "split_date":   result["split_date"],
            "train_rows":   result["train_rows"],
            "test_rows":    result["test_rows"],
            "n_series":     result["n_series"],
            "metrics":      metrics,
            "yoy_growth_pct": result["yoy_growth_pct"],
            "elapsed_sec":  result["elapsed_sec"],
        })
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)


@require_auth()
def handle_model_info(request):
    """Return model status — whether it's loaded, its metrics, etc."""
    try:
        info = get_model_info()
        return json_response(request, info)
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

@require_auth()
def handle_predict(request):
    try:
        body = read_json_body(request)
        ok, err = validate_predict(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        product = body.get("product", "")
        start   = body.get("start_date", "")
        end     = body.get("end_date", start)
        
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        
        results, breakdown, accuracy, accuracy_by_product = predict_range(product, s, e)
        if not results:
            return json_response(request, {"error": "No predictions. Train the model first."}, 400)
            
        total_predicted = sum(r["predicted_qty"] for r in results)
        
        if product == "ALL":
            source = "database/csv (multiple)"
        else:
            source = _models.get(product, {}).get("source", "unknown")
            
        hist_start = (s - timedelta(days=14)).strftime("%Y-%m-%d")
        hist_end = (s - timedelta(days=1)).strftime("%Y-%m-%d")
        
        hist_rows = []
        try:
            if product == "ALL":
                hist_query = """
                    SELECT DATE_FORMAT(sale_date, '%Y-%m-%d') as date, SUM(quantity) as quantity
                    FROM sales 
                    WHERE sale_date >= %s AND sale_date <= %s
                    GROUP BY DATE_FORMAT(sale_date, '%Y-%m-%d')
                    ORDER BY date
                """
                hist_rows = db_query(hist_query, (hist_start, hist_end))
            else:
                hist_query = """
                    SELECT DATE_FORMAT(s.sale_date, '%Y-%m-%d') as date, SUM(s.quantity) as quantity
                    FROM sales s JOIN products p ON s.product_id=p.id
                    WHERE p.name LIKE %s AND s.sale_date >= %s AND s.sale_date <= %s
                    GROUP BY DATE_FORMAT(s.sale_date, '%Y-%m-%d')
                    ORDER BY date
                """
                hist_rows = db_query(hist_query, (f"%{product}%", hist_start, hist_end))
        except Exception:
            hist_rows = []
            
        hist_dict = {r['date']: float(r['quantity']) for r in hist_rows} if hist_rows else {}
        historical_data = []
        curr_hist = s - timedelta(days=14)
        while curr_hist < s:
            d_str = curr_hist.strftime("%Y-%m-%d")
            historical_data.append({
                "date": d_str,
                "quantity": hist_dict.get(d_str, 0)
            })
            curr_hist += timedelta(days=1)
            
        return json_response(request, {
            "predictions": results, 
            "historical": historical_data,
            "breakdown": breakdown,
            "accuracy": accuracy,
            "accuracy_by_product": accuracy_by_product,
            "total_predicted": round(total_predicted, 1), 
            "product": product, 
            "source": source
        })
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

@require_auth()
def handle_get_trained_products(request):
    """Return list of products currently trained in memory (from CSV)."""
    try:
        names = _csv_tokenizer.get_all_names()
        mapping = _csv_tokenizer.get_name_to_id_map()
        items = [{"name": n, "product_id": mapping.get(n, n)} for n in names]
        return json_response(request, {"products": items, "tokenizer_map": mapping})
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

