"""
Root entry point to start the SmartRetail AI server directly:
    py server.py
"""
import sys
from pathlib import Path

# Automatically ensure 'src' is in sys.path
_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smartretail.server import run

if __name__ == "__main__":
    run()
