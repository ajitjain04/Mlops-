# PROGRESS

Items are ticked only with evidence (command run and key output). "unverified" = not yet checked.

## Milestones

| Milestone | Status |
|---|---|
| M1 Repo and environment | done (see evidence below) |
| M2 Dataset verification and subset | done except DVC tracking (M3); see evidence below |
| M3 DVC | done (see evidence below) |
| M4 Shared URL features | done; first consumers arrive in M5/M7 |
| M5 Experiments A and B + MLflow | not started |
| M6 Drift detection | not started |
| M7 FastAPI | not started |
| M8 Docker + local monitoring | not started |
| M9 GitHub Actions CI + image publishing | not started |
| M10 AWS EC2 deployment | not started |
| M11 Adaptive loop | not started |
| M12 Documentation | not started |

## Acceptance checklist (spec section 22)


### Research and ML
- [x] Dataset provenance, license/terms, schema, labels, dates, duplicates, and class balance documented. Evidence (M2): `reports/results/dataset_report.md`; `scripts/inspect_dataset.py` read all 77 shards (666,315 rows, revision eca603e0); `scripts/build_subset.py` gives 88,986 rows, identical subset_sha256 on two runs. Key finding: class and date are confounded (no benign Nov 2024-May 2025), so the window is 2025-06..10. Near-duplicate check: only exact/normalized URL.
- [ ] URL-only feature extraction shared between training and inference. Partial (M4): shared module + 19 passing tests + `featurize` stage; not yet used by a model or the API. Finding: query/fragment features are a dataset artifact (see `reports/results/feature_report.md`).
- [ ] Random-split baseline evaluated.
- [ ] Chronological temporal experiment evaluated.
- [ ] Temporal performance change reported honestly.
- [ ] Drift method, threshold, and decisions documented.
- [ ] Conditional retraining implemented.
- [ ] Candidate V2 evaluated against incumbent V1.
- [ ] Promotion/rejection criteria are explicit and tested.
- [ ] Static versus adaptive comparison reported with actual results.

### MLOps
- [x] GitHub repository and reproducible environment. Evidence (M1): `pip install -e .` OK, `pytest` 1 passed, `ruff check .` All checks passed, `git push -u origin main` created `origin/main` (commit db7396c). Python 3.11.4 in `.venv`. Clean-checkout reproduction: unverified.
- [x] DVC data/artifact tracking. Evidence (M3): DVC 3.67.1, `dvc repro` ran `fetch_meta` and `build_subset`; `dvc.lock` written; subset_sha256 identical to M2 (aa62bfce...); second `dvc repro` skipped both stages, `dvc status` clean.
- [x] DVC remote configured and retrieval tested, if storage access is available. Evidence (M3): remote `s3://adaptivephish-dvc-ajit-2026/dvc` (ap-south-1, profile in gitignored `.dvc/config.local`); `dvc push` 2 files pushed; deleted `data/interim`, `data/processed` and `.dvc/cache`, `dvc pull` fetched 2 files, sha256 of both identical to before, `dvc status` clean.
- [x] Reproducible DVC pipeline and parameters. Evidence (M3/M4): `params.yaml` (subset section) wired into `dvc.yaml`; changing `cap_per_month_label` made `dvc status` report `params.yaml: modified subset`; `dvc repro` with defaults gave subset_sha256 aa62bfce... again; stages fetch_meta, build_subset, featurize.
- [ ] MLflow runs record parameters, metrics, and artifacts.
- [ ] Data/code/feature/model/deployment versions are traceable.

### Production and delivery
- [ ] FastAPI health and prediction endpoints work.
- [ ] Shared feature code and model schema match training.
- [ ] Docker image builds and runs.
- [ ] GitHub Actions CI tests pass.
- [ ] Image is published to the selected registry.
- [ ] Approved deployment workflow runs.
- [ ] AWS EC2 service passes health and smoke tests, if cloud access/budget permit.
- [ ] Deployment version and rollback path are documented.

### Monitoring and adaptation
- [ ] Prometheus scrapes actual service metrics.
- [ ] Grafana dashboard visualizes those metrics.
- [ ] Drift monitoring uses URL-derived features and a reference window.
- [ ] Drift is not incorrectly equated with accuracy loss.
- [ ] Candidate retraining and promotion events are traceable.
- [ ] Rejected candidate leaves incumbent production model intact.
- [ ] End-to-end replay or production loop is demonstrated honestly.

### Documentation
- [ ] Setup and reproduction instructions work from a clean checkout.
- [ ] Architecture and pipeline diagrams match the implementation.
- [ ] Results, limitations, and costs are documented.
- [ ] No secrets or sensitive values are committed.
- [ ] All completion claims are supported by test/log/experiment evidence.

## Environment notes

- Docker: `docker run hello-world` OK. AWS CLI 2.38.6 present (re-checked 2026-10-27). DVC 3.67.1 installed. AWS profile `adaptivephish` verified by user (sts and s3 ls OK); I did not run those myself.
