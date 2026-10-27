# Feature drift detection (M6)

Code: `src/adaptivephish/drift.py`; calibration: `scripts/calibrate_drift.py` (DVC stage `calibrate_drift`); evidence: `drift_calibration.json`, `reports/figures/drift_calibration.png`; tests: `tests/test_drift.py` (synthetic shifted and unshifted fixtures).

## Method
- **Reference:** V1's training window, 2025-06-05..2025-07-31 (31,485 URLs), production features only. Frozen in `data/processed/drift_reference.parquet` (DVC).
- **Batch:** 2,000 unlabeled URLs. The decision uses feature values only, never labels (tested).
- **Per feature:** effect size = PSI (10 reference-quantile bins, open outer bins) plus the KS statistic (or proportion gap for binary features); significance = two-sample KS p-value (chi-square for binary), Bonferroni over the 20 tested features at alpha 0.05. A feature has drifted only if PSI >= 0.1 (conventional "meaningful shift" floor) AND the corrected p-value is significant, because large samples make tiny shifts significant (tested: a 2% scale shift is significant but stays below the PSI floor).
- **Batch alert:** at least K of the 20 tested features have drifted. KS on discrete counts is conservative because of ties.
- Six features with under 1% non-modal values in the reference (`host_is_ip`, `host_has_port`, `has_userinfo`, `has_at_symbol`, `host_is_idn`, `parse_ok`) are not tested; rare binaries give unstable PSI and invalid chi-square cells.

## Calibration (reference and validation only; the test period is never loaded, asserted in the script)
- **iid null** (100 random 2,000-row hold-outs from the reference): 0 drifted features every time. So the PSI floor plus Bonferroni gate controls false alarms under stationary sampling.
- **Time-block null** (contiguous 2,000-row blocks of the reference vs the rest, stride 500, 59 overlapping blocks, about 15 independent): the reference is NOT stationary. Alert rate by K: K=1 75%, K=3 59%, K=10 31%, K=16 6.8%, **K=17 3.4%**, K=18 0%. K is the smallest value with null alert rate <= 5%, so **K = 17 of 20**.
- **Validation (Aug 2025, 10 batches), reported, not used to choose K:** drifted-feature counts 15, 1, 13, 0, 4, 8, 2, 2, 1, 4; **0/10 alerts at K=17**. For reference, alerts on validation would be 5/10 at K=3 and 2/10 at K=10-13. `path_len` drifts in nearly every batch.

## What this means (read before relying on alerts)
1. Daily class mix in this dataset swings between about 0% and 100% phishing. Across reference blocks the number of drifted features correlates with the batch phishing fraction (Spearman 0.51, p < 0.001; descriptive, labels not used by the rule). Much "feature drift" here is composition change, not a change within a class. In validation the correlation is about 0 (10 batches only).
2. Because the reference itself contains large internal shifts (late July differs sharply from June/early July), a rule that is quiet on the reference must require almost all features to move. K=17 is therefore insensitive: it did not fire on any validation batch even though per-feature drift is visible. A lower K is more sensitive but would also alert on 30-60% of ordinary reference blocks.
3. An alert means investigate or evaluate a candidate. It is not evidence of lower accuracy and does not deploy anything. Whether drift relates to performance (H2) is NOT tested here; that needs labeled batches and is left to the later replay on the held-out period, with this rule frozen.

## Decision for you
The calibrated K=17 follows the stated procedure but is conservative. If you want a more sensitive trigger for the adaptive loop (for example K=10, 2/10 validation alerts, 31% null rate), that is a one-line change in the calibration rule, and it should be chosen before any test-period replay.
