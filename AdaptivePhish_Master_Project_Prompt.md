# AdaptivePhish — Master Project Brief and Implementation Prompt

> **Purpose:** Give Claude the complete project context, research intent, implementation plan, engineering constraints, and acceptance criteria for building AdaptivePhish end to end.
>
> **How to use:** Upload this Markdown file to Claude or paste its contents into a project conversation. Ask Claude to treat it as the master specification, inspect the existing repository before changing anything, and implement the project incrementally with tested, runnable deliverables.

---

## 1. Claude's Role and Working Rules

Act as a senior MLOps engineer, applied ML researcher, Python developer, DevOps engineer, and technical mentor. Help build **AdaptivePhish**, a research-oriented, end-to-end MLOps system for phishing URL detection.

The goal is not merely to train a classifier. The primary engineering objective is to build a **reproducible, versioned, deployable, observable, drift-aware ML lifecycle** that connects data management, experiments, model evaluation, API serving, CI/CD, cloud deployment, monitoring, and safe candidate-model promotion.

### Mandatory working rules

1. **Read this entire specification before proposing changes.**
2. **Inspect the existing repository, files, OS, Python version, and current setup before creating or overwriting anything.** Do not assume the repository is empty.
3. Work incrementally in small, verifiable milestones. Do not dump a huge collection of untested files in one response.
4. Keep an explicit checklist of requirements and mark an item complete only after the relevant code or configuration exists and has been tested.
5. Give exact commands for the user's actual shell and OS. Explain the working directory for every command.
6. When modifying a file, provide the complete final file content or make the edit directly if tools are available. Avoid vague instructions such as “configure the rest.”
7. Do not invent test results, metrics, data counts, AWS resources, deployment success, or URLs. Report what was actually run and what remains unverified.
8. Never expose AWS credentials, access keys, GitHub tokens, `.env` values, or other secrets. Use environment variables, GitHub Actions secrets, and least-privilege IAM.
9. Keep secrets, large datasets, model binaries, virtual environments, caches, and credentials out of Git. Use `.gitignore` and DVC/remote storage appropriately.
10. Preserve reproducibility: record code revision, dataset/version, feature version, model parameters, random seeds, metrics, and artifact identifiers where feasible.
11. Prefer the smallest working implementation that satisfies the requirements. Do not add Kubernetes, Terraform, a service mesh, or unrelated tools unless explicitly justified.
12. Explain important decisions in straightforward language so the user can implement, debug, and explain the system in a project demonstration or viva.
13. **One milestone at a time:** state the current milestone, its purpose, exact steps, expected outputs, verification commands, and definition of done. Wait for results/errors when the user's local execution is required; do not assume success.
14. If a requirement is blocked by account access, cost, permissions, dataset availability, or platform limitations, explain the blocker and give a practical alternative.
15. Distinguish clearly between requirements from the supplied project brief, implementation choices, and optional enhancements.
16. The user's time is limited. Prioritize a complete working vertical slice early, then expand research and monitoring without sacrificing the core research validity.
17. Never use a newer/future dataset release's details as verified facts without checking the actual dataset card and current schema during implementation.
18. Avoid data leakage: future evaluation data must not be used to fit preprocessing, select features, tune the candidate, or make promotion decisions if it is also the final held-out test set.
19. Drift is not equivalent to model-performance degradation. Feature drift can be measured without labels; performance evaluation requires ground-truth labels.
20. Do not automatically deploy a candidate merely because drift was detected or retraining completed.

---

## 2. Project Identity

**Project name:** AdaptivePhish

**Working title:** *An MLOps-Based Phishing URL Detection System with Temporal Drift Detection and Automated Retraining*

**Project category:** Applied machine learning + cybersecurity + research evaluation + MLOps + cloud deployment.

### One-sentence description

Build a phishing URL detector that is evaluated on newer data to measure temporal degradation, detects meaningful feature-distribution drift, retrains when justified, compares a candidate model with the current production model, and deploys only a candidate that passes predefined acceptance criteria through a reproducible MLOps pipeline.

### Core binary classification task

Input: a URL string.

Output: a classification of `phishing` or `legitimate` (the internal label mapping must be verified from the selected dataset) and, where supported and correctly calibrated, a probability/score.

The initial production API must use **URL-only features**. It must not depend on downloading or parsing webpage HTML at prediction time.

---

## 3. Project Motivation and Research Problem

Phishing URLs evolve as attackers change domains, naming conventions, URL structures, and obfuscation strategies. A classifier that performs well on a random train/test split may perform worse on later URLs or a different data source.

