import sys
from pathlib import Path

# Safe Windows UTF-8 stdout configuration
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add src directory to path (scripts/ -> root -> src)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from smartretail.db.connection import get_connection

print("Attempting to connect to the database...")
conn = get_connection()

if conn is not None and conn.is_connected():
    print("✅ Successfully connected to the database!")
    
    # Check products and sales count
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM products")
    products_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM sales")
    sales_count = cursor.fetchone()['count']
    
    print(f"📊 Found {products_count} products and {sales_count} sales records in the database.")
    
    cursor.close()
    conn.close()
else:
    print("❌ Failed to connect to the database. Please check if MySQL is running and your .env credentials are correct.")
