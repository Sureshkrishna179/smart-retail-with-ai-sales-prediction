import os
import sys
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
project_root = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=env_path)

# Set pythonpath so we can import smartretail
sys.path.insert(0, os.path.join(project_root, "src"))

try:
    from smartretail.db.connection import db_query
    from smartretail.services.auth_service import hash_password_pbkdf2

    def reset_admin_password():
        username = "admin"
        import mysql.connector
        
        conn = None
        credentials_to_try = [
            (os.getenv("DB_USER", "root"), os.getenv("DB_PASSWORD", "")),
            ("root", ""),
            ("root", "root"),
            ("root", "password"),
            ("retail_app", "CHANGE_ME_ROTATE_IMMEDIATELY"),
            ("retail_app", ""),
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
                    logger.info(f"Connected to DB using user: '{user}' and password: '{pwd}'")
                    break
            except Exception:
                continue
                
        if not conn or not conn.is_connected():
            logger.error("Could not connect to database with any common credentials.")
            return

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
        user_row = cursor.fetchone()
        
        if not user_row:
            logger.error(f"User '{username}' not found in database.")
            return

        new_hash = hash_password_pbkdf2(new_password)
        cursor.execute("UPDATE users SET password_hash=%s WHERE username=%s", (new_hash, username))
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("=" * 40)
        logger.info(f"SUCCESS: Password for '{username}' has been reset!")
        logger.info(f"New Password: {new_password}")
        logger.info("=" * 40)

    if __name__ == "__main__":
        reset_admin_password()
        
except ImportError as e:
    logger.error(f"Failed to import project modules: {e}")
    logger.error("Make sure you are running this from the project root.")