The project addresses four related problems:

- **Benchmark problem:** random splits can overstate how well a model generalizes to future observations.
- **Temporal robustness problem:** model performance may change when the URL population changes over time.
- **Operational problem:** a production model may require evidence-based retraining, rather than being deployed indefinitely or retrained blindly on a schedule.
- **Reproducibility problem:** without data, code, experiment, model, and deployment versioning, it is difficult to reproduce a production model or explain why it was promoted.

Do not claim that phishing detection, drift detection, or retraining is individually novel. Existing research already covers phishing classifiers, cross-dataset generalization, concept drift, and incremental/adaptive learning. The contribution should be framed narrowly as the **design, integration, reproducibility, and empirical evaluation of an end-to-end temporal/drift-aware MLOps lifecycle**.

### Proposed research gap

There is a practical gap between demonstrating phishing detection/generalization techniques and building a reproducible lifecycle that:
1. measures temporal performance degradation;
2. detects changes in URL-derived feature distributions;
3. conditionally retrains;
4. evaluates a candidate against the production model;
5. versions data, code, experiments, model artifacts, and deployment evidence; and
6. deploys only an accepted candidate through CI/CD.

### Research question

How does temporal data drift affect phishing URL detection models, and can a drift-aware MLOps pipeline maintain or recover model performance through conditional retraining?

### Hypotheses to test (not assume)

- **H1 — Temporal degradation:** a classifier trained on historical data experiences measurable performance change on temporally newer data.
- **H2 — Drift relationship:** performance changes are associated with measurable changes in URL-derived feature distributions.
- **H3 — Adaptive retraining:** drift-triggered retraining can recover a meaningful portion of lost performance while avoiding unnecessary retraining when drift is insignificant.

Report the actual results even if a hypothesis is unsupported, drift does not correspond to a large performance change, or retraining does not improve performance.

---

## 4. Dataset Strategy

### Primary dataset: PhreshPhish

The supplied project description selected **PhreshPhish** as the primary dataset because it includes dates and supports temporal evaluation.

Dataset page: https://huggingface.co/datasets/phreshphish/phreshphish  
Dataset paper: https://arxiv.org/abs/2507.10854

The project description cited a release with 666,315 rows and fields including URL, label/target, date, language, language score, HTML, and metadata. **Treat those counts and fields as historical details from the supplied brief, not guaranteed current facts.** Verify the current dataset card, files, schema, date coverage, license/terms, class balance, and practical download requirements before using it.

The description noted a release size around 36.6 GB. Do not download or move the entire release through every pipeline stage unless required and feasible. Build a documented, manageable research subset that preserves chronology and class representation appropriately.

### Dataset verification checklist

- Confirm dataset card, license/terms, intended anti-phishing research use, and citation requirements.
- Inspect dataset configuration, file formats, schema, row counts, missing values, date parsing, class labels, duplicates, and class balance.
- Inspect collection date coverage and sample counts per time period.
- Determine whether timestamps represent comparable observation/collection dates.
- Check for duplicates and near-duplicates across train, validation, and test periods.
- Define the subset sampling method, random seed, selected date range, and inclusion/exclusion rules.
- Preserve chronological order for the main temporal experiment.
- Record dataset provenance and the exact snapshot/version used.
- Avoid storing the full raw dataset in Git.
- Never silently choose arbitrary temporal cut-points before inspecting the actual date distribution.

### Secondary dataset

An independent dataset such as URL-Phish may be used for external/cross-dataset validation if practical. Treat it as external distribution-shift evaluation unless its collection process supports a valid temporal interpretation. It is optional and must not become a blocker to the primary PhreshPhish temporal study.

PhiUSIIL may be considered as a secondary benchmark, not the primary dataset for the central temporal research question:
https://archive.ics.uci.edu/dataset/967/phiusil-phishing-url-dataset

---

## 5. ML Data and Feature Design

### URL-only feature extraction

Create one shared, tested feature-extraction implementation reused by:
- offline training;
- validation and testing;
- drift analysis;
- candidate retraining;
- FastAPI inference.

Candidate features include:

- URL length;
- hostname/domain length;
- path length;
- query-string length;
- counts of dots, hyphens, digits, special characters, and parameters;
- number of subdomains;
- HTTPS indicator;
- IP-address-host indicator;
- lexical/structural character statistics;
- other lightweight URL-only features justified by inspection and tested for robustness.

