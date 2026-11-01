import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_root = Path(__file__).resolve().parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, str(project_root / "src"))

try:
    from smartretail.db.connection import db_query
    from smartretail.services.auth_service import hash_password_pbkdf2

    def reset_admin_password():
        username = "admin"
        new_password = "admin123"
        import mysql.connector
        
        conn = None
        credentials_to_try = [
            (os.getenv("DB_USER", "root"), os.getenv("DB_PASSWORD", "")),
            ("root", ""),
            ("root", "root"),
            ("root", "password"),
            ("retail_app", os.getenv("DB_PASSWORD", ""))
        ]
        
        for user, pwd in credentials_to_try:
            try:
                conn = mysql.connector.connect(
                    host=os.getenv("DB_HOST", "localhost"),
                    user=user,
                    password=pwd,
                    database=os.getenv("DB_NAME", "retail_sales_db")
                )
                if conn.is_connected():
                    logger.info("Connected to DB successfully.")
                    break
            except Exception:
                continue
                
        if not conn or not conn.is_connected():
            logger.error("Could not connect to database with available credentials.")
            return

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
        user_row = cursor.fetchone()
        
        if not user_row:
            logger.error("User '%s' not found in database.", username)
            cursor.close()
            conn.close()
            return

        new_hash = hash_password_pbkdf2(new_password)
        cursor.execute("UPDATE users SET password_hash=%s WHERE username=%s", (new_hash, username))
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("SUCCESS: Password for '%s' has been reset successfully.", username)

    if __name__ == "__main__":
        reset_admin_password()
        
except ImportError as e:
    logger.error("Failed to import project modules: %s", e)
