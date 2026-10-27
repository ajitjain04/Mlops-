"""Training/serving parity: features recomputed from raw URLs equal the stored training features."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from adaptivephish.features.url_features import PRODUCTION_FEATURE_NAMES, extract_features_df
from adaptivephish.model_io import load_production

SUBSET = Path("data/processed/subset.parquet")
FEATURES = Path("data/processed/features.parquet")

pytestmark = pytest.mark.skipif(
    not (SUBSET.exists() and FEATURES.exists()), reason="needs `dvc pull` data")


def test_serving_extraction_matches_training_features():
    sub = pd.read_parquet(SUBSET, columns=["sha256", "url"]).sample(500, random_state=0)
    feats = pd.read_parquet(FEATURES).set_index("sha256").loc[sub.sha256]
    fresh = extract_features_df(sub.url.tolist())[list(PRODUCTION_FEATURE_NAMES)]
    np.testing.assert_allclose(
        fresh.to_numpy(dtype=float), feats[list(PRODUCTION_FEATURE_NAMES)].to_numpy(dtype=float))


@pytest.mark.skipif(not Path("models/v1/model.joblib").exists(), reason="needs `dvc pull` model")
def test_model_feature_list_matches_code_and_estimator():
    m = load_production()
    assert m.feature_names == list(PRODUCTION_FEATURE_NAMES)
    n_in = getattr(m.model, "n_features_in_", len(m.feature_names))
    assert n_in == len(m.feature_names)