Do not include HTML-derived or webpage-content features in the production feature vector because the initial API receives only a URL. Prevent training-serving skew by using the same feature code and schema in all stages.

Handle malformed URLs, missing values, ports, internationalized domains, IPv4/IPv6 literals, URL encoding, and edge cases safely. Document whether URL parsing normalizes or preserves each component.

### Label handling

Inspect actual label values and map them explicitly to a stable internal target. Do not assume which numeric/string label means phishing. Check class balance and make evaluation metrics consistent with the chosen positive class.

### Leakage prevention

- Deduplicate carefully before splitting where appropriate.
- Keep the main temporal split chronological.
- Fit learned preprocessing only on training data.
- Use validation data for model/threshold selection.
- Keep a final held-out test period untouched until final evaluation.
- Do not use final test outcomes to tune drift thresholds or candidate acceptance.
- Do not train on future data and then claim that the model was tested on that same future period.

---

## 6. Experimental Design

### Experiment A — Conventional random-split baseline

Use a controlled train/validation/test split for a conventional benchmark. A stratified split may be appropriate if it does not violate the chosen baseline design; document the split and seed.

Candidate algorithms:
- Logistic Regression;
- Random Forest;
- XGBoost;
- LightGBM, if dependency and compute constraints permit.

Use scikit-learn-compatible pipelines where practical. Set reproducible seeds. Compare models on the same split and feature set.

### Experiment B — Temporal split (main research experiment)

Inspect the actual dates before setting cut-points. Train on earlier observations, tune on a later validation period, and evaluate on a future held-out period. Keep the temporal boundaries explicit and reproducible.

Compare random-split and temporal-split results and quantify performance change. Do not presume that temporal performance must degrade; report the actual result.

### Experiment C — Feature drift analysis

Compare a documented reference period with newer batches using URL-derived features only.

Choose appropriate statistical tests and/or a drift library after checking feature types and sample sizes. Potential approaches include:
- Kolmogorov–Smirnov tests for suitable continuous distributions;
- chi-square or related tests for categorical/count features where assumptions hold;
- population stability index (PSI), with documented binning;
- a library such as Evidently if it fits the design.

Account for multiple feature tests where appropriate. Record effect sizes or practical magnitude as well as statistical significance. Large datasets can make tiny changes statistically significant. Set and justify a drift decision rule using reference/validation data, not the final held-out test.

A drift alert is a **trigger to investigate/evaluate**, not proof of performance loss or permission to deploy a new model.

### Experiment D — Conditional retraining

When the documented drift rule is triggered:
1. identify the eligible, versioned newer training data;
2. run the reproducible training pipeline;
3. create a candidate model (e.g., V2);
4. evaluate it on validation data that is separate from candidate training;
5. compare it with the current production model using predefined acceptance rules;
6. retain all artifacts, metrics, logs, dataset IDs, and decision evidence.

If drift is not triggered, retain the production model and record the monitoring decision.

### Experiment E — Static vs adaptive strategy

This is the principal final comparison:
- **Static strategy:** train initial V1 and keep it deployed throughout the evaluation period.
- **Adaptive strategy:** start from the same initial V1, monitor newer data, conditionally retrain, and promote only accepted candidates.

Use comparable evaluation periods and clearly distinguish:
- labeled data used to evaluate performance;
- unlabeled data used only for feature-drift monitoring;
- eligible training data available at each simulated time point.

Compare performance trajectories, drift alerts, retraining frequency, candidate acceptance/rejection, and operational costs/latency where feasible. Avoid using future labels or data prematurely in a simulated online lifecycle.

---

## 7. Evaluation and Acceptance Criteria

Accuracy alone is insufficient.

Record:
- F1-score (proposed primary comparison metric);
- precision;
- recall;
- ROC-AUC where meaningful;
- confusion matrix;
- false-positive rate;
- inference latency;
- training time;
- model size;
- drift statistics and flagged features;
- number of drift alerts;
- retraining frequency;
- candidate acceptance/rejection outcomes;
- static versus adaptive performance over time.

The positive class must be explicitly defined. In security screening, recall is important for catching phishing URLs, while precision and false-positive rate matter because legitimate URLs can be incorrectly flagged.

### Candidate promotion rule

Define a documented rule before final evaluation. A candidate should not be promoted simply because its training score is higher or because drift was detected.

A practical rule may require:
- passing automated tests and artifact/schema validation;
- evaluation on the same appropriate held-out validation window as the incumbent;
- meeting a predefined minimum F1 or task-specific metric;
- not reducing critical recall below an agreed safety floor;
- acceptable false-positive rate and operational constraints;
- a successful container/API smoke test;
- recording the promotion decision and evidence.

