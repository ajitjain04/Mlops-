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
| M8 Docker + local monitoring | done locally (see evidence) |
| M9 GitHub Actions CI + image publishing | done (deploy workflow is M10) |
| M10 AWS EC2 deployment | done (see evidence); docs in docs/deployment.md |
| M11 Adaptive loop | done: replay reported honestly (see evidence); dashboard/metrics verified locally |
| M12 Documentation | done (README, evidence, clean-checkout check); see Final status below |

## Acceptance checklist (spec section 22)


### Research and ML
- [x] Dataset provenance, license/terms, schema, labels, dates, duplicates, and class balance documented. Evidence (M2): `reports/results/dataset_report.md`; `scripts/inspect_dataset.py` read all 77 shards (666,315 rows, revision eca603e0); `scripts/build_subset.py` gives 88,986 rows, identical subset_sha256 on two runs. Key finding: class and date are confounded (no benign Nov 2024-May 2025), so the window is 2025-06..10. Near-duplicate check: only exact/normalized URL.
- [x] URL-only feature extraction shared between training and inference. Evidence (M4/M7/M12): one module `src/adaptivephish/features/url_features.py` is used by `featurize` (training) and by the API; `tests/test_feature_parity.py` recomputes features for 500 random subset URLs through the serving extractor and they equal the stored training features (`assert_allclose`); 19 feature tests. Limitation: URL-only by design, so no page content.
- [x] Random-split baseline evaluated. Evidence (M5): `dvc repro` train stage; 4 algorithms x 2 feature sets, best test F1 0.924-0.928 for tree models; `reports/results/experiments_report.md`.
- [x] Chronological temporal experiment evaluated. Evidence (M5): train Jun-Jul, val Aug, test Sep-Oct 2025; V1 chosen by val F1 only; test F1 0.838 (CI 0.834-0.841).
- [x] Temporal performance change reported honestly. Evidence (M5): same-algorithm test F1 drops from about 0.92 (random) to about 0.84 (temporal) for tree models; single seed, collection effects not separated from drift (see report).
- [x] Drift method, threshold, and decisions documented. Evidence (M6): `reports/results/drift_report.md`, `drift_calibration.json`; 7 synthetic-fixture tests pass (shifted alerts, unshifted does not); K=17 of 20 calibrated on reference time-block null (3.4% alert rate), 0/10 validation alerts; test period never loaded.
- [x] Conditional retraining implemented. Evidence (M11): `src/adaptivephish/replay.py` (drift/schedule trigger, cooldown, label delay, candidate training on older labelled data); 10 synthetic-stream tests; official replay `reports/results/replay_results.json` (adaptive_sensitivity made 3 attempts, fixed_monthly 1). Retraining is exercised in the replay, not wired to the deployed service.
- [x] Candidate V2 evaluated against incumbent V1. Evidence (M11): every attempt logs incumbent vs candidate F1/precision/recall/FPR on the gate set plus the paired-bootstrap interval; e.g. fixed_monthly batch 9: gate F1 0.755 vs 0.701, interval [0.041, 0.069], promoted.
- [x] Promotion/rejection criteria are explicit and tested. Evidence (M11): locked in `params.yaml` and above (lock hash 3127dc13...), `tests/test_replay.py` covers each check blocking promotion, cooldown, label-delay indices, no-gain rejection leaving V1 untouched; `tests/test_replay_lock.py` covers the refusal.
- [x] Static versus adaptive comparison reported with actual results. Evidence (M11): `reports/results/replay_report.md`: pooled test F1 static 0.8377, adaptive K=17 0.8377 (never alerted), K=10 0.8377 (3 attempts, 0 promotions), fixed monthly 0.8400 (1 promotion). Adaptive arms did not beat static by a meaningful margin; reported as is. Single seed, 19 batches.

