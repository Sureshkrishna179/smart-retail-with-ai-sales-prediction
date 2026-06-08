import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, cast, Optional, TypedDict
from sklearn.ensemble import RandomForestRegressor

from smartretail.db.connection import db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.utils import read_json_body
from smartretail.api.validators.core import validate_train, validate_predict

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

_models = {}

def train_model_from_csv(csv_text, product_name):
    try:
        df = pd.read_csv(io.StringIO(csv_text))
        if 'Date' not in df.columns or 'Sales_Qty' not in df.columns or 'Product' not in df.columns:
            return False, "CSV must contain Date, Product, and Sales_Qty columns."
            
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

def train_model_from_db(product_name):
    try:
        if product_name == "ALL":
            prods = db_query("SELECT DISTINCT name FROM products ORDER BY name")
            if not prods:
                return False, "No products found in database."
            target_products = [r['name'] for r in prods]
        else:
            target_products = [product_name]
            
        total_trained = 0
        trained_names = []
        
        for p_name in target_products:
            rows = db_query("""
                SELECT s.sale_date as date, p.name as product, s.quantity, p.category
                FROM sales s JOIN products p ON s.product_id=p.id
                WHERE p.name LIKE %s ORDER BY s.sale_date
            """, (f"%{p_name}%",))
            
            if rows is None:
                continue
                
            if len(rows) < 10:
                prod_info = db_query("SELECT category FROM products WHERE name LIKE %s", (f"%{p_name}%",))
                if prod_info:
                    cat = prod_info[0]['category']
                    cat_sales = db_query("""
                        SELECT AVG(daily_sum) as cat_avg FROM (
                            SELECT DATE(s.sale_date) as sd, p.id, SUM(s.quantity) as daily_sum
                            FROM sales s JOIN products p ON s.product_id = p.id
                            WHERE p.category = %s AND p.name NOT LIKE %s
                            GROUP BY sd, p.id
                        ) t
                    """, (cat, f"%{p_name}%"))
                    cat_avg = float(cat_sales[0]['cat_avg']) if cat_sales and cat_sales[0]['cat_avg'] else 5.0
                    _models[p_name] = {"avg": cat_avg, "source": "category_fallback"}
                    total_trained += 1
                    trained_names.append(f"{p_name} (Fallback)")
                else:
                    if product_name != "ALL":
                        return False, f"Product '{p_name}' not found."
                continue
                
            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'])
            dt_accessor = cast(Any, df['date'].dt)
            df['Year']      = dt_accessor.year
            df['Month']     = dt_accessor.month
            df['Day']       = dt_accessor.day
            df['DayOfWeek'] = dt_accessor.dayofweek
            
            X = df[['Year','Month','Day','DayOfWeek']]
            y = df['quantity'].astype(float)
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)
            
            r2_score = model.score(X, y)
            accuracy = max(0.0, min(100.0, round(r2_score * 100, 1)))
            
            avg = float(cast(Any, y.mean()))
            _models[p_name] = {"model": model, "avg": avg, "accuracy": accuracy, "source": "database"}
            total_trained += 1
            trained_names.append(p_name)
            
        if total_trained == 0:
            return False, "Not enough data to train any model."
            
        if product_name == "ALL":
            return True, f"Trained {total_trained} models from database."
        else:
            info = _models.get(product_name, {})
            if "model" in info:
                avg_val = info.get('avg', 0.0)
                return True, f"Trained from database (avg: {avg_val:.1f} units/day)"
            else:
                fallback_avg = _models[product_name]['avg']
                return True, f"Cold Start: Using category average ({fallback_avg:.1f} units/day)"
    except Exception as e:
        return False, str(e)

def predict_sales(product_name: str, target_date: datetime) -> tuple[Optional[float], Optional[SalesPredictionDetails]]:
    info = _models.get(product_name)
    if not info:
        return None, None
        
    if "model" in info:
        features = pd.DataFrame(
            [[target_date.year, target_date.month, target_date.day, target_date.weekday()]], 
            columns=['Year', 'Month', 'Day', 'DayOfWeek']
        )
        base_pred = max(0, float(info["model"].predict(features)[0]))
    else:
        base_pred = info["avg"]
        
    mult, boosts = get_demand_multiplier(target_date)
    adjusted = round(base_pred * mult, 1)
    details: SalesPredictionDetails = {
        "base": round(base_pred, 1),
        "multiplier": mult,
        "boosts": boosts,
        "adjusted": adjusted,
    }
    return adjusted, details

def build_accuracy_by_product(product_names):
    return {p: _models.get(p, {}).get("accuracy") for p in product_names}

def average_accuracy(accuracy_by_product):
    values = [v for v in accuracy_by_product.values() if v is not None]
    return round(sum(values) / len(values), 1) if values else None

def predict_range(product_name, start_date, end_date):
    results = []
    breakdown = {}
    
    target_products = [product_name]
    if product_name == "ALL":
        target_products = list(_models.keys())
        if not target_products:
            return [], {}, None, {}

    current = start_date
    overall_accuracy = []
    
    while current <= end_date:
        total_adjusted = 0
        total_base = 0
        all_boosts = set()
        avg_mult = 0
        valid_models = 0
        daily_breakdown = {}
        
        for p_name in target_products:
            pred, details = predict_sales(p_name, current)
            if pred is not None and details is not None:
                total_adjusted += details["adjusted"]
                total_base += details["base"]
                all_boosts.update(details["boosts"])
                avg_mult += details["multiplier"]
                valid_models += 1
                
                model_info = _models.get(p_name, {})
                if "accuracy" in model_info:
                    overall_accuracy.append(model_info["accuracy"])
                
                daily_breakdown[p_name] = details["adjusted"]
                
                if p_name not in breakdown:
                    breakdown[p_name] = 0
                breakdown[p_name] += details["adjusted"]
                
        if valid_models > 0:
            results.append({
                "date": current.strftime("%Y-%m-%d"),
                "day": current.strftime("%A"),
                "predicted_qty": round(total_adjusted, 1),
                "base_qty": round(total_base, 1),
                "multiplier": round(avg_mult / valid_models, 2),
                "boosts": list(all_boosts),
                "daily_breakdown": daily_breakdown,
            })
        current += timedelta(days=1)
        
    for k in breakdown:
        breakdown[k] = round(breakdown[k], 1)

    accuracy_by_product = build_accuracy_by_product(target_products)
    avg_accuracy = average_accuracy(accuracy_by_product)
        
    return results, breakdown, avg_accuracy, accuracy_by_product

@require_auth()
def handle_train(request):
    try:
        body = read_json_body(request)
        ok, err = validate_train(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        csv_data = body.get("csv_data", "")
        product  = body.get("product", "").strip()
        
        if csv_data:
            ok, msg = train_model_from_csv(csv_data, product)
            source = "csv"
        else:
            ok, msg = train_model_from_db(product)
            source = "database"
            
        model_names = list(_models.keys()) if product == "ALL" else [product]
        accuracy_by_product = build_accuracy_by_product(model_names)
        
        return json_response(request, {
            "success": ok,
            "message": msg,
            "source": source,
            "accuracy": average_accuracy(accuracy_by_product),
            "accuracy_by_product": accuracy_by_product,
        })
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
