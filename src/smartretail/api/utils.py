import json

def read_json_body(request):
    length = int(request.headers.get("Content-Length", 0))
    if length <= 0 or length > 10 * 1024 * 1024:
        return {}
    raw = request.rfile.read(length).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
