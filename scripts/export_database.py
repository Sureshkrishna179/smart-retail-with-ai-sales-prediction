"""
Export Local MySQL Database Dump
================================
Exports all tables, schemas, and records (all 16,432 sales rows, 146 products,
users, festivals, stores, and audit logs) into a single standalone SQL file.
"""

import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from smartretail.db.connection import get_connection

def export_db(output_path: Path):
    conn = get_connection()
    if not conn:
        print("❌ Could not connect to local MySQL database. Is it running?")
        return False
        
    cursor = conn.cursor()
    print("Connected to local MySQL. Exporting tables...")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- SmartRetail AI Complete Database Export\n")
        f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
        
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        
        for table in tables:
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            create_stmt = cursor.fetchone()[1]
            f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
            f.write(create_stmt + ";\n\n")
            
            cursor.execute(f"SELECT * FROM `{table}`")
            rows = cursor.fetchall()
            if rows:
                cursor.execute(f"DESCRIBE `{table}`")
                cols = [f"`{c[0]}`" for c in cursor.fetchall()]
                cols_str = ", ".join(cols)
                
                print(f"  Exporting `{table}`: {len(rows)} records...")
                f.write(f"INSERT INTO `{table}` ({cols_str}) VALUES\n")
                
                batch_size = 500
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    val_lines = []
                    for r in batch:
                        formatted = []
                        for v in r:
                            if v is None:
                                formatted.append("NULL")
                            elif isinstance(v, (int, float)):
                                formatted.append(str(v))
                            else:
                                esc = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
                                formatted.append(f"'{esc}'")
                        val_lines.append("(" + ", ".join(formatted) + ")")
                    
                    if i + batch_size < len(rows):
                        f.write(",\n".join(val_lines) + ",\n")
                    else:
                        f.write(",\n".join(val_lines) + ";\n\n")
            else:
                print(f"  Table `{table}` is empty.")
                
        f.write("SET FOREIGN_KEY_CHECKS=1;\n")
        
    cursor.close()
    conn.close()
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Successfully exported complete database to: {output_path} ({size_mb:.2f} MB)")
    return True

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "database_dump.sql"
    export_db(out)
