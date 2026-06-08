"""
setup_database.py — Schema initializer for SmartRetail AI
Creates tables, seeds products with units/variants, and sets up admin user.
Supports auto-migration (safe to run multiple times).
"""

import os
import csv
import hashlib
import secrets
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

from paths import ENV_FILE, GROCERY_CSV, PROJECT_ROOT

load_dotenv(dotenv_path=ENV_FILE)
project_root = PROJECT_ROOT

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DB_NAME = os.getenv("DB_NAME", "retail_sales_db")


def create_database():
    """Create the database if it doesn't exist or connect directly to the existing cloud database."""
    host = DB_CONFIG.get("host", "localhost")
    is_local = host in ("localhost", "127.0.0.1", "::1")
    
    if is_local:
        # Local connection: try creating database first
        try:
            conn = mysql.connector.connect(
                host=DB_CONFIG["host"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"]
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
            cursor.execute(f"USE `{DB_NAME}`")
            print(f"Database '{DB_NAME}' ready.")
            return conn, cursor
        except Error as e:
            print(f"⚠️ Local database creation failed, trying direct connection: {e}")
            
    # Connect directly to the specified database (essential for cloud hosting like Clever Cloud/Render)
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_NAME
        )
        cursor = conn.cursor()
        print(f"Connected directly to database '{DB_NAME}'.")
        return conn, cursor
    except Error as e:
        print(f"❌ Error connecting to database: {e}")
        return None, None


def create_tables(cursor):
    """Create all required tables."""
    # Products table with unit column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) DEFAULT 'General',
            unit VARCHAR(20) DEFAULT 'piece',
            price DECIMAL(10,2) NOT NULL,
            current_stock INT DEFAULT 0,
            min_stock_level INT DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    # Sales transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            unit_price DECIMAL(10,2) NOT NULL,
            total_amount DECIMAL(10,2) NOT NULL,
            sale_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    # Inventory log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            change_type ENUM('sale', 'restock', 'adjustment') NOT NULL,
            quantity INT NOT NULL,
            previous_stock INT DEFAULT 0,
            new_stock INT DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    # Users table for admin panel
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role ENUM('Admin', 'Manager', 'Staff', 'Viewer') DEFAULT 'Staff',
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP NULL,
            failed_attempts INT NOT NULL DEFAULT 0,
            locked_until TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # MED-02: Add lockout columns to existing deployments (idempotent migration)
    for col_sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_attempts INT NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP NULL",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass  # Column already exists on older MySQL that doesn't support IF NOT EXISTS

    # Audit log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            action VARCHAR(100) NOT NULL,
            details TEXT,
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    # Festival calendar table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS festivals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) DEFAULT 'National',
            start_month INT NOT NULL,
            start_day INT NOT NULL,
            end_month INT NOT NULL,
            end_day INT NOT NULL,
            sales_multiplier DECIMAL(3,1) DEFAULT 1.5,
            description TEXT
        )
    """)

    print("All tables created successfully.")


def seed_products(cursor):
    """Seed products with units and variant pricing."""
    cursor.execute("SELECT COUNT(*) as count FROM products")
    result = cursor.fetchone()
    if result[0] > 0:
        print("Products already seeded, skipping...")
        return

    products = [
        # Rice variants
        ("Rice 1kg",  "Grocery", "kg",     50.00,  200, 50),
        ("Rice 5kg",  "Grocery", "kg",    240.00,  100, 30),
        ("Rice 10kg", "Grocery", "kg",    470.00,   60, 20),
        # Wheat variants
        ("Wheat 1kg",  "Grocery", "kg",   45.00,  180, 50),
        ("Wheat 5kg",  "Grocery", "kg",  215.00,   80, 25),
        # Sugar variants
        ("Sugar 1kg",  "Grocery", "kg",   42.00,  150, 50),
        ("Sugar 5kg",  "Grocery", "kg",  200.00,   70, 20),
        # Oil variants
        ("Oil 1 litre", "Grocery", "litre", 155.00, 120, 40),
        ("Oil 5 litre", "Grocery", "litre", 720.00,  40, 15),
        # Tea variants
        ("Tea 100g",  "Beverages", "pack",  45.00, 200, 60),
        ("Tea 250g",  "Beverages", "pack", 105.00, 150, 40),
        ("Tea 500g",  "Beverages", "pack", 195.00,  80, 25),
        # Biscuits variants
        ("Biscuits Small",  "Snacks", "packet",  10.00, 300, 100),
        ("Biscuits Medium", "Snacks", "packet",  20.00, 250,  80),
        ("Biscuits Large",  "Snacks", "packet",  40.00, 150,  50),
        ("Biscuits Family", "Snacks", "packet",  75.00, 100,  30),
        # Soap variants
        ("Soap Bar",       "Personal Care", "piece", 35.00, 200, 60),
        ("Soap Combo Pack","Personal Care", "pack",  90.00,  80, 25),
        # Shampoo variants
        ("Shampoo 100ml", "Personal Care", "bottle",  65.00, 150, 40),
        ("Shampoo 200ml", "Personal Care", "bottle", 120.00, 100, 30),
        ("Shampoo 500ml", "Personal Care", "bottle", 250.00,  50, 15),
        # Pulses
        ("Toor Dal 1kg",  "Grocery", "kg",   95.00, 180, 50),
        ("Moong Dal 1kg", "Grocery", "kg",  105.00, 160, 50),
        ("Chana Dal 1kg", "Grocery", "kg",   88.00,  20, 50),
        # Spices
        ("Chilli Powder 100g",  "Spices", "pack",  28.00, 200, 60),
        ("Turmeric 100g",       "Spices", "pack",  22.00, 180, 60),
        ("Coriander Powder 100g","Spices","pack",  25.00,  15, 60),
        ("Cumin Seeds 100g",    "Spices", "pack",  35.00, 140, 60),
        ("Mustard Seeds 100g",  "Spices", "pack",  18.00,   8, 60),
        # Dairy
        ("Butter 100g",     "Dairy", "pack",   52.00, 120, 40),
        ("Paneer 200g",     "Dairy", "pack",   85.00,  12, 40),
        ("Ghee 500ml",      "Dairy", "bottle", 350.00,  60, 20),
        # Beverages
        ("Coffee 100g",  "Beverages", "pack",  90.00, 130, 40),
        ("Horlicks 200g","Beverages", "pack", 135.00,   9, 30),
        ("Boost 200g",   "Beverages", "pack", 125.00,  70, 30),
        # Cleaning
        ("Washing Powder 1kg", "Cleaning", "pack",  65.00, 110, 40),
        ("Dish Soap 500ml",    "Cleaning", "bottle", 45.00,  18, 40),
        # New Products
        ("Milk 500ml",         "Dairy",    "packet", 30.00, 150, 40),
        ("Curd 500g",          "Dairy",    "packet", 45.00,  80, 20),
        ("Tata Salt 1kg",      "Grocery",  "packet", 28.00, 200, 50),
        ("Sona Masuri Rice 5kg","Grocery",  "kg",    320.00,  90, 20),
        ("Urad Dal 1kg",       "Grocery",  "kg",    120.00, 100, 30),
        ("Coconut Oil 500ml",  "Grocery",  "bottle",140.00,  80, 25),
        ("Cardamom 50g",       "Spices",   "pack",  110.00,  60, 15),
        ("Garlic 250g",        "Grocery",  "pack",   60.00,  70, 20),
    ]

    cursor.executemany(
        """INSERT INTO products (name, category, unit, price, current_stock, min_stock_level) 
           VALUES (%s, %s, %s, %s, %s, %s)""",
        products,
    )
    print(f"Seeded {len(products)} products ({len([p for p in products if p[4] < p[5]])} with low stock).")


def seed_festivals(cursor):
    """Seed Indian and Tamil Nadu festivals."""
    cursor.execute("SELECT COUNT(*) as count FROM festivals")
    result = cursor.fetchone()
    if result[0] > 0:
        print("Festivals already seeded, skipping...")
        return

    festivals = [
        # Tamil Nadu Festivals
        ("Pongal", "Tamil Nadu", 1, 14, 1, 17, 1.5, "Tamil harvest festival"),
        ("Thai Poosam", "Tamil Nadu", 1, 25, 1, 25, 1.3, "Festival of Lord Murugan"),
        ("Masi Magam", "Tamil Nadu", 2, 24, 2, 24, 1.2, "Sacred bathing festival"),
        ("Panguni Uthiram", "Tamil Nadu", 3, 25, 3, 25, 1.2, "Festival of divine marriages"),
        ("Chithirai Festival", "Tamil Nadu", 4, 14, 4, 28, 1.4, "Tamil New Year celebrations"),
        ("Aadi Perukku", "Tamil Nadu", 7, 18, 7, 18, 1.3, "Monsoon water festival"),
        ("Vinayagar Chaturthi", "Tamil Nadu", 9, 7, 9, 7, 1.4, "Lord Ganesha festival"),
        ("Navaratri", "Tamil Nadu", 10, 3, 10, 12, 1.5, "Nine nights festival"),
        ("Karthigai Deepam", "Tamil Nadu", 11, 25, 11, 25, 1.4, "Festival of lights (TN)"),
        # National Festivals
        ("Republic Day", "National", 1, 26, 1, 26, 1.2, "National holiday"),
        ("Holi", "National", 3, 14, 3, 14, 1.3, "Festival of colors"),
        ("Ram Navami", "National", 4, 6, 4, 6, 1.2, "Birth of Lord Rama"),
        ("Independence Day", "National", 8, 15, 8, 15, 1.2, "National holiday"),
        ("Janmashtami", "National", 8, 26, 8, 26, 1.3, "Birth of Lord Krishna"),
        ("Gandhi Jayanti", "National", 10, 2, 10, 2, 1.1, "National holiday"),
        ("Dussehra", "National", 10, 12, 10, 12, 1.4, "Victory of good over evil"),
        ("Diwali", "National", 10, 24, 11, 3, 1.5, "Festival of lights"),
        ("Christmas", "National", 12, 24, 12, 25, 1.3, "Christmas celebrations"),
        ("New Year", "National", 12, 31, 1, 2, 1.4, "New Year celebrations"),
        ("Eid ul-Fitr", "National", 4, 10, 4, 12, 1.4, "End of Ramadan"),
        ("Eid ul-Adha", "National", 6, 17, 6, 19, 1.3, "Festival of sacrifice"),
        ("Onam", "National", 9, 5, 9, 5, 1.3, "Kerala harvest festival"),
        ("Raksha Bandhan", "National", 8, 9, 8, 9, 1.3, "Sibling bond festival"),
        ("Makar Sankranti", "National", 1, 14, 1, 14, 1.3, "Harvest festival"),
        ("Guru Nanak Jayanti", "National", 11, 15, 11, 15, 1.2, "Sikh festival"),
        # Shopping Seasons
        ("Wedding Season Summer", "Shopping", 4, 15, 6, 15, 1.3, "Peak wedding season"),
        ("Wedding Season Winter", "Shopping", 11, 15, 12, 15, 1.3, "Winter wedding season"),
        ("Back to School", "Shopping", 6, 1, 6, 15, 1.2, "School reopening shopping"),
        ("Exam Season", "Shopping", 3, 1, 3, 31, 1.1, "Student exam preparation"),
        ("Deepavali Shopping", "National", 10, 15, 10, 28, 1.5, "Pre-Diwali shopping rush"),
        ("Summer Vacation", "Shopping", 5, 1, 5, 31, 1.2, "Summer holiday shopping"),
        ("Monsoon Season", "Shopping", 7, 1, 8, 31, 1.1, "Rainy season essentials"),
        ("Pongal Shopping", "Tamil Nadu", 1, 7, 1, 14, 1.4, "Pre-Pongal shopping rush"),
        ("Thai Pongal", "Tamil Nadu", 1, 15, 1, 15, 1.5, "Main Pongal day"),
        ("Mattu Pongal", "Tamil Nadu", 1, 16, 1, 16, 1.2, "Cattle worship day"),
    ]

    cursor.executemany(
        """INSERT INTO festivals (name, category, start_month, start_day, end_month, end_day, sales_multiplier, description) 
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        festivals,
    )
    print(f"Seeded {len(festivals)} festivals.")


