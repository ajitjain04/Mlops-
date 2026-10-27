# AdaptivePhish

Drift-aware MLOps lifecycle for phishing URL detection: versioned data (DVC), tracked
experiments (MLflow), a FastAPI service, Docker, GitHub Actions CI/CD, AWS EC2 deployment,
Prometheus/Grafana monitoring, and drift-triggered retraining with gated model promotion.

Status: work in progress. See [PROGRESS.md](PROGRESS.md) for the evidence-backed checklist.
Full specification: [AdaptivePhish_Master_Project_Prompt.md](AdaptivePhish_Master_Project_Prompt.md).

## Setup (Windows, cmd)

```bat
cd /d E:\Projects\Mlops-
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m pytest
python -m ruff check .
```

Python 3.11 is required.

## Team

| Member | GitHub | Role |
|---|---|---|
| Ajit Jain | [@ajitjain04](https://github.com/ajitjain04) | Pipeline, DVC, CI/CD, AWS deployment |
| <His Full Name> | [@MrLoSt1805](https://github.com/MrLoSt1805) | Documentation, architecture diagram and evidence |
| <Third Member Name> | [@DheerAjmera](https://github.com/DheerAjmera) | Tests, viva preparation and demo support |