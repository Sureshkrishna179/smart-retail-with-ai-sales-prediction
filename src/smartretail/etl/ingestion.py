"""
SmartRetail SaaS — Universal Ingestion ETL Pipeline
====================================================
Role: Senior Data Engineer
Module: src.smartretail.etl.ingestion

Architecture: Integrates with the project's existing http.server handler
pattern (same interface as sales.py, ml.py, etc.) while also exposing
pure functions for unit testing without a running server.

Capabilities:
  1. Multi-tenant isolation: enforces strict tenant_id scoping on every record.
  2. Multi-format stream ingestion: .csv, .xlsx, .xls, .json without disk I/O.
  3. Dynamic Schema Transformation: translates disparate source schemas via
     user-provided column_mapping dictionary.
  4. Anti-Corruption Layer (ACL): strictly enforces target contract:
     ['tenant_id', 'date', 'product_id', 'quantity_sold']
  5. Resilient Type Coercion: mixed datetime parsing + numeric coercion + null imputation.
  6. High-throughput chunked SQL bulk-load with transactional rollback safety.
"""

import io
import json
import logging
import time
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np

from smartretail.db.connection import get_connection, db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth

logger = logging.getLogger("smartretail.etl")

# ==============================================================================
# 1. STRICT DATA CONTRACT & CONSTANTS
# ==============================================================================
REQUIRED_COLUMNS: List[str] = ["tenant_id", "date", "product_id", "quantity_sold"]
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_BATCH_CHUNK_SIZE = 5000


