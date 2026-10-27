import json

import joblib
from sklearn.ensemble import RandomForestClassifier

from adaptivephish.features.url_features import (
    DATASET_ARTIFACT_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    PRODUCTION_FEATURE_NAMES,
    extract_features_df,
)
from adaptivephish.model_io import load_production

URLS = ["https://example.com/", "http://paypal-login.verify-account.xyz/a/b/c/d", "http://1.2.3.4/x"]


def test_production_features_exclude_artifacts():
    assert set(PRODUCTION_FEATURE_NAMES) == set(FEATURE_NAMES) - set(DATASET_ARTIFACT_FEATURES)
    assert len(PRODUCTION_FEATURE_NAMES) == len(FEATURE_NAMES) - 3


def test_save_load_predict_roundtrip(tmp_path):
    cols = list(PRODUCTION_FEATURE_NAMES)
    x = extract_features_df(URLS * 10)[cols]
    model = RandomForestClassifier(n_estimators=5, random_state=0).fit(x, [0, 1, 1] * 10)
    joblib.dump(model, tmp_path / "m.joblib")
    meta = {"model_path": str(tmp_path / "m.joblib"), "feature_version": FEATURE_VERSION,
            "feature_names": cols, "threshold": 0.5}
    (tmp_path / "production.json").write_text(json.dumps(meta))
    loaded = load_production(tmp_path / "production.json")
    p = loaded.predict_proba(URLS)
    assert p.shape == (3,) and ((p >= 0) & (p <= 1)).all()
    assert list(loaded.predict(URLS)) == [0, 1, 1]
