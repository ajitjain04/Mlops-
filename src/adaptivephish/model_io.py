"""Save, load and use the production model. Shared by training scripts and the API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from adaptivephish.features.url_features import FEATURE_VERSION, extract_features_df

PRODUCTION_FILE = Path("models/production.json")


@dataclass
class LoadedModel:
    model: Any
    feature_names: list[str]
    threshold: float
    metadata: dict[str, Any]

    def predict_proba(self, urls: list[str]) -> np.ndarray:
        """P(phishing) per URL, using the same extractor and column order as training."""
        x = extract_features_df(urls)[self.feature_names]
        return self.model.predict_proba(x)[:, 1]

    def predict(self, urls: list[str]) -> np.ndarray:
        """Label per URL: 1 = phishing, 0 = benign, using the validation-selected threshold."""
        return (self.predict_proba(urls) >= self.threshold).astype(int)


def load_production(path: str | Path = PRODUCTION_FILE) -> LoadedModel:
    meta = json.loads(Path(path).read_text())
    if meta["feature_version"] != FEATURE_VERSION:
        raise RuntimeError(
            f"model expects feature_version {meta['feature_version']}, code has {FEATURE_VERSION}"
        )
    model = joblib.load(Path(meta["model_path"]))
    return LoadedModel(model, list(meta["feature_names"]), float(meta["threshold"]), meta)
