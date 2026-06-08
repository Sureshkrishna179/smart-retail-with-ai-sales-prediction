import urllib.request
import os

urls = [
    "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js",
    "https://unpkg.com/chart.js@4.4.0/dist/chart.umd.min.js",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"
]

os.makedirs("frontend", exist_ok=True)

for url in urls:
    try:
        print(f"Trying {url}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            with open("frontend/chart.js", "wb") as f:
                f.write(content)
            print("Successfully downloaded!")
            break
    except Exception as e:
        print(f"Failed: {e}")
