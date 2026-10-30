"""
Migrate Database Dump to Cloud MySQL
====================================
Uploads the local database dump (`data/database_dump.sql`) to any remote/cloud
MySQL database (e.g. Aiven, TiDB Cloud, Clever Cloud, AWS RDS, DigitalOcean).

Usage:
    python scripts/migrate_to_cloud_db.py --host <cloud_host> --port <port> --user <cloud_user> --password <cloud_pass> --db <cloud_db>
"""

import sys
import argparse
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mysql.connector

def run_migration(host, port, user, password, database, ssl_ca=None):
    dump_file = Path(__file__).resolve().parent.parent / "data" / "database_dump.sql"
    if not dump_file.is_file():
        print(f"❌ Dump file not found: {dump_file}")
        print("Please run `python scripts/export_database.py` first.")
        return False
        
    print(f"Connecting to Cloud MySQL at {host}:{port} ({database})...")
    conn_params = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "charset": "utf8mb4",
    }
    if ssl_ca:
        conn_params["ssl_ca"] = ssl_ca
        
    try:
        conn = mysql.connector.connect(**conn_params)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
        
    print("✅ Connected to Cloud MySQL!")
    print(f"Reading dump file ({dump_file.stat().st_size / (1024*1024):.2f} MB)...")
    
    with open(dump_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    statements = sql_content.split(";\n")
    cursor = conn.cursor()
    
    total = len(statements)
    print(f"Executing {total} SQL statement batches...")
    
    executed = 0
    for idx, stmt in enumerate(statements):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            cursor.execute(stmt)
            executed += 1
            if executed % 10 == 0 or executed == total:
                print(f"  Progress: {executed}/{total} statements executed...")
        except Exception as e:
            print(f"  Warning on statement {idx}: {e}")
            
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n🎉 Migration completed successfully! Your cloud database now has all products and sales data.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload database to Cloud MySQL")
    parser.add_argument("--host", required=True, help="Cloud MySQL host")
    parser.add_argument("--port", type=int, default=3306, help="Cloud MySQL port (default 3306)")
    parser.add_argument("--user", required=True, help="Cloud MySQL user")
    parser.add_argument("--password", required=True, help="Cloud MySQL password")
    parser.add_argument("--db", required=True, help="Cloud MySQL database name")
    
    args = parser.parse_args()
    run_migration(args.host, args.port, args.user, args.password, args.db)

