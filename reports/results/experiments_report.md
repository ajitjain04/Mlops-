# Experiments A and B (M5)

Data: 88,986-row subset (subset_sha256 `aa62bfce…`), shared features v1.0.0. Seed 42. All runs in local MLflow (`sqlite:///mlflow.db`, experiments `adaptivephish-temporal` and `adaptivephish-random-split`; the store is gitignored and not on the DVC remote). Raw numbers: `experiments_summary.json`; figure: `reports/figures/f1_random_vs_temporal.png`.

Protocol: each config is fit on train and scored on validation; the threshold maximises validation F1; the best config per algorithm and V1 are chosen by validation F1 only. Test is scored once, for already-selected models. Temporal split: train Jun-Jul 2025, val Aug, test Sep-Oct (class balance 50/50 in val, 46.7% phish in test). Random split: stratified, same sizes, seed 42. Every model is trained with the production feature set (26) and with all 29 features.

## Test F1 of the selected model per algorithm

| Algorithm | Random, prod | Temporal, prod | Random, all | Temporal, all |
|---|---|---|---|---|
| Logistic regression | 0.817 | 0.801 | 0.819 | 0.800 |
| Random forest | 0.924 | 0.838 | 0.926 | 0.841 |
| XGBoost | 0.920 | 0.838 | 0.923 | 0.838 |
| LightGBM | 0.926 | 0.836 | 0.928 | 0.841 |

Random-split to temporal change for the tree models is about -0.08 to -0.09 F1 (ROC-AUC 0.98 to 0.93). Logistic regression drops less (-0.016) but starts much lower. This is a single split per setting with no repeated seeds; the random split mixes months and shares hostnames across train/test, so it is likely optimistic. Part of the temporal drop may come from how each class was collected rather than from drift.

## V1

Random forest (300 trees, no depth limit, min_samples_leaf 1), production features, threshold 0.183 chosen on validation. Validation F1 0.862 (best of the four on production features). Test: F1 0.838 (95% bootstrap CI 0.834-0.841), precision 0.790, recall 0.891, FPR 0.207. The false-positive rate is high for a deployed detector. The F1-optimal threshold trades it for recall; a different operating point is a decision for later.

## Artifact-feature check (V1 hyperparameters, with vs without query/fragment/param features)

| | val F1 | test F1 (95% CI) | test FPR |
|---|---|---|---|
| Without (production, 26) | 0.862 | 0.838 (0.834-0.841) | 0.207 |
| With (all 29) | 0.867 | 0.841 (0.837-0.844) | 0.192 |

The artifact features add about +0.003 test F1, with overlapping CIs. So the dataset artifact is real but does not drive the results here, probably because 83% of phishing URLs have no query anyway and other features carry the signal. Excluding them costs little and avoids the failure on real benign URLs with query strings (not tested here: no such benign data exists in this dataset).

## Other suspiciously class-dependent features (`feature_diagnostics.csv`, `v1_permutation_importance_val.csv`)

- **path_depth and path_len** are by far the strongest single features (univariate AUC 0.22 and 0.23 on train; same on val/test). 47.6% of phishing URLs have an empty path versus 7.0% of benign, and `path_len` is also V1's top permutation feature (-0.066 val AUC when shuffled). Bare-domain phishing is plausible real behaviour, but benign samples that are deep page URLs may reflect how benign pages were crawled. Treat as the main dataset-dependence risk.
- **Host digits/hyphens** (`host_n_digits`, `host_digit_ratio`, `host_n_hyphens`): moderate (AUC about 0.62-0.65) and stable across periods; matches known phishing patterns. Not flagged by the thresholds.
- **is_https**: 97.6% of benign vs 82.1% of phishing; AUC 0.39-0.44. Likely a real signal today but weakens as HTTPS becomes universal; worth watching in drift analysis.
- **host_entropy, host_longest_label, host_len**: moderate, stable.
- No feature's univariate AUC shifted by 0.1 or more from train to test; the thresholds (|AUC-0.5|*2 >= 0.5, zero-rate gap >= 0.3, shift >= 0.1) were set by me and are coarse. The query/fragment/param artifact was not caught by the zero-rate rule (gap 0.12) and was found earlier by direct inspection.
- Features with no variation in practice (`parse_ok`, `has_userinfo`, `host_is_idn`) are uninformative here.

## Limitations

Single seed and split; validation F1 differences between top tree models are small (0.851-0.862) so the V1 pick (random forest) is not strongly separated from LightGBM or XGBoost. Hyperparameter grids are small (1-4 configs per algorithm). Test was not used for selection.