def seed_sales_from_grocery_csv(cursor):
    """Import sales from data/grocery_sales_realistic.csv when product names match catalog."""
    csv_path = GROCERY_CSV
    if not csv_path.is_file():
        return False

    cursor.execute("SELECT id, name, price FROM products")
    catalog = {row[1]: (row[0], float(row[2])) for row in cursor.fetchall()}
    sales_records = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pname = row.get("Product", "").strip()
            if pname not in catalog:
                continue
            try:
                qty = int(float(row.get("Sales_Qty", 0)))
            except (ValueError, TypeError):
                continue
            if qty < 1:
                continue
            sale_date = row.get("Date", "").strip()
            pid, price = catalog[pname]
            total = round(price * qty, 2)
            sales_records.append((pid, qty, price, total, sale_date))

    if len(sales_records) < 100:
        return False

    batch_size = 500
    for i in range(0, len(sales_records), batch_size):
        batch = sales_records[i : i + batch_size]
        cursor.executemany(
            """INSERT INTO sales (product_id, quantity, unit_price, total_amount, sale_date)
               VALUES (%s, %s, %s, %s, %s)""",
            batch,
        )
    print(f"Imported {len(sales_records)} sales rows from grocery CSV ({csv_path.name}).")
    return True


def seed_demo_sales(cursor):
    """Generate realistic demo sales data for training the ML model."""
    cursor.execute("SELECT COUNT(*) as count FROM sales")
    result = cursor.fetchone()
    if result[0] > 0:
        print("Sales data already seeded, skipping...")
        return

    if seed_sales_from_grocery_csv(cursor):
        return

    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()

    sales_records = []
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 12, 31)
    current_date = start_date

    while current_date <= end_date:
        for prod_id, name, price in products:
            if "Rice" in name or "Wheat" in name or "Sugar" in name:
                base_qty = random.randint(5, 25)
            elif "Oil" in name:
                base_qty = random.randint(3, 15)
            elif "Tea" in name:
                base_qty = random.randint(5, 20)
            elif "Biscuits" in name:
                base_qty = random.randint(10, 40)
            elif "Soap" in name or "Shampoo" in name:
                base_qty = random.randint(3, 12)
            else:
                base_qty = random.randint(5, 15)

            # Weekend boost
            if current_date.weekday() >= 5:
                base_qty = int(base_qty * 1.2)

            # Festival boost
            month = current_date.month
            day = current_date.day
            if (month == 1 and 14 <= day <= 17):  # Pongal
                base_qty = int(base_qty * 1.5)
            elif (month == 10 and 24 <= day <= 31) or (month == 11 and 1 <= day <= 3):  # Diwali
                base_qty = int(base_qty * 1.5)
            elif (month == 12 and day >= 25) or (month == 1 and day <= 2):  # New Year
                base_qty = int(base_qty * 1.4)

            qty = max(1, base_qty + random.randint(-3, 3))
            total = round(float(price) * qty, 2)

            sales_records.append((
                prod_id, qty, float(price), total,
                current_date.strftime("%Y-%m-%d")
            ))

        current_date += timedelta(days=1)

    # Batch insert
    batch_size = 500
    for i in range(0, len(sales_records), batch_size):
        batch = sales_records[i:i + batch_size]
        cursor.executemany(
            """INSERT INTO sales (product_id, quantity, unit_price, total_amount, sale_date) 
               VALUES (%s, %s, %s, %s, %s)""",
            batch,
        )

    print(f"Seeded {len(sales_records)} sales records (1 year of data).")


