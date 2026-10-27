# syntax=docker/dockerfile:1
# Build: docker build -t adaptivephish:<git-sha> .   (models/ must be DVC-pulled first)
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements-serve.txt .
RUN pip install -r requirements-serve.txt
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .

FROM python:3.11-slim
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ADAPTIVEPHISH_PRODUCTION=/app/models/production.json
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Model baked in at build time from the DVC-pulled models/ folder (no host files at runtime).
COPY models/production.json models/production.json
COPY models/v1/model.joblib models/v1/model.joblib
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "adaptivephish.api.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
