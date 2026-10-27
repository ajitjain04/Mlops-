"""Calibrate the batch drift rule on the reference (train) and validation windows only.

The final test period is never loaded: rows are filtered at read time and asserted.
K (minimum number of drifted features that raises a batch alert) is the smallest value whose
false-alert rate on the time-block null is <= max_null_alert_rate. The null uses contiguous
blocks of the reference compared with the rest of the reference, so it includes the natural
day-to-day composition changes of the data. Validation outcomes are reported, not optimised.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from adaptivephish.drift import DriftConfig, build_reference, detect_drift  # noqa: E402
from adaptivephish.features.url_features import PRODUCTION_FEATURE_NAMES  # noqa: E402


def chunks(df: pd.DataFrame, size: int):
    for s in range(0, len(df) - size + 1, size):
        yield s, df.iloc[s : s + size]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--out-ref", default="data/processed/drift_reference.parquet")
    ap.add_argument("--out-json", default="reports/results/drift_calibration.json")
    ap.add_argument("--out-fig", default="reports/figures/drift_calibration.png")
    args = ap.parse_args()

    P = yaml.safe_load(Path(args.params).read_text())["drift"]
    seed = yaml.safe_load(Path(args.params).read_text())["train"]["seed"]
    feats = list(PRODUCTION_FEATURE_NAMES)
    df = pd.read_parquet(args.features, filters=[("role", "in", ["train", "val"])])
    assert set(df.role) == {"train", "val"}, "test period must not be loaded"
    tr = df[df.role == "train"].sort_values(["date", "sha256"]).reset_index(drop=True)
    va = df[df.role == "val"].sort_values(["date", "sha256"]).reset_index(drop=True)
    B = P["batch_size"]
    cfg = DriftConfig(P["psi_bins"], P["psi_threshold"], P["alpha"], 1, P["min_variation"])
    ref = build_reference(tr, feats, cfg)
    ref.data.to_parquet(args.out_ref, index=False)
    rng = np.random.default_rng(seed)

    # iid null: hold out B random reference rows, build the reference from the rest.
    iid = []
    for _ in range(P["null_repeats"]):
        perm = rng.permutation(len(tr))
        r = build_reference(tr.iloc[perm[B:]], feats, cfg)
        iid.append(detect_drift(r, tr.iloc[perm[:B]], cfg)["n_drifted"])

    # time-block null: contiguous block vs rest of the reference.
    blocks = []
    for s in range(0, len(tr) - B + 1, P["null_block_stride"]):
        blk = tr.iloc[s : s + B]
        rest = tr.drop(tr.index[s : s + B])
        o = detect_drift(build_reference(rest, feats, cfg), blk, cfg)
        blocks.append({"start_row": s, "n_drifted": o["n_drifted"], "max_psi": o["max_psi"],
                       "phish_fraction": float(blk.y.mean())})
    null_counts = np.array([b["n_drifted"] for b in blocks])

    n_tested = len(ref.tested)
    k_table = {
        k: float((null_counts >= k).mean()) for k in range(1, n_tested + 1)
    }
    K = next(k for k in range(1, n_tested + 1) if k_table[k] <= P["max_null_alert_rate"])

    # validation batches (reported, not used to choose K)
    val_rows = []
    for i, (_s, batch) in enumerate(chunks(va, B)):
        o = detect_drift(ref, batch, cfg)
        val_rows.append({
            "batch": i, "dates": f"{batch.date.min():%m-%d}..{batch.date.max():%m-%d}",
            "n_drifted": o["n_drifted"], "max_psi": o["max_psi"],
            "drifted_features": o["drifted_features"],
            "phish_fraction_descriptive_only": float(batch.y.mean()),
        })
    val_counts = np.array([v["n_drifted"] for v in val_rows])
    alerts_by_k = {k: int((val_counts >= k).sum()) for k in range(1, n_tested + 1)}

    rho_blocks = spearmanr([b["phish_fraction"] for b in blocks], null_counts)
    rho_val = spearmanr([v["phish_fraction_descriptive_only"] for v in val_rows], val_counts)

    cal = {
        "reference_window": f"{tr.date.min():%Y-%m-%d}..{tr.date.max():%Y-%m-%d} n={len(tr)}",
        "validation_window": f"{va.date.min():%Y-%m-%d}..{va.date.max():%Y-%m-%d} n={len(va)}",
        "test_period_used": False,
        "batch_size": B,
        "config": {"psi_bins": cfg.psi_bins, "psi_threshold": cfg.psi_threshold,
                   "alpha": cfg.alpha, "min_variation": cfg.min_variation,
                   "min_drifted_features": K},
        "tested_features": ref.tested,
        "skipped_features_non_modal_share": ref.skipped,
        "iid_null_n_drifted_distribution": np.bincount(iid).tolist(),
        "time_block_null": {
            "n_blocks": len(blocks), "n_drifted": null_counts.tolist(),
            "alert_rate_by_K": k_table, "chosen_K": K,
            "max_allowed_alert_rate": P["max_null_alert_rate"],
            "note": "overlapping blocks (stride < batch size); about "
                    f"{len(tr) // B} independent blocks, so rates are coarse",
        },
        "validation_batches": val_rows,
        "validation_alerts_by_K": alerts_by_k,
        "validation_alerts_at_chosen_K": f"{alerts_by_k[K]}/{len(val_rows)}",
        "descriptive_spearman_phish_fraction_vs_n_drifted": {
            "reference_blocks": [float(rho_blocks.statistic), float(rho_blocks.pvalue)],
            "validation_batches": [float(rho_val.statistic), float(rho_val.pvalue)],
        },
    }
    Path(args.out_json).write_text(json.dumps(cal, indent=2))

    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(range(len(null_counts)), null_counts, label="reference time-blocks (null)")
    ax.plot(np.arange(len(val_counts)) * (len(null_counts) / max(len(val_counts), 1)),
            val_counts, "o-", label="validation batches")
    ax.axhline(K, color="r", ls="--", label=f"alert threshold K={K}")
    ax.set_xlabel("batch index (rescaled)")
    ax.set_ylabel(f"drifted features (of {n_tested})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.out_fig, dpi=130)
    print(json.dumps({k: cal[k] for k in ("config", "validation_alerts_at_chosen_K",
                                          "validation_alerts_by_K")}, indent=2))
    print("time-block alert rate by K:", {k: round(v, 3) for k, v in k_table.items()})
    print("spearman:", cal["descriptive_spearman_phish_fraction_vs_n_drifted"])


if __name__ == "__main__":
    main()
