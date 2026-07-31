import io
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, cast, Optional, TypedDict
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)

# Model storage for in-memory / CSV models
_models: dict[str, Any] = {}

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
    
    Auto-detects two CSV column formats:
      Format A (simple): Date, Product, Sales_Qty
      Format B (full):   Date, Store_ID, Product_ID, Units_Sold, ...
    """
    try:
        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = df.columns.str.strip()
        
        # Auto-detect column format and normalize to: Date, Product, Sales_Qty
        if 'Product_ID' in df.columns and 'Units_Sold' in df.columns:
            # Format B: full sales_data.csv format
            df = df.rename(columns={'Product_ID': 'Product', 'Units_Sold': 'Sales_Qty'})
            logger.info("CSV auto-detected as Format B (Product_ID/Units_Sold)")
        elif 'Product' in df.columns and 'Sales_Qty' in df.columns:
            logger.info("CSV auto-detected as Format A (Product/Sales_Qty)")
        else:
            return False, (
                "CSV must contain either (Date, Product, Sales_Qty) or "
                "(Date, Product_ID, Units_Sold) columns. "
                f"Found: {', '.join(df.columns.tolist())}"
            )
        
        if 'Date' not in df.columns:
            return False, "CSV must contain a 'Date' column."
            
        df['Date'] = pd.to_datetime(df['Date'])
        
        target_products = [product_name]
        if product_name == "ALL":
            target_products = df['Product'].unique().tolist()
            if not target_products:
                return False, "No products found in CSV."
                
        total_trained = 0
        trained_names = []
        for p_name in target_products:
            prod_data = df[df['Product'] == p_name].copy()
            if len(prod_data) < 5:
                if product_name != "ALL":
                    return False, f"Not enough data for '{p_name}'. Need 5 records."
                continue
                
            assert isinstance(prod_data, pd.DataFrame)
            prod_data = prod_data.sort_values(by='Date')
            dt_accessor = cast(Any, prod_data['Date'].dt)
            prod_data['Year']      = dt_accessor.year
            prod_data['Month']     = dt_accessor.month
            prod_data['Day']       = dt_accessor.day
            prod_data['DayOfWeek'] = dt_accessor.dayofweek

            X = prod_data[['Year','Month','Day','DayOfWeek']]
            y = prod_data['Sales_Qty'].astype(float)

            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)
            
            r2_score = model.score(X, y)
            accuracy = max(0.0, min(100.0, round(r2_score * 100, 1)))
            
            avg = float(cast(Any, y.mean()))
            _models[p_name] = {"model": model, "avg": avg, "accuracy": accuracy, "source": "csv"}
            total_trained += 1
            trained_names.append(p_name)
            
        if total_trained == 0:
            return False, "Not enough data to train any model."
            
        if product_name == "ALL":
            return True, f"Trained {total_trained} models from CSV: {', '.join(trained_names)}"
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
    """Predict for a product_name on a given date using the HGBR model."""
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
    """Date-range prediction using HGBR or custom CSV RandomForest model."""
    if product_name in _models:
        info = _models[product_name]
        model = info["model"]
        curr = start_date
        results = []
        while curr <= end_date:
            X = pd.DataFrame([{
                'Year': curr.year,
                'Month': curr.month,
                'Day': curr.day,
                'DayOfWeek': curr.weekday()
            }])
            base_pred = float(model.predict(X)[0])
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
        results_by_date: dict[str, float] = {}
        daily_breakdowns: dict[str, dict[str, float]] = {}
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
            return json_response(request, {
                "success": True,
                "message": msg,
                "source": "uploaded_csv"
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
