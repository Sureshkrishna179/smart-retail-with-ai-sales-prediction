"""Unit tests for API input validation."""

from smartretail.api.validators.core import (
    validate_add_product,
    validate_billing,
    validate_predict,
    validate_restock,
    validate_train,
)
from smartretail.api.validators.products import validate_create_user


def test_validate_billing_ok():
    ok, err = validate_billing({"cart": [{"product_id": 1, "quantity": 2}]})
    assert ok is True
    assert err == ""


def test_validate_billing_empty_cart():
    ok, err = validate_billing({"cart": []})
    assert ok is False
    assert "non-empty" in err.lower()


def test_validate_restock_invalid_qty():
    ok, err = validate_restock({"product_id": 1, "quantity": 0})
    assert ok is False


def test_validate_create_user_weak_password():
    ok, err = validate_create_user({"username": "test_user", "password": "abc", "role": "Staff"})
    assert ok is False


def test_validate_create_user_ok():
    ok, err = validate_create_user({"username": "store_mgr", "password": "SecurePassword1!", "role": "Manager"})
    assert ok is True


def test_validate_add_product_ok():
    ok, err = validate_add_product(
        {"name": "Rice 1kg", "category": "Grocery", "unit": "kg", "price": 50, "stock": 100, "min_stock": 20}
    )
    assert ok is True


def test_validate_predict_bad_date():
    ok, err = validate_predict({"product": "Rice 1kg", "start_date": "not-a-date"})
    assert ok is False


def test_validate_train_ok():
    ok, err = validate_train({"product": "Rice 1kg", "csv_data": ""})
    assert ok is True