### MLOps
- [x] GitHub repository and reproducible environment. Evidence (M1): `pip install -e .` OK, `pytest` 1 passed, `ruff check .` All checks passed, `git push -u origin main` created `origin/main` (commit db7396c). Python 3.11.4 in `.venv`. Clean-checkout reproduction: unverified.
- [x] DVC data/artifact tracking. Evidence (M3): DVC 3.67.1, `dvc repro` ran `fetch_meta` and `build_subset`; `dvc.lock` written; subset_sha256 identical to M2 (aa62bfce...); second `dvc repro` skipped both stages, `dvc status` clean.
- [x] DVC remote configured and retrieval tested, if storage access is available. Evidence (M3): remote `s3://adaptivephish-dvc-ajit-2026/dvc` (ap-south-1, profile in gitignored `.dvc/config.local`); `dvc push` 2 files pushed; deleted `data/interim`, `data/processed` and `.dvc/cache`, `dvc pull` fetched 2 files, sha256 of both identical to before, `dvc status` clean.
- [x] Reproducible DVC pipeline and parameters. Evidence (M3/M4): `params.yaml` (subset section) wired into `dvc.yaml`; changing `cap_per_month_label` made `dvc status` report `params.yaml: modified subset`; `dvc repro` with defaults gave subset_sha256 aa62bfce... again; stages fetch_meta, build_subset, featurize.
- [x] MLflow runs record parameters, metrics, and artifacts. Evidence (M5): local sqlite store, 22 random-split and 24 temporal runs with params, tags (git commit, subset hash, feature version), val metrics, train seconds; model artifacts and test metrics on the 8 selected runs per experiment; reloaded V1 via `runs:/<id>/model`. Store is local only (not shared).
- [x] Data/code/feature/model/deployment versions are traceable. Evidence (M12): `models/production.json` records dataset revision, subset sha256, features md5, feature_version, git commit and MLflow run id; `dvc.lock` pins data/code/params hashes; image tag = git short SHA; `/health` reports model_version and feature_version; EC2 keeps `current_tag`/`previous_tag`/`deployments.log`. Limitations: the MLflow store is local only, and `/health` does not report the image tag.

### Production and delivery
- [x] FastAPI health and prediction endpoints work. Evidence (M7): `uvicorn adaptivephish.api.app:app_factory --factory` served V1; GET /health 200 (model v1, feature 1.0.0, 26 features); POST /predict nyc.gov URL -> legitimate (score 0.003), paypal-lookalike -> phishing (0.71), `http://[::1` -> 422; /metrics counters matched those calls; 16 API tests pass (44 total), ruff clean.
- [x] Shared feature code and model schema match training. Evidence (M7/M12): `load_production` refuses a feature_version mismatch (tested); `tests/test_feature_parity.py::test_model_feature_list_matches_code_and_estimator` checks the stored feature list equals `PRODUCTION_FEATURE_NAMES` and the estimator's `n_features_in_`; serving/training feature parity test above. Limitation: no per-column dtype/range signature check.
- [x] Docker image builds and runs. Evidence (M8): `docker compose up -d --build`; image adaptivephish:82da5dc, 1.11 GB on disk (python:3.11-slim, non-root uid 10001, V1 joblib 122 MB baked in, no extra files; `docker history` has no credential strings); container healthcheck `healthy`; /health 200 and /predict 200/422 from the container on 127.0.0.1:8000. Clean-checkout build (needs `dvc pull` for models/v1): unverified.
- [x] GitHub Actions CI tests pass. Evidence (M9): run 40533354578 on a226708, ruff + 44 pytest (real-V1 test skipped without the model) green on ubuntu/py3.11, no AWS credentials used; image workflow also reran CI via workflow_call.
- [x] Image is published to the selected registry. Evidence (M9): build-and-push run 40533354628 green (dvc pull with the read-only AWS user, build, container smoke test, push); Docker Hub public API shows 0008a/adaptivephish:a226708 (public repo, linux/amd64, digest sha256:0dce761a...); `docker pull` OK; pulled container: /health model v1 healthy, /predict phishing for a lookalike URL, runs as non-root.
- [x] Approved deployment workflow runs. Evidence (M10, user-reported): Deploy to EC2 with tag a226708 passed the production-environment approval, OIDC role assumption, SSM Success and the on-instance smoke test (DEPLOY OK). Earlier failed runs (OIDC sub format, wrong role ARN variable) are in docs/deployment.md. I did not see the run log myself.
- [x] AWS EC2 service passes health and smoke tests, if cloud access/budget permit. Evidence (M10, checked by me 2026-10-27 from this machine): GET http://15.206.211.173:8000/health returned model_loaded true, model_version v1, feature_version 1.0.0, n_features 26; POST /predict: paypal-lookalike URL gave phishing (score 0.937), nyc.gov URL gave legitimate (0.003), threshold 0.1833. Plain HTTP, reachable only from the operator IP.
- [x] Deployment version and rollback path are documented. Evidence (M10): docs/deployment.md (current_tag/previous_tag/deployments.log, image_tag=previous rollback, automatic rollback on a failed smoke test, cleanup). Rollback exercised 2026-10-28: deploy 3dc1367 then `image_tag=previous`, both green with DEPLOY OK lines (a226708 restored; user-reported logs). I then checked /health (200, v1, model_loaded true) and /predict (phishing 0.937 / legitimate 0.003) at the public IP. The image tag itself is not visible from outside, and both tags hold the same V1 model, so this proves the mechanics only.

