import json
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from adaptivephish.api.app import create_app
from adaptivephish.features.url_features import FEATURE_VERSION, PRODUCTION_FEATURE_NAMES
from adaptivephish.model_io import LoadedModel, load_production


class FixedModel:
    """score = min(url_len / 100, 1); deterministic stand-in with the sklearn API."""

    def predict_proba(self, x):
        p = np.clip(x["url_len"].to_numpy() / 100.0, 0, 1)
        return np.column_stack([1 - p, p])


def make_loaded(threshold=0.5):
    meta = {"model_version": "vtest", "algorithm": "fixed", "feature_version": FEATURE_VERSION}
    return LoadedModel(FixedModel(), list(PRODUCTION_FEATURE_NAMES), threshold, meta)


@pytest.fixture
def client():
    with TestClient(create_app(loaded=make_loaded())) as c:
        yield c


def metric(client, name, **labels):
    text = client.get("/metrics").text
    want = ",".join(f'{k}="{v}"' for k, v in labels.items())
    for line in text.splitlines():
        if line.startswith(name + "{") and want in line:
            return float(line.rsplit(" ", 1)[1])
        if not want and line.startswith(name + " "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["model_version"] == "vtest"
    assert body["feature_version"] == FEATURE_VERSION


def test_predict_schema_and_label_mapping(client):
    short = client.post("/predict", json={"url": "http://a.io"}).json()
    long_ = client.post("/predict", json={"url": "http://x.example/" + "a" * 120}).json()
    assert short["prediction"] == "legitimate" and long_["prediction"] == "phishing"
    assert set(short) == {"url", "prediction", "score", "threshold", "model_version",
                          "feature_version"}
    assert 0 <= short["score"] < short["threshold"] <= long_["score"] <= 1
    assert short["model_version"] == "vtest"


@pytest.mark.parametrize("body", [{}, {"url": ""}, {"url": 5}, {"url": "x" * 5000}, {"u": "a"}])
def test_invalid_payload_rejected(client, body):
    assert client.post("/predict", json=body).status_code == 422


@pytest.mark.parametrize("url", ["   ", "http://[::1", "http://host:notaport/"])
def test_unparseable_url_rejected_not_crashing(client, url):
    r = client.post("/predict", json={"url": url})
    assert r.status_code == 422
    assert client.get("/health").status_code == 200


def test_metrics_change_after_requests(client):
    before = metric(client, "adaptivephish_predictions_total", prediction="legitimate")
    client.post("/predict", json={"url": "http://a.io"})
    client.post("/predict", json={"url": "http://a.io"})
    assert metric(client, "adaptivephish_predictions_total", prediction="legitimate") == before + 2
    assert metric(client, "adaptivephish_http_requests_total", endpoint="/predict",
                  status="200") == 2
    assert metric(client, "adaptivephish_http_request_duration_seconds_count",
                  endpoint="/predict") == 2
    client.post("/predict", json={"url": "http://[::1"})
    assert metric(client, "adaptivephish_errors_total", type="unparseable_url") == 1
    assert metric(client, "adaptivephish_model_loaded") == 1
    assert metric(client, "adaptivephish_model_info", model_version="vtest") == 1


def test_urls_never_appear_in_metrics(client):
    client.post("/predict", json={"url": "https://secret.example/?token=abc123"})
    text = client.get("/metrics").text
    assert "secret.example" not in text and "abc123" not in text


def test_unknown_route_has_bounded_label(client):
    assert client.get("/nope/123").status_code == 404
    assert metric(client, "adaptivephish_http_requests_total", endpoint="unmatched",
                  status="404") == 1


def test_missing_model_reports_unavailable(tmp_path):
    with TestClient(create_app(production_path=str(tmp_path / "missing.json"))) as c:
        assert c.get("/health").status_code == 503
        assert c.post("/predict", json={"url": "http://a.io"}).status_code == 503
        assert metric(c, "adaptivephish_model_loaded") == 0


def test_feature_version_mismatch_refuses_to_load(tmp_path):
    joblib.dump(FixedModel(), tmp_path / "m.joblib")
    meta = {"model_path": str(tmp_path / "m.joblib"), "feature_version": "0.0.0-old",
            "feature_names": list(PRODUCTION_FEATURE_NAMES), "threshold": 0.5}
    (tmp_path / "production.json").write_text(json.dumps(meta))
    with pytest.raises(RuntimeError):
        load_production(tmp_path / "production.json")


REAL = Path("models/production.json")


@pytest.mark.skipif(not (REAL.exists() and Path("models/v1/model.joblib").exists()),
                    reason="trained V1 not present (DVC pull required)")
def test_real_v1_serves_and_versions_match():
    meta = json.loads(REAL.read_text())
    with TestClient(create_app()) as c:
        h = c.get("/health").json()
        assert h["model_version"] == meta["model_version"]
        assert h["feature_version"] == meta["feature_version"]
        r = c.post("/predict", json={"url": "https://www.nyc.gov/site/dcas/employment/jobs.page"})
        assert r.status_code == 200 and r.json()["model_version"] == "v1"