# CRIT-03: hash_password_pbkdf2 is now imported from auth_service (600K iterations).
# This function is kept as a thin wrapper for backward compat with any callers in this file.
def hash_password_pbkdf2(password):
    """Hash password with PBKDF2-HMAC-SHA256 (600K iterations) — delegates to auth_service."""
    from smartretail.services.auth_service import hash_password_pbkdf2 as _hash
    return _hash(password)


def _generate_secure_password(length=20):
    """Generate a cryptographically random password meeting complexity requirements."""
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each required character class
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    # Shuffle to avoid predictable positions
    random.shuffle(password)
    return "".join(password)


import string

def create_first_admin(conn, cursor):
    """Create the first admin user with a securely generated random password."""
    cursor.execute("SELECT COUNT(*) AS c FROM users WHERE role='Admin'")
    if cursor.fetchone()[0] > 0:
        return
        
    pw = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%^") for _ in range(20))
    # We must import hash_password_pbkdf2 here or define it, since we are moving it.
    from smartretail.services.auth_service import hash_password_pbkdf2
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'Admin')",
        ("admin", hash_password_pbkdf2(pw))
    )
    conn.commit()
    print(f"\n{'='*50}\nFirst-run admin password: {pw}\nChange it immediately!\n{'='*50}\n")

