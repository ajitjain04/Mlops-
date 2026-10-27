"""Extract shared URL features for the research subset (DVC stage `featurize`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from adaptivephish.features.url_features import (
    DATASET_ARTIFACT_FEATURES,
    FEATURE_VERSION,
    extract_features_df,
    feature_schema,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", default="data/processed/subset.parquet")
    ap.add_argument("--out", default="data/processed/features.parquet")
    ap.add_argument("--schema", default="reports/results/feature_schema.json")
    args = ap.parse_args()

    sub = pd.read_parquet(args.subset)
    feats = extract_features_df(sub.url)
    out = pd.concat([sub[["sha256", "date", "month", "role", "y"]], feats], axis=1)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)

    schema = feature_schema() | {
        "dataset_artifact_features": list(DATASET_ARTIFACT_FEATURES),
        "rows": len(out),
    }
    Path(args.schema).write_text(json.dumps(schema, indent=2))
    print(f"wrote {args.out} rows={len(out)} feature_version={FEATURE_VERSION}")


if __name__ == "__main__":
    main()
