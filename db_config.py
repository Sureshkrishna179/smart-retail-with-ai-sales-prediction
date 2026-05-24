"""
db_config.py — Database connection manager for SmartRetail AI
Reads credentials from .env file and provides connection pooling.
"""

import os
import mysql.connector
from mysql.connector import pooling, Error
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "retail_sales_db"),
}

# Connection pool for efficient database access
_connection_pool = None


def get_connection_pool():
    """Create or return the existing connection pool."""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pooling.MySQLConnectionPool(
                pool_name="retail_pool",
                pool_size=5,
                pool_reset_session=True,
                **DB_CONFIG,
            )
        except Error as e:
            print(f"❌ Error creating connection pool: {e}")
            return None
    return _connection_pool


def get_connection():
    """Get a connection from the pool."""
    pool = get_connection_pool()
    if pool:
        try:
            return pool.get_connection()
        except Error as e:
            print(f"❌ Error getting connection: {e}")
            return None
    return None


def execute_query(query, params=None, fetch=False, fetchone=False):
    """Execute a query and optionally return results."""
    conn = get_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        if fetch:
            result = cursor.fetchall()
            return result
        elif fetchone:
            result = cursor.fetchone()
            return result
        else:
            conn.commit()
            return cursor.lastrowid
    except Error as e:
        print(f"❌ Query error: {e}")
        conn.rollback()
        return None
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def execute_transaction(queries_params_list):
    """Execute multiple queries in a single transaction."""
    conn = get_connection()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        for query, params in queries_params_list:
            cursor.execute(query, params or ())
        conn.commit()
        return True
    except Error as e:
        print(f"❌ Transaction error: {e}")
        conn.rollback()
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def test_connection():
    """Test the database connection."""
    conn = get_connection()
    if conn and conn.is_connected():
        info = conn.get_server_info()
        conn.close()
        return True, info
    return False, None
