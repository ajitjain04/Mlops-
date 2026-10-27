# PROGRESS

Items are ticked only with evidence (command run and key output). "unverified" = not yet checked.

## Milestones

| Milestone | Status |
|---|---|
| M1 Repo and environment | done (see evidence below) |
| M2 Dataset verification and subset | done except DVC tracking (M3); see evidence below |
| M3 DVC | done (see evidence below) |
| M4 Shared URL features | done; first consumers arrive in M5/M7 |
| M5 Experiments A and B + MLflow | done (V1 = random forest); V1 artifact not on DVC remote (see notes) |
| M6 Drift detection | done; rule LOCKED (K=17) 2026-10-27 |
| M7 FastAPI | done (local uvicorn; container is M8) |
| M8 Docker + local monitoring | not started |
| M9 GitHub Actions CI + image publishing | not started |
| M10 AWS EC2 deployment | not started |
| M11 Adaptive loop | not started |
| M12 Documentation | not started |

## Acceptance checklist (spec section 22)


### Research and ML
- [x] Dataset provenance, license/terms, schema, labels, dates, duplicates, and class balance documented. Evidence (M2): `reports/results/dataset_report.md`; `scripts/inspect_dataset.py` read all 77 shards (666,315 rows, revision eca603e0); `scripts/build_subset.py` gives 88,986 rows, identical subset_sha256 on two runs. Key finding: class and date are confounded (no benign Nov 2024-May 2025), so the window is 2025-06..10. Near-duplicate check: only exact/normalized URL.
- [ ] URL-only feature extraction shared between training and inference. Partial (M4): shared module + 19 passing tests + `featurize` stage; not yet used by a model or the API. Finding: query/fragment features are a dataset artifact (see `reports/results/feature_report.md`).
- [x] Random-split baseline evaluated. Evidence (M5): `dvc repro` train stage; 4 algorithms x 2 feature sets, best test F1 0.924-0.928 for tree models; `reports/results/experiments_report.md`.
- [x] Chronological temporal experiment evaluated. Evidence (M5): train Jun-Jul, val Aug, test Sep-Oct 2025; V1 chosen by val F1 only; test F1 0.838 (CI 0.834-0.841).
- [x] Temporal performance change reported honestly. Evidence (M5): same-algorithm test F1 drops from about 0.92 (random) to about 0.84 (temporal) for tree models; single seed, collection effects not separated from drift (see report).
- [x] Drift method, threshold, and decisions documented. Evidence (M6): `reports/results/drift_report.md`, `drift_calibration.json`; 7 synthetic-fixture tests pass (shifted alerts, unshifted does not); K=17 of 20 calibrated on reference time-block null (3.4% alert rate), 0/10 validation alerts; test period never loaded.
- [ ] Conditional retraining implemented.
- [ ] Candidate V2 evaluated against incumbent V1.
- [ ] Promotion/rejection criteria are explicit and tested.
- [ ] Static versus adaptive comparison reported with actual results.

### MLOps
- [x] GitHub repository and reproducible environment. Evidence (M1): `pip install -e .` OK, `pytest` 1 passed, `ruff check .` All checks passed, `git push -u origin main` created `origin/main` (commit db7396c). Python 3.11.4 in `.venv`. Clean-checkout reproduction: unverified.
- [x] DVC data/artifact tracking. Evidence (M3): DVC 3.67.1, `dvc repro` ran `fetch_meta` and `build_subset`; `dvc.lock` written; subset_sha256 identical to M2 (aa62bfce...); second `dvc repro` skipped both stages, `dvc status` clean.
- [x] DVC remote configured and retrieval tested, if storage access is available. Evidence (M3): remote `s3://adaptivephish-dvc-ajit-2026/dvc` (ap-south-1, profile in gitignored `.dvc/config.local`); `dvc push` 2 files pushed; deleted `data/interim`, `data/processed` and `.dvc/cache`, `dvc pull` fetched 2 files, sha256 of both identical to before, `dvc status` clean.
- [x] Reproducible DVC pipeline and parameters. Evidence (M3/M4): `params.yaml` (subset section) wired into `dvc.yaml`; changing `cap_per_month_label` made `dvc status` report `params.yaml: modified subset`; `dvc repro` with defaults gave subset_sha256 aa62bfce... again; stages fetch_meta, build_subset, featurize.
- [x] MLflow runs record parameters, metrics, and artifacts. Evidence (M5): local sqlite store, 22 random-split and 24 temporal runs with params, tags (git commit, subset hash, feature version), val metrics, train seconds; model artifacts and test metrics on the 8 selected runs per experiment; reloaded V1 via `runs:/<id>/model`. Store is local only (not shared).
- [ ] Data/code/feature/model/deployment versions are traceable.

