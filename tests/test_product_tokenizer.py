"""Unit and Integration tests for ProductTokenizer and Universal Dataset Handling."""

import io
from datetime import datetime, timedelta
import pandas as pd
import pytest

from smartretail.ml.product_tokenizer import ProductTokenizer
from smartretail.api.handlers.ml import (
    train_model_from_csv,
    predict_range,
    _models,
    _csv_tokenizer,
)


def test_tokenizer_bidirectional_mapping():
    tokenizer = ProductTokenizer(prefix="UP")
    products = ["Avocado Oil 500ml", "Greek Yogurt 200g", "Organic Quinoa 1kg"]
    
    mapping = tokenizer.encode(products)
    assert len(mapping) == 3
    assert set(mapping.keys()) == set(products)
    
    # Check surrogate IDs
    for name, surr_id in mapping.items():
        assert surr_id.startswith("UP")
        # Test 2-way decoding
        assert tokenizer.decode(surr_id) == name
        assert tokenizer.get_id(name) == surr_id
        assert tokenizer.get_name(surr_id) == name

    # Test unknown fallback
    assert tokenizer.decode("UNKNOWN_ID") == "UNKNOWN_ID"
    assert tokenizer.get_id("Nonexistent Product") is None


def test_universal_grocery_csv_training_and_prediction():
    # Create sample CSV with brand-new product names and custom date range
    dates = pd.date_range("2025-01-01", periods=60)
    rows = []
    custom_products = ["Dragonfruit 500g", "Almond Butter 200g", "Cold Brew 250ml"]
    
    for d in dates:
        for idx, p in enumerate(custom_products):
            rows.append({
                "Date": d.strftime("%Y-%m-%d"),
                "Product": p,
                "Sales_Qty": (idx + 1) * 10 + (d.day % 5),
            })
    
    df = pd.DataFrame(rows)
    csv_text = df.to_csv(index=False)

    # 1. Train ALL products from this novel CSV
    ok, msg = train_model_from_csv(csv_text, "ALL")
    assert ok is True, f"Training failed: {msg}"
    
    # Verify tokenizer encoded all 3
    encoded_names = _csv_tokenizer.get_all_names()
    for p in custom_products:
        assert p in encoded_names
        surrogate = _csv_tokenizer.get_id(p)
        assert surrogate is not None and surrogate.startswith("UP")
        assert _csv_tokenizer.decode(surrogate) == p

    # 2. Test ALL prediction range — must show NEW product names in breakdown
    start_date = datetime(2025, 4, 1)
    end_date = datetime(2025, 4, 7)
    results, breakdown, avg_acc, acc_by_prod = predict_range("ALL", start_date, end_date)

    assert len(results) == 7
    assert breakdown is not None
    assert set(breakdown.keys()) == set(custom_products), f"Expected {custom_products}, got {list(breakdown.keys())}"
    assert set(acc_by_prod.keys()) == set(custom_products)

    # Check daily breakdown keys
    for r in results:
        daily_keys = set(r["daily_breakdown"].keys())
        assert daily_keys == set(custom_products)
        assert r["predicted_qty"] > 0

    # 3. Test single-product prediction
    single_p = "Dragonfruit 500g"
    results_s, breakdown_s, acc_s, acc_by_prod_s = predict_range(single_p, start_date, end_date)
    assert len(results_s) == 7
    assert list(breakdown_s.keys()) == [single_p]
    assert list(acc_by_prod_s.keys()) == [single_p]

