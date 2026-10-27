# PhreshPhish dataset verification (M2)

Verified 2026-10-27 against the live Hugging Face dataset card and parquet files.

- **Source:** https://huggingface.co/datasets/phreshphish/phreshphish, revision `eca603e0ecd4f698f8d4d226c088659e72681239` (v1.0.1, last modified 2026-10-24). Not gated.
- **License/terms:** CC-BY-4.0; the card says to use it only for anti-phishing research. Citation: Dalton et al. 2025, arXiv:2507.10854.
- **Schema:** `sha256, url, html, label ('phish'|'benign'), target, date (date32), lang, lang_score`. Label mapping: phish=1, benign=0 (our `y`).
- **Size:** 666,315 rows (train 498,255; test 168,060), 77 parquet shards, 36.6 GB. Only the metadata columns (no HTML) were read, via parquet column projection (`scripts/inspect_dataset.py`, ~46 MB).
- **Missing values:** `target` 367,904 (benign pages), `lang` 15,974; no missing url/label/date.
- **Duplicates:** 0 duplicate sha256, 0 duplicate URLs (exact), 0 URLs with conflicting labels, 0 test URLs in train. Near-duplicates were not checked beyond case/trailing-slash normalization.
- **Dates:** 2024-07-02 to 2025-12-16. The card's train/test split is itself chronological (train <= 2025-09-08, test >= 2025-09-08).

## Caveat: class and time are confounded

Benign and phishing samples are not spread evenly over time. 2024-07 is 99.7% phishing; there are no benign samples at all from 2024-11 to 2025-05; 2025-11/12 are almost all phishing. A split over the full range would let a model learn "date" through URL style rather than phishing. Dates are collection dates, and the two classes may have been collected by different processes, so a temporal drop could reflect collection changes as well as real drift.

## Subset (`scripts/build_subset.py`, seed 42)

- Window 2025-06-01..2025-10-31, the only months with both classes at useful volume.
- Exact-URL dedup after lowercase/trailing-slash normalization (removed 0 rows), then cap of 10,000 per month x label, random sample.
- Chronological roles: train = Jun-Jul, val = Aug, test = Sep-Oct. No shuffling across roles. Cut points were set after inspecting the table above.
- 88,986 rows: train 16,760 benign / 14,725 phish; val 10,000 / 10,000; test 20,000 / 17,501.
- Hostname overlap with train: 25.4% of val rows, 22.5% of test rows (leakage-adjacent; keep in mind for results).
- Rebuild is deterministic: two runs gave the same `subset_sha256` (`aa62bfce...`). Manifest: `reports/results/subset_manifest.json`.
- Caps flatten the natural class balance (about 50/50 here), so base rates in production will differ.

Not done: secondary dataset (optional); DVC tracking and remote (M3).