Thresholds must be chosen and justified using development/validation evidence. Do not invent a result or claim that a candidate is better before experiments run.

Keep a known-good incumbent artifact and make deployment updates recoverable. In a simple implementation, rejected candidates leave the running production version unchanged.

---

## 8. MLOps Architecture and Technology Stack

The required lifecycle is:

**Raw data → dataset versioning → preprocessing → shared URL features → experiments → evaluation → model selection → model versioning → API → Docker → CI/CD → container registry → AWS EC2 → drift monitoring → conditional retraining → candidate evaluation → promotion/rejection.**

### Core technology choices

| Area | Planned technology | Role |
|---|---|---|
| Language | Python | ML, API, pipeline, monitoring |
| Data | pandas; Polars only if beneficial | Inspection and transformation |
| ML | scikit-learn, XGBoost; LightGBM optional | Candidate classifiers |
| Code history | Git + GitHub | Source and configuration history |
| Data/artifact versioning | DVC | Version datasets and selected artifacts |
| DVC remote | S3 or another configured remote | Store versioned data/artifacts outside Git |
| Experiment tracking | MLflow | Log parameters, metrics, and artifacts |
| API | FastAPI | `/predict`, `/health`, and metrics endpoint if appropriate |
| Packaging | Docker | Reproducible API runtime |
| CI/CD | GitHub Actions | Tests, image build/push, controlled deployment |
| Image registry | Docker Hub or AWS ECR | Versioned deployable container images |
| Cloud | AWS EC2 | Host the containerized service |
| Cloud storage | Amazon S3 if selected | DVC remote and/or artifact storage |
| Monitoring | Prometheus + Grafana | Scrape, query, and visualize service metrics |
| Drift | Python statistical tests/library | Compare reference and new URL-feature distributions |
| Tests | pytest | Unit, integration, and smoke tests |

Choose Docker Hub versus ECR and S3 configuration after considering time, account access, cost, permissions, and simplicity. Avoid implementing two alternatives when one is sufficient.

### Data and model traceability

Preserve links between:
- Git commit;
- dataset snapshot/DVC version;
- feature-extractor version;
- training configuration and random seed;
- experiment ID;
- model artifact/checksum;
- evaluation metrics;
- drift trigger and newer-data snapshot;
- candidate-versus-incumbent decision;
- Docker image tag/digest;
- deployed model version and deployment commit.

Do not assume that every model registry feature is provided by DVC. Use DVC for the configured data/artifact versioning and MLflow for experiment tracking; document exactly where model metadata and production state are stored.

---

## 9. Recommended Repository Structure

Inspect the existing repository before applying this layout. Adapt it without deleting useful work.