### Production and delivery
- [x] FastAPI health and prediction endpoints work. Evidence (M7): `uvicorn adaptivephish.api.app:app_factory --factory` served V1; GET /health 200 (model v1, feature 1.0.0, 26 features); POST /predict nyc.gov URL -> legitimate (score 0.003), paypal-lookalike -> phishing (0.71), `http://[::1` -> 422; /metrics counters matched those calls; 16 API tests pass (44 total), ruff clean.
- [ ] Shared feature code and model schema match training. Partial (M7): API uses `extract_features` and `load_production`, which refuses a feature_version mismatch (tested); schema check against the trained model's own input signature not added.
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
- [ ] Drift is not incorrectly equated with accuracy loss. Partial (M6): documented in drift_report.md and module docstring; no performance link tested yet.
- [ ] Candidate retraining and promotion events are traceable.
- [ ] Rejected candidate leaves incumbent production model intact.
- [ ] End-to-end replay or production loop is demonstrated honestly.

### Documentation
- [ ] Setup and reproduction instructions work from a clean checkout.
- [ ] Architecture and pipeline diagrams match the implementation.
- [ ] Results, limitations, and costs are documented.
- [ ] No secrets or sensitive values are committed.
- [ ] All completion claims are supported by test/log/experiment evidence.

## Pre-registration for M11 (fixed 2026-10-27, before any test-period replay)

Locked drift rule (`params.yaml` `drift.locked`): K=17 of 20 tested features, PSI floor 0.1, Bonferroni at alpha 0.05, batch size 2,000. No threshold, K, acceptance criterion or arm may change after test-period replay results are seen; any later deviation must be reported as a deviation.

Arms to run and report together on the same test-period batches (`params.yaml` `replay.arms`):
1. **static_v1**: V1 never retrained.
2. **adaptive_primary**: retrain when the K=17 drift rule alerts; promote only if the candidate passes the fixed acceptance rules.
3. **adaptive_sensitivity**: same as primary with K=10.
4. **fixed_monthly**: retrain on a fixed monthly schedule regardless of drift; same acceptance rules.

All arms report the same metrics whatever the outcome, including the number of retrains, accepted and rejected candidates, and performance trajectories. Acceptance criteria for promotion are to be written before the replay starts and recorded here.

## Environment notes

- DVC remote push FAILED at the end of M5 (403 HeadObject); `aws sts get-caller-identity --profile adaptivephish` now returns InvalidClientTokenId, so the access key appears deleted or rotated. `models/v1` and the new `features.parquet` md5 are therefore NOT on S3. Needs a fresh `aws configure --profile adaptivephish` by the user.
- V1 reload gate: `load_production()` loaded models/v1/model.joblib and predicted 3 test URLs (probabilities 0.12, 0.93, 0.003).
- Docker: `docker run hello-world` OK. AWS CLI 2.38.6 present (re-checked 2026-10-27). DVC 3.67.1 installed. AWS profile `adaptivephish` verified by user (sts and s3 ls OK); I did not run those myself.