### Monitoring and adaptation
- [x] Prometheus scrapes actual service metrics. Evidence (M8): target `adaptivephish-api` http://api:8000/metrics health=up (5s interval).
- [x] Grafana dashboard visualizes those metrics. Evidence (M8): dashboard provisioned from files (uid adaptivephish-api); after ~60 requests, all 8 panel queries run through Grafana's own datasource API returned data (e.g. /predict about 1 req/s, p50 75 ms, p95 99 ms, 422s counted as unparseable_url). Checked via API, not by eyeballing screenshots. Drift/retraining panels not built yet.
- [x] Drift monitoring uses URL-derived features and a reference window. Evidence (M6/M11): drift on 20 URL features against the train-window reference, per batch in the replay (`drift_per_batch` in replay_results.json) and exported to /metrics and Grafana.
- [x] Drift is not incorrectly equated with accuracy loss. Evidence (M11): across the 19 test batches the drifted-feature count correlates 0.17 with static-V1 F1, while F1 correlates 0.91 with the batch's phishing share; the worst F1 batches had 7-8 drifted features (replay_report.md).
- [x] Candidate retraining and promotion events are traceable. Evidence (M11): replay_results.json lists every attempt (batch, versions, gate/threshold/train batches, checks, failed reasons, train seconds) and replay_batches.csv records the model version per batch; counters exported as adaptivephish_retrain_attempts_total, _promotions_total, _rejections_total{reason} (tested and read through Grafana's datasource API).
- [x] Rejected candidate leaves incumbent production model intact. Evidence (M11): adaptive_sensitivity rejected 3 candidates and ends on v1 with all 37,501 rows scored by v1 (replay_results.json); unit test `test_no_improvement_means_rejection_and_incumbent_untouched`.
- [x] End-to-end replay or production loop is demonstrated honestly. Evidence (M11): one official replay under the locked design (replay_report.md). It is a replay of recorded data, not a live production loop; the deployed EC2 service is not retrained or hot-swapped.

### Documentation
- [x] Setup and reproduction instructions work from a clean checkout. Evidence (M12, 2026-10-28, fresh `git clone` of 46dcc48 into a sibling folder): new venv, `pip install -r requirements-dev.txt` and `-e .`; ruff clean; 62 passed, 1 skipped before `dvc pull`; `dvc remote modify --local storage profile adaptivephish` + `dvc pull` fetched 6 files; 63 passed after; replay lock verified; the official replay re-run in the clone gave results identical to the committed ones (ignoring timings); `docker build` from the clone then `/health` (model v1) and `/predict` (phishing 0.937) worked. Defect found and fixed: `dvc status` in the clone listed 4 stages as changed because 4 scripts had CRLF line endings when `dvc.lock` hashed them (Git stores LF); converted them to LF and ran `dvc commit -f` (only dependency hashes changed). Not done: a from-scratch `dvc repro` of the whole pipeline from Hugging Face (unverified), and a read-only IAM user for others (policy documented in README, not created).
- [x] Architecture and pipeline diagrams match the implementation. Evidence (M12): README keeps the teammates' high-level diagram and adds an 'As implemented' Mermaid diagram (DVC stages, three workflows, EC2, local compose monitoring, replay-only loop) checked against `dvc.yaml`, `.github/workflows/` and `docker-compose.yml`. The original diagram implies a live retrain/promote loop; the README states that loop is replay-only.
- [x] Results, limitations, and costs are documented. Evidence (M12): README sections 'Results and hypotheses' (H1 supported with caveats, H2 weak, H3 not supported), 'Limitations', 'Costs and AWS cleanup checklist'; `reports/results/*_report.md`; `docs/deployment.md`. Costs are rough published rates, not billing data (none available to me).
- [x] No secrets or sensitive values are committed. Evidence (M12): `git grep` of tracked files and `git log -G` over history for AWS access-key IDs, `dckr_pat_`, `ghp_`/`github_pat_`, private-key headers and Slack tokens found nothing; no `.env`, `config.local` or credentials files are tracked; workflows reference secrets by name only; Grafana password only in the gitignored `.env`. Not secret but identifying: AWS account ID, instance ID and public IP appear in docs/deployment.md. The DVC bucket name is in `.dvc/config`. This is a pattern scan, not a guarantee.
- [x] All completion claims are supported by test/log/experiment evidence. Every tick above cites a command, file or test. Claims that rest on the project owner's report rather than my own observation: the Deploy to EC2 run logs (DEPLOY OK for a226708, 3dc1367, rollback), the AWS/GitHub console setup, and the secret/variable values. I verified the running service myself over HTTP. No screenshots exist; the README lists them as 'to be added'.

## Pre-registration for M11 (fixed 2026-10-27, before any test-period replay)

Locked drift rule (`params.yaml` `drift.locked`): K=17 of 20 tested features, PSI floor 0.1, Bonferroni at alpha 0.05, batch size 2,000. No threshold, K, acceptance criterion or arm may change after test-period replay results are seen; any later deviation must be reported as a deviation.

Arms to run and report together on the same test-period batches (`params.yaml` `replay.arms`):
1. **static_v1**: V1 never retrained.
2. **adaptive_primary**: retrain when the K=17 drift rule alerts; promote only if the candidate passes the fixed acceptance rules.
3. **adaptive_sensitivity**: same as primary with K=10.
4. **fixed_monthly**: retrain on a fixed monthly schedule regardless of drift; same acceptance rules.

All arms report the same metrics whatever the outcome, including the number of retrains, accepted and rejected candidates, and performance trajectories.

### Replay design and promotion criteria (approved by the user and locked 2026-10-27, before any replay code)

Machine-readable copy: `params.yaml` `replay` section; its hash plus `drift.locked` is in `reports/results/replay_lock.json`. `src/adaptivephish/replay_lock.py` `verify()` makes the replay refuse to run if the locked values changed, if the lock file has uncommitted edits, or if results exist from a different lock (7 tests).

- Replay: test window (Sep-Oct 2025) in 2,000-row batches in time order; every batch is scored by the model in production at that moment (prequential), never re-scored later.
- Label delay D=1: labels of batch j become usable after batch j+1 is scored. At a decision after batch i: labelled batches are <= i-1; gate set = batches i-2 and i-1; threshold batch = i-3; training = train + validation windows + replayed batches <= i-4.
- Candidate: random forest with V1's exact hyperparameters, no search; threshold = max F1 on the threshold batch.
- Cooldown: at most one retrain attempt per 3 batches. Triggers: primary K=17, sensitivity K=10, fixed arm at the first batch of each calendar month. Same acceptance rules for all adaptive arms.
- Promote only if ALL hold on the gate set (each model at its own threshold): (1) candidate F1 >= incumbent F1 + 0.01; (2) paired bootstrap of the F1 difference (1,000 resamples, seed 42) has a 95% interval lower bound > 0; (3) candidate FPR <= incumbent FPR + 0.02 and <= 0.25 absolute; (4) candidate recall >= incumbent recall - 0.02; (5) feature_version matches serving code and the candidate loads and scores a fixed canary URL set.
- Otherwise reject: the incumbent stays untouched, the reason is logged, no retry with other settings.
- All arms report the same things whatever happens: per-batch F1/recall/FPR and cumulative values, counts of alerts, attempts, promotions and rejections, labels consumed, retraining compute time. Results are reported even if adaptive arms never promote or never beat static.
- Stated limits: the gate set is made of the replay's own past batches (decisions use only past data, but it is one replay of one dataset with one seed); the dataset's class/date confounding remains; a drift alert means "investigate", not accuracy loss.
- Not in scope: Prometheus/Grafana on EC2 (documented as a limitation); local compose stack gets the new drift/retraining panels.

## Environment notes

- Docker Desktop disk image lives on D:\DockerData (C: was full). Keep C: above 2 GB free.
- Local monitoring: copy `.env.example` to `.env` (gitignored), set GRAFANA_ADMIN_PASSWORD; Grafana http://127.0.0.1:3000, Prometheus http://127.0.0.1:9090, API http://127.0.0.1:8000.

- Resolved: the M5 DVC push failed (403) because the AWS key had been rotated; the owner created a new key, `dvc push` then succeeded and `dvc status -c` is in sync (M6).
- V1 reload gate: `load_production()` loaded models/v1/model.joblib and predicted 3 test URLs (probabilities 0.12, 0.93, 0.003).
- Docker: `docker run hello-world` OK. AWS CLI 2.38.6 present (re-checked 2026-10-27). DVC 3.67.1 installed. AWS profile `adaptivephish` verified by user (sts and s3 ls OK); I did not run those myself.

- M11 monitoring: `/metrics` exports per-arm drift status, drifted-feature count, max PSI, attempts, promotions, rejections by failed check and suppressed triggers when `ADAPTIVEPHISH_LIFECYCLE` points at the replay's state file (compose mounts `artifacts/lifecycle`); 9 new Grafana panels return data via the datasource API. Not on EC2 (documented limitation: no Prometheus/Grafana there).

## Final status (M12)

All checklist items are ticked. Items ticked with a stated limitation (documented in README 'Limitations'):
H3 not supported and H2 weak (reported results, not failures of the work); MLflow store local only; no
Prometheus/Grafana on EC2; plain HTTP on EC2; one seed and one replay; high FPR (~0.21); K=17 conservative;
from-scratch `dvc repro` and a created read-only IAM user not verified; README Team table placeholders belong to
teammates; screenshots to be added; cleanup of AWS resources is the owner's to-do (checklist in README).
