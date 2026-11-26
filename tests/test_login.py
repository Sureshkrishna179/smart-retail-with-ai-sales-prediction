"""Login API tests."""

import json
import socket
import threading
import time
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from smartretail.server import DashboardHandler as APIHandler


@pytest.fixture
def api_server():
    port = _free_port()
    server = HTTPServer(("", port), APIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _post(url, body):
    req = Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Origin": "http://localhost:8080"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode())


@pytest.mark.integration
def test_login_invalid_credentials(api_server, requires_mysql):
    status, data = _post(f"{api_server}/api/login", {"username": "nobody", "password": "wrong"})
    assert status == 401
    assert "error" in data


@pytest.mark.integration
def test_login_valid_admin(api_server, requires_mysql):
    from smartretail.db.connection import db_query
    from smartretail.services.auth_service import hash_password_pbkdf2

    test_user = "ci_test_admin"
    test_pw = "TestAdmin#2026!"
    pw_hash = hash_password_pbkdf2(test_pw)

    db_query(
        "INSERT INTO users (username, password_hash, role, is_active) "
        "VALUES (%s, %s, 'Admin', TRUE) "
        "ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash), role='Admin', is_active=TRUE",
        (test_user, pw_hash),
        fetch=False,
    )
    try:
        status, data = _post(f"{api_server}/api/login", {"username": test_user, "password": test_pw})
        assert status == 200
        assert data.get("success") is True
        assert data.get("token")
        assert data["user"]["role"] == "Admin"
    finally:
        db_query("UPDATE users SET is_active=FALSE WHERE username=%s", (test_user,), fetch=False)
