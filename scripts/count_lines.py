import os

def count_lines(directory):
    total_files = 0
    total_lines = 0
    exclude_dirs = {'.venv', '.git', '__pycache__', 'node_modules', 'data', 'docs', 'tests', '.pytest_cache'}
    exclude_exts = {'.db', '.png', '.jpg', '.pyc', '.ico', '.pyo', '.csv', '.xlsx'}

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in exclude_exts):
                continue
            
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = [line for line in f if line.strip()]
                    total_lines += len(lines)
                    total_files += 1
            except Exception:
                pass

    return total_files, total_lines

if __name__ == '__main__':
    files, lines = count_lines('.')
    print(f"Total Source Code Files: {files}")
    print(f"Total Lines of Code (excluding blanks): {lines}")
