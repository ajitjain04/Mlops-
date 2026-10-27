import importlib.util
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adaptivephish.api.app import INDEX_PAGE, create_app
from test_api import make_loaded


@pytest.fixture
def client():
    with TestClient(create_app(loaded=make_loaded())) as c:
        yield c


def test_root_serves_html_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "AdaptivePhish" in r.text and "Lifecycle results" in r.text
    assert "Controlled replay results; the retraining loop is not live on this server." in r.text


def test_page_headers_lock_down_content(client):
    h = client.get("/").headers
    csp = h["content-security-policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp and "'unsafe-inline'" not in csp
    assert h["x-content-type-options"] == "nosniff"


def test_csp_hashes_cover_the_inline_script_and_style(client):
    import base64
    import hashlib

    html = client.get("/").text
    csp = client.get("/").headers["content-security-policy"]
    for tag in ("script", "style"):
        for body in re.findall(rf"<{tag}>(.*?)</{tag}>", html, flags=re.S):
            digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            assert f"'sha256-{digest}'" in csp


def test_existing_endpoints_unchanged(client):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/metrics").status_code == 200
    r = client.post("/predict", json={"url": "https://example.com"})
    assert r.status_code == 200 and r.json()["model_version"] == "vtest"
    assert client.post("/predict", json={"url": "http://[::1"}).status_code == 422
    assert "/" not in client.get("/openapi.json").json()["paths"]


def test_page_is_offline_and_never_uses_innerhtml():
    src = INDEX_PAGE.read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                   "localStorage", "sessionStorage", "console.log"):
        assert banned not in src, banned
    assert not re.search(r"<script[^>]+src=", src) and "<link" not in src
    assert not re.search(r"(src|href)=[\"']https?://", src)
    assert "@import" not in src and "cdn" not in src.lower()


def test_embedded_replay_data_matches_results_file():
    spec = importlib.util.spec_from_file_location("embed", Path("scripts/embed_replay_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    results = json.loads(Path("reports/results/replay_results.json").read_text("utf-8"))
    expected = mod.trimmed(results)
    src = INDEX_PAGE.read_text(encoding="utf-8")
    block = re.search(r'<script type="application/json" id="replay-data">(.*?)</script>', src,
                      flags=re.S)
    # parsed exactly as the page's JSON.parse(textContent) sees it
    assert json.loads(block.group(1)) == expected
    assert [a["promotions"] for a in expected["arms"]] == [0, 0, 0, 1]
