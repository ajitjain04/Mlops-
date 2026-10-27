"""Label-free feature drift detection on URL-derived features.

A batch of unlabeled URLs is compared with a fixed reference window, feature by feature:
- effect size: PSI (bins = reference quantiles, outer bins open-ended) and the KS statistic;
- significance: two-sample KS p-value for multi-valued features, chi-square for binary ones,
  Bonferroni-corrected over the tested features.
A feature counts as drifted only if BOTH its PSI exceeds a practical-magnitude threshold AND
its corrected p-value is significant (large samples make tiny shifts significant). A batch
alerts when at least `min_drifted_features` features have drifted.

An alert means "investigate / evaluate a candidate". It is not evidence that accuracy fell
(that needs labels) and never deploys anything by itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp

PSI_EPS = 1e-4


@dataclass
class DriftConfig:
    psi_bins: int = 10
    psi_threshold: float = 0.1
    alpha: float = 0.05  # family-wise, Bonferroni over tested features
    min_drifted_features: int = 3
    min_variation: float = 0.01  # skip features whose non-modal value share is below this


@dataclass
class Reference:
    """Reference window snapshot: feature values plus the frozen PSI bin edges."""

    data: pd.DataFrame
    tested: list[str]
    skipped: dict[str, float]
    edges: dict[str, np.ndarray] = field(default_factory=dict)
    binary: set[str] = field(default_factory=set)


def _edges(x: np.ndarray, bins: int) -> np.ndarray:
    qs = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)[1:-1]))
    return qs


def build_reference(df: pd.DataFrame, features: Sequence[str], cfg: DriftConfig) -> Reference:
    tested, skipped, edges, binary = [], {}, {}, set()
    for f in features:
        x = df[f].to_numpy(dtype=float)
        vals, counts = np.unique(x, return_counts=True)
        non_modal = 1.0 - counts.max() / len(x)
        if non_modal < cfg.min_variation:
            skipped[f] = float(non_modal)
            continue
        tested.append(f)
        if set(vals.tolist()) <= {0.0, 1.0}:
            binary.add(f)
        else:
            edges[f] = _edges(x, cfg.psi_bins)
    return Reference(df[tested].reset_index(drop=True), tested, skipped, edges, binary)


def _props(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(edges, x, side="right")
    p = np.bincount(idx, minlength=len(edges) + 1) / len(x)
    return np.clip(p, PSI_EPS, None)


def psi(ref: np.ndarray, new: np.ndarray, edges: np.ndarray) -> float:
    p, q = _props(ref, edges), _props(new, edges)
    return float(np.sum((q - p) * np.log(q / p)))


def compare_feature(ref: Reference, batch: pd.DataFrame, f: str) -> dict[str, float]:
    r = ref.data[f].to_numpy(dtype=float)
    b = batch[f].to_numpy(dtype=float)
    if f in ref.binary:
        edges = np.array([0.5])
        table = np.array([[np.sum(r == 1), np.sum(r == 0)], [np.sum(b == 1), np.sum(b == 0)]])
        p = 1.0 if (table.sum(axis=0) == 0).any() else float(chi2_contingency(table)[1])
        d = abs(float(np.mean(b)) - float(np.mean(r)))
        return {"psi": psi(r, b, edges), "effect": d, "p_value": p}
    res = ks_2samp(r, b)
    return {
        "psi": psi(r, b, ref.edges[f]),
        "effect": float(res.statistic),
        "p_value": float(res.pvalue),
    }


def compare_batch(ref: Reference, batch: pd.DataFrame, cfg: DriftConfig) -> pd.DataFrame:
    """Per-feature table: psi, effect (KS D or proportion gap), p_value, drifted."""
    rows = {f: compare_feature(ref, batch, f) for f in ref.tested}
    out = pd.DataFrame(rows).T
    out.index.name = "feature"
    corrected = cfg.alpha / max(len(ref.tested), 1)
    out["drifted"] = (out.psi >= cfg.psi_threshold) & (out.p_value < corrected)
    return out


def detect_drift(ref: Reference, batch: pd.DataFrame, cfg: DriftConfig) -> dict:
    """Batch-level decision. Uses only feature columns, never labels."""
    table = compare_batch(ref, batch, cfg)
    drifted = table.index[table.drifted].tolist()
    return {
        "n_rows": len(batch),
        "n_tested": len(table),
        "n_drifted": len(drifted),
        "drifted_features": drifted,
        "alert": len(drifted) >= cfg.min_drifted_features,
        "max_psi": float(table.psi.max()),
        "table": table,
    }


def load_reference(
    reference_path: str = "data/processed/drift_reference.parquet",
    calibration_path: str = "reports/results/drift_calibration.json",
) -> tuple[Reference, DriftConfig]:
    """Rebuild the frozen reference (same bin edges) and the calibrated config."""
    import json
    from pathlib import Path

    cal = json.loads(Path(calibration_path).read_text())
    c = cal["config"]
    cfg = DriftConfig(c["psi_bins"], c["psi_threshold"], c["alpha"], c["min_drifted_features"],
                      c["min_variation"])
    data = pd.read_parquet(reference_path)
    ref = build_reference(data, cal["tested_features"], cfg)
    if ref.tested != cal["tested_features"]:
        raise RuntimeError("drift reference does not match calibrated feature list")
    return ref, cfg
