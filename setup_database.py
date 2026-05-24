"""
setup_database.py — Schema initializer for SmartRetail AI
Creates tables, seeds products with units/variants, and sets up admin user.
Supports auto-migration (safe to run multiple times).
"""

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os
import hashlib
import secrets
from datetime import datetime, timedelta
import random

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DB_NAME = os.getenv("DB_NAME", "retail_sales_db")


def create_database():
    """Create the database if it doesn't exist."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
        cursor.execute(f"USE `{DB_NAME}`")
        print(f"Database '{DB_NAME}' ready.")
        return conn, cursor
    except Error as e:
        print(f"❌ Error creating database: {e}")
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
    """Seed products with units and variant pricing (36 products, some with low stock)."""
    cursor.execute("SELECT COUNT(*) as count FROM products")
    result = cursor.fetchone()
    if result[0] > 0:
        # If database has the old catalog length (37), clear and reseed everything
        if result[0] == 37:
            print("Product catalog expanded (37 -> 45). Resetting tables for a clean seed...")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute("TRUNCATE TABLE sales")
            cursor.execute("TRUNCATE TABLE inventory_log")
            cursor.execute("TRUNCATE TABLE products")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        else:
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
        # ── Extra Products added below ──────────────────────────────
        # Pulses
        ("Toor Dal 1kg",  "Grocery", "kg",   95.00, 180, 50),
        ("Moong Dal 1kg", "Grocery", "kg",  105.00, 160, 50),
        ("Chana Dal 1kg", "Grocery", "kg",   88.00,  20, 50),   # LOW STOCK
        # Spices
        ("Chilli Powder 100g",  "Spices", "pack",  28.00, 200, 60),
        ("Turmeric 100g",       "Spices", "pack",  22.00, 180, 60),
        ("Coriander Powder 100g","Spices","pack",  25.00,  15, 60),  # LOW STOCK
        ("Cumin Seeds 100g",    "Spices", "pack",  35.00, 140, 60),
        ("Mustard Seeds 100g",  "Spices", "pack",  18.00,   8, 60),  # CRITICALLY LOW
        # Dairy
        ("Butter 100g",     "Dairy", "pack",   52.00, 120, 40),
        ("Paneer 200g",     "Dairy", "pack",   85.00,  12, 40),   # LOW STOCK
        ("Ghee 500ml",      "Dairy", "bottle", 350.00,  60, 20),
        # Beverages
        ("Coffee 100g",  "Beverages", "pack",  90.00, 130, 40),
        ("Horlicks 200g","Beverages", "pack", 135.00,   9, 30),   # LOW STOCK
        ("Boost 200g",   "Beverages", "pack", 125.00,  70, 30),
        # Cleaning
        ("Washing Powder 1kg", "Cleaning", "pack",  65.00, 110, 40),
        ("Dish Soap 500ml",    "Cleaning", "bottle", 45.00,  18, 40),  # LOW STOCK
        # New Products Added
        ("Milk 500ml",         "Dairy",    "packet", 30.00, 150, 40),
        ("Curd 500g",          "Dairy",    "cup",    45.00,  80, 20),
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
    """Seed 35+ Indian and Tamil Nadu festivals."""
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


def seed_demo_sales(cursor):
    """Generate realistic demo sales data for training the ML model."""
    cursor.execute("SELECT COUNT(*) as count FROM sales")
    result = cursor.fetchone()
    if result[0] > 0:
        print("Sales data already seeded, skipping...")
        return

    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()

    sales_records = []
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 12, 31)
    current_date = start_date

    while current_date <= end_date:
        for prod_id, name, price in products:
            # Base sales quantity varies by product
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

            # Festival boost (simplified check)
            month = current_date.month
            day = current_date.day
            if (month == 1 and 14 <= day <= 17):  # Pongal
                base_qty = int(base_qty * 1.5)
            elif (month == 10 and 24 <= day <= 31) or (month == 11 and 1 <= day <= 3):  # Diwali
                base_qty = int(base_qty * 1.5)
            elif (month == 12 and day >= 25) or (month == 1 and day <= 2):  # New Year
                base_qty = int(base_qty * 1.4)

            # Add some randomness
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


def hash_password_pbkdf2(password):
    """Hash password with PBKDF2-HMAC-SHA256 + random salt. Returns 'salt_hex:hash_hex'."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def seed_users(cursor):
    """Create default users for all 3 roles: Admin, Manager, Staff.
    Uses PBKDF2-HMAC-SHA256 password hashing (100K iterations)."""
    cursor.execute("SELECT COUNT(*) as count FROM users")
    result = cursor.fetchone()
    if result[0] > 0:
        print("Users already seeded, skipping...")
        return

    users = [
        ("admin",   hash_password_pbkdf2("admin123"),   "Admin"),
        ("manager", hash_password_pbkdf2("manager123"), "Manager"),
        ("staff",   hash_password_pbkdf2("staff123"),   "Staff"),
    ]
    cursor.executemany(
        """INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)""",
        users,
    )
    print("Users created (PBKDF2 hashed):")
    print("  admin   / admin123   (Admin)")
    print("  manager / manager123 (Manager)")
    print("  staff   / staff123   (Staff)")


def main():
    """Run the full database setup."""
    print("\nSmartRetail AI -- Database Setup\n" + "=" * 40)

    conn, cursor = create_database()
    if conn is None:
        print("❌ Failed to connect to MySQL. Check your .env configuration.")
        return

    try:
        create_tables(cursor)
        seed_products(cursor)
        seed_festivals(cursor)
        seed_demo_sales(cursor)
        seed_users(cursor)
        conn.commit()
        print("\nDatabase setup complete!")
        print(f"   Database: {DB_NAME}")
        print(f"   Host: {DB_CONFIG['host']}")
        print("   Run: python serve_dashboard.py to start the server.\n")
    except Error as e:
        print(f"❌ Setup error: {e}")
        conn.rollback()
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
