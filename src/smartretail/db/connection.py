import logging
import mysql.connector
from mysql.connector import pooling, Error
from smartretail.config import settings

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": settings.db_host,
    "user": settings.db_user,
    "password": settings.db_password,
    "database": settings.db_name,
}

_connection_pool = None

def get_connection_pool():
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
            logger.error(f"Error creating connection pool: {e}")
            return None
    return _connection_pool

def get_connection():
    pool = get_connection_pool()
    if pool:
        try:
            return pool.get_connection()
        except Error as e:
            logger.error(f"Error getting connection: {e}")
    return None

def db_query(query, params=None, fetch=True, fetchone=False):
    """Execute a query and optionally return results."""
    conn = get_connection()
    if conn is None:
        return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        if fetch:
            return cursor.fetchall()
        elif fetchone:
            return cursor.fetchone()
        else:
            conn.commit()
            return cursor.lastrowid
    except Error as e:
        logger.error(f"Query error: {e}")
        conn.rollback()
        return None
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def db_transaction(queries_params_list):
    """Execute multiple queries in a single transaction."""
    conn = get_connection()
    if conn is None:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        for query, params in queries_params_list:
            cursor.execute(query, params or ())
        conn.commit()
        return True
    except Error as e:
        logger.error(f"Transaction error: {e}")
        conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
