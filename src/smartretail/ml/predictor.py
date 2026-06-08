import pandas as pd
from typing import TypedDict
from datetime import datetime

from smartretail.ml.trainer import _models

class SalesPredictionDetails(TypedDict):
    base: float
    multiplier: float
    boosts: list[str]
    adjusted: float

def predict_sales(product_name: str, target_date: datetime) -> SalesPredictionDetails:
    """Predict sales for a specific product and date using trained models or fallbacks."""
    info = _models.get(product_name)
    if not info:
        return {"base": 5.0, "multiplier": 1.0, "boosts": ["Cold Start (Default)"], "adjusted": 5.0}

    base_pred = info.get("avg", 5.0)
    
    # Try RF model if available
    model = info.get("model")
    if model:
        try:
            # We need to construct the feature vector for target_date
            X_pred = pd.DataFrame([[
                target_date.year,
                target_date.month,
                target_date.weekday(),
                target_date.day,
                1 if target_date.weekday() >= 5 else 0,
                1 if target_date.day in (1, 2, 15, 16) else 0,
            ]], columns=['Year', 'Month', 'DayOfWeek', 'DayOfMonth', 'IsWeekend', 'IsPayDay'])
            base_pred = float(model.predict(X_pred)[0])
        except Exception:
            pass
            
    # For now, omit festival logic or external DB calls for brevity, 
    # as the user requested just extracting ML predict logic.
    return {
        "base": round(base_pred, 1),
        "multiplier": 1.0,
        "boosts": [],
        "adjusted": round(base_pred, 1)
    }
