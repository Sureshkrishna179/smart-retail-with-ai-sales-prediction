import os
import subprocess
try:
    with open("c:\\MY Projects\\Project AI Sales\\js_check.txt", "w") as f:
        res = subprocess.run(["node", "-c", "c:\\MY Projects\\Project AI Sales\\frontend\\js\\main.js"], capture_output=True, text=True)
        f.write(f"RC: {res.returncode}\n")
        f.write(f"STDOUT: {res.stdout}\n")
        f.write(f"STDERR: {res.stderr}\n")
except Exception as e:
    with open("c:\\MY Projects\\Project AI Sales\\js_check.txt", "w") as f:
        f.write(f"Error: {e}\n")