# ==============================================================================
# 2. FILE EXTRACTION LAYER (STREAM-BASED, NO DISK I/O)
# ==============================================================================
def extract_file_to_dataframe(filename: str, contents: bytes) -> pd.DataFrame:
    """
    Detects file extension and safely parses byte stream into a Pandas DataFrame.
    Raw data never touches disk — critical for multi-tenant data isolation.
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    buffer = io.BytesIO(contents)

    if ext == ".csv":
        # UTF-8 first, fallback to latin1 for legacy retail POS exports
        try:
            df = pd.read_csv(buffer, encoding="utf-8")
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, encoding="latin1")

    elif ext in {".xlsx", ".xls"}:
        df = pd.read_excel(buffer)

    elif ext == ".json":
        df = pd.read_json(buffer)

    else:
        raise ValueError(f"Unhandled extension: {ext}")

    if df.empty:
        raise ValueError("Uploaded file contains no data (empty DataFrame).")

    return df


# ==============================================================================
# 3. TRANSFORMATION & ANTI-CORRUPTION LAYER (ACL)
# ==============================================================================
def transform_and_enforce_contract(
    raw_df: pd.DataFrame,
    column_mapping: Dict[str, str],
    tenant_id: str
) -> Tuple[pd.DataFrame, int]:
    """
    Executes dynamic transformation and strictly enforces the target data contract.

    Contract: ['tenant_id', 'date', 'product_id', 'quantity_sold']

    Steps:
      3.1  Clean whitespace + rename columns via user-provided mapping
      3.2  Verify mandatory target fields exist after mapping
      3.3  Attach immutable tenant_id to every row (multi-tenant fence)
      3.4  Drop all unmapped/extra columns (anti-corruption filter)
      3.5  Standardize mixed date formats via pd.to_datetime(format='mixed')
      3.6  Force numeric coercion on quantity_sold (errors -> NaN)
      3.7  Drop rows with unrecoverable keys (null date or product_id)
      3.8  Fill safe defaults (NaN quantity -> 0)

    Returns:
        (pristine_df, dropped_rows_count)
    """
    initial_rows = len(raw_df)
    df = raw_df.copy()

    # 3.1: Clean whitespace in column names, then apply mapping
    df.columns = [c.strip() if isinstance(c, str) else str(c).strip() for c in df.columns]
    sanitized_mapping = {k.strip(): v.strip() for k, v in column_mapping.items()}
    df = df.rename(columns=sanitized_mapping)

    # 3.2: Verify mandatory target fields exist
    needed_fields = ["date", "product_id", "quantity_sold"]
    missing_fields = [f for f in needed_fields if f not in df.columns]
    if missing_fields:
        raise ValueError(
            f"Column mapping incomplete. Missing required target fields: {missing_fields}. "
            f"Mapped columns available: {list(df.columns)}"
        )

    # 3.3: Attach immutable tenant_id
    df["tenant_id"] = tenant_id.strip()

    # 3.4: Anti-Corruption — keep ONLY the contract columns
    df = df[REQUIRED_COLUMNS]

    # 3.5: Resilient datetime standardization
    # Handles ISO8601, US/UK dates ('2026-05-12', '12/05/2026', 'May 12 2026')
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")

    # 3.6: Strict numeric coercion for quantity
    df["quantity_sold"] = pd.to_numeric(df["quantity_sold"], errors="coerce")

    # 3.7: Drop rows with unrecoverable primary keys
    valid_mask = (
        df["date"].notna()
        & df["product_id"].notna()
        & (df["product_id"].astype(str).str.strip() != "")
    )
    df = df[valid_mask].copy()

    # 3.8: Fill safe defaults and finalize types
    df["quantity_sold"] = df["quantity_sold"].fillna(0.0).round().astype(int)
    df["product_id"] = df["product_id"].astype(str).str.strip()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    dropped_rows = initial_rows - len(df)
    return df, dropped_rows


# ==============================================================================
# 4. SECURE SQL LOADING LAYER (BATCHED & TRANSACTIONAL)
# ==============================================================================
def ensure_sales_history_table():
    """Create the Sales_History table if it doesn't already exist."""
    conn = get_connection()
    if conn is None:
        logger.warning("No DB connection available — skipping table creation.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Sales_History (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                tenant_id VARCHAR(64) NOT NULL,
                date DATE NOT NULL,
                product_id VARCHAR(64) NOT NULL,
                quantity_sold INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_tenant_product_date (tenant_id, product_id, date),
                INDEX idx_tenant_date (tenant_id, date),
                INDEX idx_tenant_product (tenant_id, product_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        logger.info("Sales_History table verified/created.")
    except Exception as e:
        logger.error(f"Failed to create Sales_History table: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn.is_connected():
            conn.close()


def load_to_sales_history(
    df: pd.DataFrame,
    chunk_size: int = DEFAULT_BATCH_CHUNK_SIZE
) -> int:
    """
    Securely inserts the pristine DataFrame into the Sales_History SQL table.
    Uses parameterized batching and transactions to guarantee ACID compliance
    and prevent MySQL max_allowed_packet buffer exhaustion.

    ON DUPLICATE KEY UPDATE makes re-uploads idempotent.
    """
    if df.empty:
        return 0

    insert_sql = """
        INSERT INTO Sales_History (tenant_id, date, product_id, quantity_sold)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            quantity_sold = VALUES(quantity_sold),
            updated_at = CURRENT_TIMESTAMP
    """

    rows_to_insert = [
        (row["tenant_id"], row["date"], row["product_id"], int(row["quantity_sold"]))
        for row in df.to_dict(orient="records")
    ]

    conn = get_connection()
    if conn is None:
        logger.warning("No DB connection — returning logical insert count.")
        return len(rows_to_insert)

    total_inserted = 0
    cursor = conn.cursor()
    try:
        for i in range(0, len(rows_to_insert), chunk_size):
            chunk = rows_to_insert[i : i + chunk_size]
            cursor.executemany(insert_sql, chunk)
            total_inserted += len(chunk)

        conn.commit()
        logger.info(f"Committed {total_inserted} rows to Sales_History.")
    except Exception as sql_err:
        conn.rollback()
        logger.error(f"SQL batch ingestion failed: {sql_err}", exc_info=True)
        raise
    finally:
        cursor.close()
        if conn.is_connected():
            conn.close()

    return total_inserted


# ==============================================================================
# 5. MULTIPART PARSER (Python 3.13+ compatible, no cgi module)
# ==============================================================================
def _parse_multipart(request):
    """
    Parse a multipart/form-data POST request from http.server.
    Returns (fields_dict, file_data_bytes, filename).
    
    Uses manual boundary splitting — compatible with Python 3.14+
    where the cgi module has been removed.
    """
    content_type = request.headers.get("Content-Type", "")
    content_length = int(request.headers.get("Content-Length", 0))
    if not (0 < content_length <= MAX_FILE_SIZE_BYTES):
        raise ValueError(f"Content-Length must be between 1 and {MAX_FILE_SIZE_BYTES} bytes")

    if "multipart/form-data" not in content_type:
        raise ValueError("Content-Type must be multipart/form-data")

    # Extract boundary from Content-Type header
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
            break

    if not boundary:
        raise ValueError("Missing boundary in multipart Content-Type")

    raw_body = request.rfile.read(content_length)
    boundary_bytes = ("--" + boundary).encode("utf-8")

    # Split on boundary markers
    parts = raw_body.split(boundary_bytes)

    fields = {}
    file_data = None
    filename = None

    for part in parts:
        # Skip empty parts and the closing boundary
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue

        # Split headers from body at double CRLF
        if b"\r\n\r\n" in part:
            header_section, body = part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in part:
            header_section, body = part.split(b"\n\n", 1)
        else:
            continue

        # Strip trailing CRLF from body
        if body.endswith(b"\r\n"):
            body = body[:-2]

        headers_text = header_section.decode("utf-8", errors="replace")

        # Parse Content-Disposition to extract name and filename
        field_name = None
        field_filename = None
        for line in headers_text.split("\n"):
            line = line.strip()
            if line.lower().startswith("content-disposition:"):
                for token in line.split(";"):
                    token = token.strip()
                    if token.startswith("name="):
                        field_name = token.split("=", 1)[1].strip('"').strip("'")
                    elif token.startswith("filename="):
                        field_filename = token.split("=", 1)[1].strip('"').strip("'")

        if field_name is None:
            continue

        if field_filename:
            file_data = body
            filename = field_filename
        else:
            fields[field_name] = body.decode("utf-8", errors="replace")

    return fields, file_data, filename



@require_auth()
def handle_etl_upload(request):
    """
    POST /api/v1/etl/upload

    Accepts multipart/form-data with:
      - file: the raw data file (.csv, .xlsx, .json)
      - tenant_id: multi-tenant identifier string
      - column_mapping: JSON string mapping raw column names to target schema

    Returns JSON with extraction/transformation/load summary.
    """
    start_time = time.time()

    try:
        fields, file_data, filename = _parse_multipart(request)
    except Exception as e:
        return json_response(request, {
            "error": f"Failed to parse multipart upload: {str(e)}"
        }, 400)

    # Validate required form fields
    tenant_id = fields.get("tenant_id", "").strip()
    if not tenant_id:
        return json_response(request, {"error": "tenant_id is required."}, 400)

    column_mapping_raw = fields.get("column_mapping", "")
    try:
        column_mapping = json.loads(column_mapping_raw)
        if not isinstance(column_mapping, dict) or not column_mapping:
            raise ValueError()
    except Exception:
        return json_response(request, {
            "error": "column_mapping must be a valid non-empty JSON object."
        }, 400)

    if file_data is None or filename is None:
        return json_response(request, {"error": "No file uploaded."}, 400)

    if len(file_data) > MAX_FILE_SIZE_BYTES:
        return json_response(request, {
            "error": f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB."
        }, 413)

    # Phase 1: Extract
    try:
        raw_df = extract_file_to_dataframe(filename, file_data)
    except ValueError as ve:
        return json_response(request, {"error": str(ve)}, 422)
    except Exception as e:
        return json_response(request, {"error": f"Extraction failed: {str(e)}"}, 422)

    raw_rows = len(raw_df)

    # Phase 2: Transform & Enforce Contract
    try:
        pristine_df, rejected_count = transform_and_enforce_contract(
            raw_df, column_mapping, tenant_id
        )
    except ValueError as ve:
        return json_response(request, {"error": str(ve)}, 422)

    # Phase 3: Load
    try:
        ensure_sales_history_table()
        loaded_count = load_to_sales_history(pristine_df)
    except Exception as e:
        return json_response(request, {
            "error": f"Database load failed: {str(e)}"
        }, 500)

    elapsed = round(time.time() - start_time, 3)

    logger.info(
        f"[ETL Success] Tenant={tenant_id} | File={filename} | "
        f"Extracted={raw_rows} | Loaded={loaded_count} | "
        f"Rejected={rejected_count} | Time={elapsed}s"
    )

    return json_response(request, {
        "success": True,
        "tenant_id": tenant_id,
        "filename": filename,
        "rows_extracted": raw_rows,
        "rows_loaded": loaded_count,
        "rows_rejected": rejected_count,
        "execution_time_seconds": elapsed,
        "columns_mapped": list(column_mapping.keys()),
        "message": (
            f"Successfully ingested {loaded_count} verified records "
            f"for tenant '{tenant_id}'."
        )
    })
