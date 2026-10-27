"""Build the chronological research subset from the metadata table.

Window, cap and cut points live in params.yaml (section "subset"). They were chosen
after inspecting the date x label table (see reports/results/dataset_report.md): only
2025-06..2025-10 has both classes in every month at useful volume.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import yaml

PARAMS_PATH = "params.yaml"


def norm_url(u: str) -> str:
    return u.strip().lower().rstrip("/")


def host(u: str) -> str:
    try:
        return urlsplit(u if "://" in u else "//" + u).hostname or ""
    except ValueError:
        return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", default="data/interim/phreshphish_meta.parquet")
    ap.add_argument("--out", default="data/processed/subset.parquet")
    ap.add_argument("--manifest", default="reports/results/subset_manifest.json")
    ap.add_argument("--params", default=PARAMS_PATH)
    args = ap.parse_args()

    with open(args.params) as f:
        P = yaml.safe_load(f)["subset"]
    SEED = P["seed"]
    WINDOW = (P["window_start"], P["window_end"])
    CAP_PER_MONTH_LABEL = P["cap_per_month_label"]
    ROLES = P["roles_by_month"]

    df = pd.read_parquet(args.meta, columns=["sha256", "url", "label", "date", "split"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df.date >= WINDOW[0]) & (df.date <= WINDOW[1])].copy()
    n_window = len(df)
    df["nurl"] = df.url.map(norm_url)
    df = df.sort_values(["date", "sha256"]).drop_duplicates("nurl", keep="first")
    n_dedup = len(df)
    df["month"] = df.date.dt.strftime("%Y-%m")
    df = (df.sample(frac=1, random_state=SEED)
            .groupby(["month", "label"]).head(CAP_PER_MONTH_LABEL))
    df = df.sort_values(["date", "sha256"]).reset_index(drop=True)
    df["role"] = df.month.map(ROLES)
    df["y"] = (df.label == "phish").astype("int8")
    df["host"] = df.url.map(host)

    overlap = {}
    hosts = {r: set(g.host) for r, g in df.groupby("role")}
    for r in ("val", "test"):
        te = df[df.role == r]
        share = float(te.host.isin(hosts["train"]).mean())
        overlap[f"{r}_rows_with_host_in_train"] = round(share, 4)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[["sha256", "url", "label", "y", "date", "month", "role"]].to_parquet(out, index=False)
    manifest = {
        "dataset": "phreshphish/phreshphish",
        "dataset_revision": "eca603e0ecd4f698f8d4d226c088659e72681239",
        "license": "CC-BY-4.0 (anti-phishing research use only)",
        "seed": SEED, "window": WINDOW, "cap_per_month_label": CAP_PER_MONTH_LABEL,
        "roles_by_month": ROLES,
        "rows_in_window": n_window, "rows_after_url_dedup": n_dedup, "rows_subset": len(df),
        "counts": {f"{k[0]}|{k[1]}": int(v)
                   for k, v in df.groupby(["role", "label"]).size().items()},
        "per_month_label": {f"{k[0]}|{k[1]}": int(v)
                            for k, v in df.groupby(["month", "label"]).size().items()},
        "host_overlap": overlap,
        "subset_sha256": hashlib.sha256(
            "\n".join(df.sha256).encode()).hexdigest(),
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