def main():
    """Run the database setup script."""
    print("\nSmartRetail AI -- Database Setup\n" + "=" * 40)

    conn, cursor = create_database()
    if conn is None:
        import sys
        print("❌ Failed to connect to MySQL. Check your database configuration.")
        sys.exit(1)

    grocery_csv = GROCERY_CSV
    if not grocery_csv.is_file():
        print("Tip: run 'python scripts/generate_grocery_sales.py' for realistic sales data.")

    try:
        assert cursor is not None
        create_tables(cursor)
        seed_products(cursor)
        seed_festivals(cursor)
        seed_demo_sales(cursor)
        
        import sys
        sys.path.insert(0, str(project_root / "src"))
        create_first_admin(conn, cursor)
        
        # SECURITY-FIX applied: Least privilege database user (Fix 15)
        cursor.execute("CREATE USER IF NOT EXISTS 'retail_app'@'localhost' IDENTIFIED BY %s", (DB_CONFIG["password"],))
        cursor.execute("GRANT SELECT, INSERT, UPDATE ON retail_sales_db.products TO 'retail_app'@'localhost'")
        cursor.execute("GRANT SELECT, INSERT ON retail_sales_db.sales TO 'retail_app'@'localhost'")
        cursor.execute("GRANT SELECT, INSERT, UPDATE ON retail_sales_db.users TO 'retail_app'@'localhost'")
        cursor.execute("GRANT SELECT, INSERT ON retail_sales_db.audit_log TO 'retail_app'@'localhost'")
        cursor.execute("FLUSH PRIVILEGES")
        
        conn.commit()
        print("\nDatabase setup complete!")
        print(f"   Database: {DB_NAME}")
        print(f"   Host: {DB_CONFIG['host']}")
        print("   Run: python backend/serve_dashboard.py to start the server.\n")
    except Error as e:
        print(f"❌ Setup error: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            if cursor:
                cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