```text
AdaptivePhish/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── build-and-push.yml
│       └── deploy.yml
├── configs/
│   ├── data.yaml
│   ├── features.yaml
│   ├── training.yaml
│   └── monitoring.yaml
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── reference/
├── models/
│   └── .gitkeep
├── notebooks/
│   └── 01_dataset_exploration.ipynb
├── reports/
│   ├── figures/
│   └── results/
├── scripts/
│   ├── inspect_dataset.py
│   ├── build_subset.py
│   └── run_monitoring.py
├── src/
│   └── adaptivephish/
│       ├── __init__.py
│       ├── data/
│       │   ├── load.py
│       │   └── preprocess.py
│       ├── features/
│       │   └── url_features.py
│       ├── models/
│       │   ├── train.py
│       │   ├── evaluate.py
│       │   ├── predict.py
│       │   └── promote.py
│       ├── monitoring/
│       │   ├── drift.py
│       │   └── metrics.py
│       ├── pipeline/
│       │   └── retrain.py
│       └── api/
│           └── main.py
├── tests/
│   ├── test_features.py
│   ├── test_preprocessing.py
│   ├── test_model.py
│   ├── test_api.py
│   └── test_promotion.py
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
│       └── dashboards/
├── Dockerfile
├── docker-compose.yml
├── dvc.yaml
├── params.yaml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

This is a proposed target layout, not a demand to create every file immediately. Use a standard Python package layout and keep imports/install behavior reliable. Add a `Makefile` only if useful for the user's environment. Keep large datasets and generated model binaries outside ordinary Git history.

---

## 10. DVC and Reproducible Pipelines

DVC is a core requirement, not a label added to the README.

Implement and verify:
- `dvc init`;
- `.dvc` tracking or DVC pipeline outputs as appropriate;
- a configured remote for data/artifacts;
- data retrieval and version restoration;
- a reproducible pipeline defined in `dvc.yaml`;
- parameters in `params.yaml` or a documented equivalent;
- `dvc repro` to run pipeline stages;
- versioned dataset/subset and processed-feature outputs;
- a clear division between files tracked by Git and content managed by DVC;
- instructions for a clean checkout and reproduction.

Possible pipeline stages:
1. inspect/build a research subset;
2. preprocess and create random/temporal splits;
3. extract URL features;
4. train baseline candidates;
5. evaluate and record results;
6. generate drift/reference artifacts;
7. train a candidate when the retraining workflow requests it.

Do not put the full dataset into Git. If S3 is used as a DVC remote, document bucket setup, region, permissions, and commands. Never hard-code credentials. Use IAM roles for EC2 where appropriate and short-lived/managed credentials locally when possible.

A large pipeline need not run automatically on every commit. CI should run fast tests; data-heavy training can be a separate workflow or manual dispatch. Explain this distinction.

---

## 11. MLflow Experiment Tracking

Use MLflow to log, at minimum:
- run name and experiment;
- algorithm and hyperparameters;
- random seed;
- dataset/version identifier;
- feature version/schema;
- train/validation/test date boundaries or split IDs;
- F1, precision, recall, ROC-AUC where applicable, and false-positive rate;
- training duration;
- model artifact and relevant plots/reports;
- selected-model decision.

Choose a tracking setup that matches time and infrastructure. A local tracking store can be sufficient for initial experiments; remote/shared tracking is optional if it adds substantial setup. Do not expose an MLflow server publicly without appropriate access controls.

Document how to inspect runs and reproduce the selected model.

---

## 12. FastAPI Service Contract

Build a production-style API with:
- `GET /health` — returns health/readiness information;
- `POST /predict` — accepts a URL and returns prediction, model version, and a score/probability if supported;
- `GET /metrics` — exposes Prometheus-compatible metrics if using Prometheus instrumentation.

Example request:

```json
{
  "url": "https://example.com/login"
}
```

Illustrative response only; do not hard-code this prediction:

```json
{
  "url": "https://example.com/login",
  "prediction": "legitimate",
  "score": 0.97,
  "model_version": "v1"
}
```

Define a stable response schema and label mapping. Validate inputs, handle malformed URLs, load the model once at startup rather than on every request, and use the exact shared feature extractor used during training. Avoid logging complete user URLs unnecessarily because URLs may contain sensitive query parameters. Do not claim a probability is calibrated confidence unless calibration was evaluated.

---

## 13. Docker

Create a small, secure Docker image that includes:
- application code;
- feature extraction;
- compatible model artifact/loading strategy;
- runtime dependencies;
- an appropriate non-root runtime user where practical;
- a predictable service port and startup command;
- health checks or a documented health-check method.

Verify:
- image builds;
- container starts;
- `/health` responds;
- `/predict` works with known test inputs;
- logs are understandable;
- model and feature versions match;
- the service can run without relying on undeclared files on the host.

Do not bake AWS credentials, GitHub tokens, or private data into the image. Keep image tags immutable/versioned where possible; use a commit SHA or release tag rather than relying solely on `latest`.

---

## 14. GitHub Actions CI/CD

Separate validation from deployment.

### CI workflow

On push and pull request:
1. check out repository;
2. set up a supported Python version;
3. install dependencies;
4. run lint/type checks if configured;
5. run unit tests;
6. run API/integration tests that are suitable for CI;
7. optionally validate Docker build;
8. fail the workflow if required checks fail.

Do not download the full research dataset or train all large models on every push unless necessary.

### Build and publish workflow

On an approved branch/tag or release:
1. run required checks;
2. build the Docker image;
3. tag it with a commit SHA/release version;
4. authenticate using GitHub Secrets or OIDC where supported;
5. push to the selected registry;
6. record the image digest and build commit.

### Deployment workflow

Deploy only from an approved workflow path after successful validation and image publishing. Use GitHub Actions secrets or AWS OIDC where configured, least-privilege IAM, and explicit environment approvals if practical. Do not allow an untrusted pull request to access production secrets.

Deployment should:
1. connect to the EC2 deployment mechanism;
2. pull the approved image;
3. replace/restart the service safely;
4. wait for health/readiness;
5. run a smoke test;
6. report success only if the smoke test succeeds;
7. retain enough information to restore the previous known-good version if deployment fails.

SSH deployment may be a practical first implementation; Systems Manager or OIDC-based AWS access can be considered if feasible. Choose one and document its security model rather than mixing approaches.

---

## 15. AWS Deployment

Target a single EC2-hosted Docker service initially. Keep architecture simple enough to complete and explain.

Required considerations:
- EC2 operating system and instance size chosen for available resources and cost;
- IAM role and least-privilege permissions;
- inbound rules restricted to necessary ports and trusted sources;
- SSH access restricted to the user's IP where SSH is used;
- API served on the intended port, with TLS/reverse proxy if exposed publicly;
- Docker installation and service startup;
- environment configuration outside the image;
- registry authentication using an appropriate credential mechanism;
- logs and restart behavior;
- health check and smoke test;
- deployment version tracking;
- rollback to the prior image/model;
- cleanup and cost control after testing.

Do not claim EC2, a bucket, ECR, or a public endpoint exists until it has actually been created and verified. Do not put credentials into Git, Docker layers, screenshots, or documentation.

The initial project can use Docker Hub to reduce AWS setup, or ECR for a more AWS-integrated flow. Select one. If DVC remote uses S3, make that a separate explicit decision.

---

## 16. Prometheus and Grafana

Grafana is required for visible operational monitoring. It visualizes metrics; it does not itself compute phishing model drift.

### Minimum monitoring implementation

Instrument the API/application and expose metrics such as:
- total prediction requests;
- requests by prediction outcome, using bounded labels;
- request latency histogram;
- error count;
- model version currently serving;
- model-load/health status;
- drift score or drift alert status;
- candidate training/promotion/rejection counters;
- last successful retraining timestamp or a suitable age metric.

Avoid high-cardinality metric labels such as full URLs, query strings, IP addresses, or arbitrary request IDs.

Prometheus should scrape the service metrics endpoint. Grafana should use Prometheus as a data source and provide a dashboard for:
- request volume;
- latency;
- errors;
- service/model health;
- current model version;
- drift status and relevant drift scores;
- retraining and promotion events.

Store dashboard/provisioning configuration in the repository where practical. Test that metrics change when API requests are made. Use an explicit network configuration for Prometheus and Grafana; do not expose admin interfaces publicly without access controls. For a time-constrained implementation, Docker Compose may be used locally first, then moved to EC2 or a suitable secured monitoring setup.

### Model monitoring caveat

URL-feature drift can be monitored on unlabeled incoming URLs. Precision, recall, F1, and actual error rates require ground-truth labels. Do not present feature drift as proof that accuracy has dropped.

---

## 17. Drift-Triggered Retraining and Model Promotion

Implement this as a controlled lifecycle, not an unconditional cron job.

### Expected logic

```text
Production Model V1
        |
        v
