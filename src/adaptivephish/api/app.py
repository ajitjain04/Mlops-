"""FastAPI prediction service.

Loads the production model once at startup (lifespan), reuses the training-time feature
extractor, and exposes Prometheus metrics. Raw URLs are never logged or used as metric labels.

Response contract: `score` is the model's phishing probability (positive class), NOT a
calibrated confidence (calibration was not evaluated). `prediction` is "phishing" when
score >= the validation-selected threshold stored in models/production.json, else "legitimate".
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, Field

from adaptivephish.features.url_features import extract_features
from adaptivephish.lifecycle import LIFECYCLE_ENV, LifecycleCollector
from adaptivephish.model_io import PRODUCTION_FILE, LoadedModel, load_production

log = logging.getLogger("adaptivephish.api")

MAX_URL_LENGTH = 4096
LABELS = {1: "phishing", 0: "legitimate"}


class PredictRequest(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)


class PredictResponse(BaseModel):
    url: str
    prediction: Literal["phishing", "legitimate"]
    score: float = Field(description="Model phishing probability; not calibrated")
    threshold: float
    model_version: str
    feature_version: str


class Metrics:
    """Per-app registry so tests and multiple apps do not share global state."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "adaptivephish_http_requests_total", "HTTP requests",
            ["endpoint", "status"], registry=self.registry)
        self.latency = Histogram(
            "adaptivephish_http_request_duration_seconds", "HTTP request latency",
            ["endpoint"], registry=self.registry,
            buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
        self.predictions = Counter(
            "adaptivephish_predictions_total", "Predictions by outcome",
            ["prediction"], registry=self.registry)
        self.errors = Counter(
            "adaptivephish_errors_total", "Errors by type", ["type"], registry=self.registry)
        self.model_info = Gauge(
            "adaptivephish_model_info", "Serving model (value is always 1)",
            ["model_version", "feature_version"], registry=self.registry)
        self.model_loaded = Gauge(
            "adaptivephish_model_loaded", "1 if a model is loaded", registry=self.registry)
        # Drift status and retraining/promotion counters written by the replay (see lifecycle.py).
        # Exported only if ADAPTIVEPHISH_LIFECYCLE points at a state file.
        self.registry.register(LifecycleCollector(os.environ.get(LIFECYCLE_ENV)))


def create_app(loaded: LoadedModel | None = None, production_path: str | None = None) -> FastAPI:
    """`loaded` lets tests inject a model; otherwise it is read from production.json."""
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        model = loaded
        if model is None:
            path = production_path or os.environ.get("ADAPTIVEPHISH_PRODUCTION", PRODUCTION_FILE)
            try:
                model = load_production(path)
            except Exception:
                log.exception("failed to load production model from %s", path)
                metrics.errors.labels("model_load").inc()
        app.state.model = model
        metrics.model_loaded.set(1 if model else 0)
        if model:
            meta = model.metadata
            metrics.model_info.labels(
                meta.get("model_version", "unknown"), meta["feature_version"]).set(1)
            log.info("loaded model %s (%s), feature_version=%s threshold=%.4f",
                     meta.get("model_version"), meta.get("algorithm"),
                     meta["feature_version"], model.threshold)
        yield

    app = FastAPI(title="AdaptivePhish", version="0.1.0", lifespan=lifespan)
    app.state.metrics = metrics
    app.state.model = None

    @app.middleware("http")
    async def instrument(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            metrics.errors.labels("unhandled").inc()
            raise
        finally:
            route = request.scope.get("route")  # set by routing during call_next
            endpoint = route.path if route else "unmatched"
            metrics.requests.labels(endpoint, str(status)).inc()
            metrics.latency.labels(endpoint).observe(time.perf_counter() - start)

    @app.get("/health")
    def health(response: Response):
        model: LoadedModel | None = app.state.model
        if model is None:
            response.status_code = 503
            return {"status": "unavailable", "model_loaded": False}
        meta = model.metadata
        return {
            "status": "ok",
            "model_loaded": True,
            "model_version": meta.get("model_version", "unknown"),
            "algorithm": meta.get("algorithm"),
            "feature_version": meta["feature_version"],
            "n_features": len(model.feature_names),
        }

    @app.post("/predict", response_model=PredictResponse)
    def predict(req: PredictRequest):
        model: LoadedModel | None = app.state.model
        if model is None:
            metrics.errors.labels("model_unavailable").inc()
            raise HTTPException(status_code=503, detail="model not loaded")
        url = req.url.strip()
        if not url or extract_features(url)["parse_ok"] != 1.0:
            metrics.errors.labels("unparseable_url").inc()
            raise HTTPException(status_code=422, detail="URL could not be parsed")
        score = float(model.predict_proba([url])[0])
        label = LABELS[int(score >= model.threshold)]
        metrics.predictions.labels(label).inc()
        meta = model.metadata
        return PredictResponse(
            url=req.url, prediction=label, score=score, threshold=model.threshold,
            model_version=meta.get("model_version", "unknown"),
            feature_version=meta["feature_version"],
        )

    @app.get("/metrics")
    def metrics_endpoint():
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn adaptivephish.api.app:app_factory --factory`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
