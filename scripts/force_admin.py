import os
import sys
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, os.path.join(project_root, "src"))

try:
    from smartretail.db.connection import db_query, get_connection
    from smartretail.services.auth_service import hash_password_pbkdf2

    def force_admin():
        new_password = "admin123"
        new_hash = hash_password_pbkdf2(new_password)
        
        # Check users
        users = db_query("SELECT id, username, role FROM users")
        logger.info(f"Existing users in database: {users}")
        
        # See if admin exists
        admin = db_query("SELECT id FROM users WHERE username='admin'")
        if admin:
            db_query("UPDATE users SET password_hash=%s, is_active=1 WHERE username='admin'", (new_hash,), fetch=False)
            logger.info("Updated existing 'admin' user.")
        else:
            db_query("INSERT INTO users (username, password_hash, role, is_active) VALUES ('admin', %s, 'Admin', 1)", (new_hash,), fetch=False)
            logger.info("Created new 'admin' user.")
            
        logger.info("=" * 40)
        logger.info(f"SUCCESS: Login is now username 'admin' and password '{new_password}'")
        logger.info("=" * 40)

    if __name__ == "__main__":
        force_admin()
        
except ImportError as e:
    logger.error(f"Import error: {e}")
except Exception as e:
    logger.error(f"Error: {e}")
