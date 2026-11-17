from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as app_module


def _assert_security_headers(response) -> None:
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp
    cache_directives = {part.strip().lower() for part in response.headers["Cache-Control"].split(",")}
    assert "no-store" in cache_directives


def test_api_responses_have_security_headers_and_no_store() -> None:
    response = app_module.app.test_client().get("/auth/me")

    assert response.status_code in {200, 401}
    _assert_security_headers(response)


def test_html_responses_have_security_headers_and_no_store() -> None:
    response = app_module.app.test_client().get("/login")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    _assert_security_headers(response)
