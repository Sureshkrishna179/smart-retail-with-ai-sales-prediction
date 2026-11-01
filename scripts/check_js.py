import os
import subprocess
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
js_file = repo_root / "frontend" / "js" / "main.js"
out_file = repo_root / "js_check.txt"

try:
    res = subprocess.run(["node", "-c", str(js_file)], capture_output=True, text=True)
    out_file.write_text(f"RC: {res.returncode}\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}\n", encoding="utf-8")
    print(f"JS syntax check finished with RC: {res.returncode}")
    if res.stderr:
        print(res.stderr)
except Exception as e:
    out_file.write_text(f"Error: {e}\n", encoding="utf-8")
    print(f"Error checking JS: {e}")
