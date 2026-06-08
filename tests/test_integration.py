"""Integration tests: database connectivity and HTTP API (optional MySQL)."""

import json
import socket
import threading
import time
from http.server import HTTPServer
from urllib.request import Request, urlopen

import pytest

from serve_dashboard import APIHandler


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def api_server():
    port = _free_port()
    server = HTTPServer(("", port), APIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{port}"
    yield base
    server.shutdown()
    server.server_close()


def _get(url: str):
    req = Request(url, headers={"Origin": "http://localhost:8080"})
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode())


@pytest.mark.integration
def test_api_festivals(api_server):
    status, data = _get(f"{api_server}/api/festivals")
    assert status == 200
    assert "festivals" in data
    assert len(data["festivals"]) >= 20


@pytest.mark.integration
def test_api_csv_template(api_server):
    req = Request(
        f"{api_server}/api/csv-template",
        headers={"Origin": "http://localhost:8080"},
    )
    with urlopen(req, timeout=5) as resp:
        body = resp.read().decode()
    assert "Date,Product,Sales_Qty" in body


@pytest.mark.integration
def test_dashboard_html_served(api_server):
    req = Request(f"{api_server}/", headers={"Origin": "http://localhost:8080"})
    with urlopen(req, timeout=5) as resp:
        html = resp.read().decode()
    assert resp.status == 200
    assert "html" in html.lower() or "SmartRetail" in html or len(html) > 100


@pytest.mark.integration
def test_mysql_connection(requires_mysql):
    from db_config import get_connection

    conn = get_connection()
    assert conn is not None
    conn.close()


@pytest.mark.integration
def test_api_products_when_db_up(requires_mysql, api_server):
    status, data = _get(f"{api_server}/api/products")
    assert status == 200
    assert "products" in data
    assert len(data["products"]) >= 1