Receive/prepare a new URL batch
        |
        v
Extract features with the shared feature function
        |
        v
Compare new feature distributions with reference
        |
        +---- No significant drift ----> Record decision; keep V1
        |
        +---- Significant drift -------> Record trigger
                                            |
                                            v
                                    Run reproducible training
                                            |
                                            v
                                      Candidate Model V2
                                            |
                                            v
                                Validate schema and model artifact
                                            |
                                            v
                                Evaluate against incumbent V1
                                            |
                            +---------------+----------------+
                            |                                |
                        Accepted                          Rejected
                            |                                |
                            v                                v
                     Promote/deploy V2              Retain production V1
                            |
                            v
                     Health/smoke test
                            |
                            v
                 Record version and decision evidence
```

### Critical implementation details

- Define a reference dataset/window and feature schema.
- Use a documented drift method and threshold.
- Keep drift logic testable with synthetic shifted and non-shifted fixtures.
- Version the data used for retraining and record its time range.
- Never use the final test set as retraining input or candidate tuning evidence.
- Evaluate candidates on an appropriate labeled validation window.
- Use fixed acceptance criteria and record every decision.
- Ensure rejected candidates cannot overwrite the incumbent artifact or production container.
- Use an explicit promotion mechanism such as a versioned model manifest, registry tag, or deployment configuration.
- Avoid race conditions from concurrent retraining/deployments.
- Test the no-drift, drift-and-accepted, drift-and-rejected, and deployment-failure paths.
- If the real data stream or continuous labels are not available, simulate chronological batches using the held-out research periods and label this clearly as a controlled replay experiment.
- Do not claim live production learning if the implementation only runs a manual/offline replay.

The system should be able to demonstrate a complete event trail: drift decision → retraining run → candidate metrics → accept/reject → deployment version.

---

## 18. Testing Strategy

Use `pytest` and add tests incrementally.

### Unit tests
- URL parsing and feature extraction;
- malformed and edge-case URLs;
- label mapping and preprocessing;
- split chronology and leakage guards;
- drift calculation and thresholds;
- candidate acceptance/rejection;
- model loading and prediction schema.

### Integration tests
- training pipeline on a small fixture;
- artifact save/load and reproducible prediction;
- DVC pipeline stages where feasible;
- FastAPI `/health` and `/predict`;
- Prometheus metrics change after requests;
- Docker build and container smoke test;
- candidate promotion preserves incumbent on rejection.

### CI/CD and deployment tests
- workflow fails when tests fail;
- image has a unique version/tag;
- published image can be pulled;
- deployed service passes health and prediction checks;
- failed deployment does not silently mark the release successful;
- rollback instructions are verified as far as safe access allows.

Use a small deterministic test dataset in CI. Do not require AWS credentials or the full PhreshPhish dataset for ordinary unit tests.

---

## 19. Research Results and Reporting

At completion, produce actual evidence for:
- dataset and subset provenance;
- schema, dates, class balance, and duplicate analysis;
- URL feature definitions;
- random-split results;
- temporal-split results;
- quantified performance changes;
- drift statistics and decisions;
- baseline versus candidate metrics;
- retraining frequency and outcome;
- static versus adaptive comparison;
- API latency and container behavior;
- CI workflow evidence;
- cloud deployment evidence;
- Prometheus/Grafana dashboard evidence;
- limitations, failed hypotheses, and future work.

Use plots and tables generated from actual experiment outputs. Clearly label simulated/replayed monitoring results versus live telemetry. Do not fabricate performance improvements, screenshots, URLs, logs, workflow passes, or deployment claims.

### Final project demonstration should show

1. A working URL prediction API.
2. A versioned, reproducible data/training pipeline.
3. Experiment runs and model metrics.
4. CI tests and image build/publish.
5. A running AWS-hosted container if account access and budget permit.
6. Grafana dashboard backed by real Prometheus metrics.
7. A controlled drift event.
8. A retraining run and candidate comparison.
9. An accepted or rejected promotion decision.
10. A static-versus-adaptive analysis with evidence.

---

## 20. Phased Execution Plan Under Time Constraints

Prioritize a complete working vertical slice before optional sophistication.

### Phase 1 — Repository and environment
- Inspect existing project, OS, shell, Python, Git, Docker, and account access.
- Establish a clean Python environment and dependency management.
- Create/verify GitHub repository and `.gitignore`.
- Establish the target folder structure and README.
- **Definition of done:** repository runs a basic Python check and tests locally.

### Phase 2 — Dataset verification and compact research subset
- Verify the current PhreshPhish schema, terms, dates, labels, and practical download strategy.
- Create a documented subset and chronological split plan.
- Add DVC tracking and a working remote when credentials/storage are available.
- **Definition of done:** subset can be reconstructed/retrieved and its provenance is documented.

### Phase 3 — Baseline model and experiment tracking
- Implement shared URL features.
- Train and compare candidate classifiers on controlled data.
- Record runs in MLflow.
- Save model and metrics reproducibly.
- **Definition of done:** selected V1 can be reloaded and used to predict.

### Phase 4 — Temporal evaluation and drift
- Run the temporal experiment.
- Measure degradation/change without assuming the outcome.
- Implement drift metrics and a documented threshold.
- **Definition of done:** temporal metrics and drift reports are reproducible.

### Phase 5 — API and container
- Build FastAPI and unit/integration tests.
- Build and test Docker image.
- Add `/metrics`.
- **Definition of done:** container starts and prediction/health/metrics endpoints work.

### Phase 6 — GitHub Actions and registry
- Add CI tests.
- Add image build and publishing.
- Use secure secrets/OIDC and a versioned image tag.
- **Definition of done:** a controlled push/release produces a verified image only after tests pass.

### Phase 7 — AWS EC2 deployment
- Provision or inspect EC2 and IAM/security configuration.
- Deploy image and run health/smoke tests.
- Document rollback and cost cleanup.
- **Definition of done:** approved version is verifiably running, or any access/budget blocker is explicitly recorded.

### Phase 8 — Monitoring
- Configure Prometheus scrape.
- Configure Grafana data source and dashboard.
- Validate real metrics from requests.
- **Definition of done:** dashboard displays service telemetry.

### Phase 9 — Adaptive loop
- Implement drift trigger, retraining, candidate evaluation, promotion/rejection.
- Test all key paths, including rejected candidate.
- Connect approved promotion to deployment where safe.
- **Definition of done:** the full loop can be demonstrated with a recorded decision trail.

### Phase 10 — Final research comparison and documentation
- Compare static and adaptive strategies.
- Create results tables/figures.
- Complete architecture diagram, README, report, and demo steps.
- **Definition of done:** every claim is supported by reproducible evidence.

If time becomes critically short, prioritize:
1. working local training/API/Docker;
2. DVC data versioning and MLflow tracking;
3. GitHub Actions CI and image publishing;
4. one successful EC2 deployment;
5. Prometheus/Grafana telemetry;
6. controlled drift/retraining and model promotion;
7. expanded research and polish.

Do not silently remove a core requirement. If something cannot be completed, record it as a blocker or limitation rather than marking it done.

---

## 21. External Sources and Literature

Use these as starting points, and verify that links and versions are current during implementation.

- PhreshPhish dataset: https://huggingface.co/datasets/phreshphish/phreshphish
- PhreshPhish paper: https://arxiv.org/abs/2507.10854
- UCI PhiUSIIL dataset: https://archive.ics.uci.edu/dataset/967/phiusil-phishing-url-dataset
- Generalization research cited in the supplied project brief: Rashid et al. (2024), https://doi.org/10.1016/j.comnet.2024.110398
- Adaptive phishing research cited in the supplied brief: AdaptPUD (2025), https://doi.org/10.1016/j.comnet.2025.111303
- DVC documentation: https://dvc.org/doc
- MLflow documentation: https://mlflow.org/docs/latest/
- GitHub Actions: https://docs.github.com/en/actions
- Docker documentation: https://docs.docker.com/
- AWS EC2 documentation: https://docs.aws.amazon.com/ec2/
- Amazon ECR documentation: https://docs.aws.amazon.com/ecr/
- Amazon S3 documentation: https://docs.aws.amazon.com/s3/
- Prometheus documentation: https://prometheus.io/docs/introduction/overview/
- Grafana documentation: https://grafana.com/docs/
- FastAPI documentation: https://fastapi.tiangolo.com/
- scikit-learn documentation: https://scikit-learn.org/stable/
- XGBoost documentation: https://xgboost.readthedocs.io/

Do not claim these references were freshly checked unless they actually were. Use research papers to establish context and accurately qualify the contribution.

---

## 22. Final Acceptance Checklist

The project is complete only to the extent that the following evidence exists.

### Research and ML
- [ ] Dataset provenance, license/terms, schema, labels, dates, duplicates, and class balance documented.
- [ ] URL-only feature extraction shared between training and inference.
- [ ] Random-split baseline evaluated.
- [ ] Chronological temporal experiment evaluated.
- [ ] Temporal performance change reported honestly.
- [ ] Drift method, threshold, and decisions documented.
- [ ] Conditional retraining implemented.
- [ ] Candidate V2 evaluated against incumbent V1.
- [ ] Promotion/rejection criteria are explicit and tested.
- [ ] Static versus adaptive comparison reported with actual results.

### MLOps
- [ ] GitHub repository and reproducible environment.
- [ ] DVC data/artifact tracking.
- [ ] DVC remote configured and retrieval tested, if storage access is available.
- [ ] Reproducible DVC pipeline and parameters.
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

---

## 23. Instructions for Starting Work in Claude

**Do not immediately generate the whole project. Start with repository discovery and Phase 1 only.**

First response should:
1. confirm the intended objective in a concise paragraph;
2. summarize the required core components and end-to-end flow;
3. ask the user to open/provide the current repository context or run minimal environment-inspection commands if repository tools are unavailable;
4. identify any existing files before proposing changes;
5. give the exact first milestone, commands, expected output, and definition of done;
6. wait for the user to run commands and share results if direct execution is unavailable.

If Claude has file/terminal tools, inspect the repository and environment directly, but do not delete or overwrite existing work without checking it. If a command fails, diagnose that failure before proceeding. Continue milestone by milestone and update the acceptance checklist based on verified evidence.

**Master principle:** build a working, reproducible, secure, observable MLOps system around the phishing URL model. The classifier is necessary, but the key project contribution is the complete evidence-backed lifecycle—from versioned data and experiments to monitored deployment, drift-triggered retraining, candidate evaluation, and controlled model promotion.
