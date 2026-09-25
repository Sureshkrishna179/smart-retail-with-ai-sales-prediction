"""
Tests for Universal ETL Ingestion Pipeline
============================================
Verifies:
  - Multi-format file extraction (.csv)
  - Dynamic column mapping & renaming
  - Anti-corruption contract enforcement (strict schema filtering)
  - Mixed datetime standardization
  - Numeric coercion with safe defaults
  - Multi-tenant isolation (tenant_id injection)
  - Corrupt/missing row rejection
"""

import sys
import os

# Ensure project src is on the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from smartretail.etl.ingestion import (
    extract_file_to_dataframe,
    transform_and_enforce_contract,
    REQUIRED_COLUMNS,
)


def test_messy_csv_transformation():
    """Simulate a messy client POS export with dirty dates, bad types, extra columns."""

    raw_csv = (
        "Bill_No,Tx_Date,Item_Code,Item_Desc,Sold_Units,Price,Cashier\n"
        "1001,2026-05-10,P001,Ponni Rice 5kg,12,350.00,Ramesh\n"
        "1002,10/05/2026,P002,Aachi Masala,five,45.00,Suresh\n"        # dirty string qty
        "1003,May 11 2026,P001,Ponni Rice 5kg,,350.00,Ramesh\n"        # missing qty
        "1004,invalid_date,P003,Gingelly Oil,4,220.00,Priya\n"         # corrupted date
        "1005,2026-05-12,  P004  ,Tata Tea,2.8,110.00,Karthik\n"       # spaces + decimal qty
    ).encode("utf-8")

    # ------------------------------------------------------------------
    # Phase 1: Extract (stream -> DataFrame, no disk I/O)
    # ------------------------------------------------------------------
    df = extract_file_to_dataframe("messy_store_sales.csv", raw_csv)
    assert len(df) == 5, f"Expected 5 raw rows, got {len(df)}"

    # ------------------------------------------------------------------
    # Phase 2: Dynamic column mapping (client headers -> target schema)
    # ------------------------------------------------------------------
    mapping = {
        "Tx_Date": "date",
        "Item_Code": "product_id",
        "Sold_Units": "quantity_sold",
    }

    # ------------------------------------------------------------------
    # Phase 3: Transform & enforce strict anti-corruption contract
    # ------------------------------------------------------------------
    clean_df, dropped = transform_and_enforce_contract(
        df, mapping, tenant_id="TENANT_MADURAI_01"
    )

    # --- Anti-corruption: only contract columns survive ---
    assert list(clean_df.columns) == REQUIRED_COLUMNS, (
        f"Contract violated: {list(clean_df.columns)}"
    )
    for extra_col in ["Bill_No", "Cashier", "Price", "Item_Desc"]:
        assert extra_col not in clean_df.columns, f"Extra column leaked: {extra_col}"

    # --- Row rejection: 'invalid_date' row must be dropped ---
    assert dropped == 1, f"Expected 1 rejected row, got {dropped}"
    assert len(clean_df) == 4, f"Expected 4 clean rows, got {len(clean_df)}"

    # --- Multi-tenant isolation: tenant_id on every row ---
    assert (clean_df["tenant_id"] == "TENANT_MADURAI_01").all(), (
        "tenant_id not applied to all rows"
    )

    # --- Date normalization: all dates are ISO YYYY-MM-DD ---
    for d in clean_df["date"]:
        assert len(d) == 10 and d[4] == "-" and d[7] == "-", (
            f"Date not normalized to ISO: {d}"
        )

    # --- Numeric coercion & safe defaults ---
    # Row 2: "five" -> NaN -> 0
    # Row 3: missing -> NaN -> 0
    # Row 5: 2.8 -> round -> 3
    quantities = list(clean_df["quantity_sold"])
    assert quantities == [12, 0, 0, 3], (
        f"Quantity coercion failed: expected [12, 0, 0, 3], got {quantities}"
    )

    # --- Product ID whitespace strip ---
    assert "P004" in list(clean_df["product_id"]), (
        "Product ID whitespace not stripped"
    )

    print("[PASSED] test_messy_csv_transformation")


def test_json_extraction():
    """Verify JSON file ingestion works correctly."""
    raw_json = b'[{"sale_date":"2026-01-15","sku":"SKU001","qty":10},{"sale_date":"2026-01-16","sku":"SKU002","qty":25}]'
    df = extract_file_to_dataframe("data_export.json", raw_json)
    assert len(df) == 2, f"Expected 2 rows from JSON, got {len(df)}"

    mapping = {"sale_date": "date", "sku": "product_id", "qty": "quantity_sold"}
    clean_df, dropped = transform_and_enforce_contract(df, mapping, "TENANT_TEST")
    assert len(clean_df) == 2
    assert dropped == 0
    assert list(clean_df["quantity_sold"]) == [10, 25]

    print("[PASSED] test_json_extraction")


def test_unsupported_file_format():
    """Verify unsupported extensions are rejected."""
    try:
        extract_file_to_dataframe("data.xml", b"<root/>")
        assert False, "Should have raised ValueError for .xml"
    except ValueError as e:
        assert "Unsupported" in str(e)

    print("[PASSED] test_unsupported_file_format")


def test_incomplete_mapping_rejected():
    """Verify that missing required target fields raise a clear error."""
    raw_csv = b"col_a,col_b\n1,2\n3,4\n"
    df = extract_file_to_dataframe("partial.csv", raw_csv)

    # Mapping is missing 'quantity_sold'
    bad_mapping = {"col_a": "date", "col_b": "product_id"}
    try:
        transform_and_enforce_contract(df, bad_mapping, "TENANT_X")
        assert False, "Should have raised ValueError for incomplete mapping"
    except ValueError as e:
        assert "quantity_sold" in str(e)

    print("[PASSED] test_incomplete_mapping_rejected")


def test_empty_file_rejected():
    """Verify that an empty CSV is rejected."""
    raw_csv = b"col_a,col_b\n"
    try:
        extract_file_to_dataframe("empty.csv", raw_csv)
        assert False, "Should have raised ValueError for empty file"
    except ValueError as e:
        assert "no data" in str(e).lower()

    print("[PASSED] test_empty_file_rejected")


# ==============================================================================
# Run all tests
# ==============================================================================
if __name__ == "__main__":
    test_messy_csv_transformation()
    test_json_extraction()
    test_unsupported_file_format()
    test_incomplete_mapping_rejected()
    test_empty_file_rejected()
    print("\n=== ALL 5 ETL PIPELINE TESTS PASSED ===")
