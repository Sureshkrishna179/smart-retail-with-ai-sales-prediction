import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from smartretail.db.connection import get_connection

print("Attempting to connect to the database...")
conn = get_connection()

if conn is not None and conn.is_connected():
    print("✅ Successfully connected to the database!")
    
    # Let's check how many products and sales are in there
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
