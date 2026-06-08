import io
import pandas as pd
import numpy as np
from typing import Any, cast
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

from smartretail.db.connection import db_query
from smartretail.ml.cache import save_models, load_models

# Keep models in memory
_models = load_models()

def _add_enhanced_features(df, date_col='Date'):
    """Add datetime and rolling features."""
    df = df.copy()
    df['Year'] = df[date_col].dt.year
    df['Month'] = df[date_col].dt.month
    df['DayOfWeek'] = df[date_col].dt.dayofweek
    df['DayOfMonth'] = df[date_col].dt.day
    df['IsWeekend'] = df['DayOfWeek'].apply(lambda x: 1 if x >= 5 else 0)
    df['IsPayDay'] = df['DayOfMonth'].apply(lambda x: 1 if x in (1, 2, 15, 16) else 0)
    return ['Year', 'Month', 'DayOfWeek', 'DayOfMonth', 'IsWeekend', 'IsPayDay']

def _compute_eval_metrics(y_true, y_pred):
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = mean_absolute_error(y_true, y_pred)
    y_arr = np.array(y_true, dtype=float)
    p_arr = np.array(y_pred, dtype=float)
    mask = y_arr > 0
    if mask.sum() > 0:
        mape = float(np.mean(np.abs((y_arr[mask] - p_arr[mask]) / y_arr[mask])) * 100)
    else:
        mape = None
    return {"rmse": round(rmse, 2), "mae": round(mae, 2), "mape": round(mape, 1) if mape is not None else None}

def persist_models():
    save_models(_models)

def train_model_from_csv(csv_text: str, product_name: str) -> tuple[bool, str]:
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
                continue
                
            prod_data = prod_data.sort_values(by='Date')
            feat_cols = _add_enhanced_features(prod_data, date_col='Date')

            X = prod_data[feat_cols]
            y = prod_data['Sales_Qty'].astype(float)

            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)
            
            r2_score = model.score(X, y)
            accuracy = max(0.0, min(100.0, round(r2_score * 100, 1)))
            y_pred = model.predict(X)
            metrics = _compute_eval_metrics(y.values, y_pred)
            
            avg = float(cast(Any, y.mean()))
            _models[p_name] = {"model": model, "avg": avg, "accuracy": accuracy, "source": "csv", "metrics": metrics}
            total_trained += 1
            trained_names.append(p_name)
            
        if total_trained == 0:
            return False, "Not enough data to train any model."
        persist_models()
        return True, f"Trained {total_trained} models."
    except Exception as e:
        return False, str(e)
