# URL feature extraction (M4)

Implementation: `src/adaptivephish/features/url_features.py` (version `1.0.0`, 29 numeric features, all URL-only). Schema: `reports/results/feature_schema.json`. Parsing policy and its limits are in the module docstring (raw string preserved, no decoding, host via `urlsplit`, IP literals via `ipaddress`, subdomain count is a heuristic without a public-suffix list, encoded-IPv4 hosts not detected).

Tests: `tests/test_features.py` (19 tests incl. IPv4/IPv6, userinfo, IDN/punycode, percent-encoding, invalid ports, None/empty/non-str, 20k-char URLs). Run on the 88,986-row subset: 3.8 s, no NaN, `parse_ok` = 1 for every row.

## Dataset artifact: benign URLs have no query or fragment

In the subset, 0 of the benign URLs contain `?` or `#`, versus 16.7% (`?`) and 0.9% (`#`) of phishing URLs. So `query_len`, `fragment_len` and `n_params` separate the classes because of how the dataset was collected or cleaned, not because of phishing behaviour. A model trained on them would likely flag real benign URLs that carry a query string. They are computed (the API must accept any URL) and listed in `DATASET_ARTIFACT_FEATURES`; M5 should compare models with and without them, and the production model should probably exclude them. Other features (scheme, host digits, path depth) are also strongly class-dependent in this data and may carry similar dataset-specific signal; the leakage check in M5 should look at feature importances.

## Not yet done

The extractor is not yet used by a trained model or the API, so "shared between training and inference" is not ticked. Only `featurize` output exists so far.
