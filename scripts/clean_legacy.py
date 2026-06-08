import shutil
import os

shutil.rmtree(r'c:\MY Projects\Project AI Sales\backend\legacy', ignore_errors=True)
if os.path.exists(r'c:\MY Projects\Project AI Sales\requirements-legacy.txt'):
    os.remove(r'c:\MY Projects\Project AI Sales\requirements-legacy.txt')
