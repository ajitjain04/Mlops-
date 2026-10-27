"""Experiments A (random split) and B (temporal split), tracked in MLflow.

Protocol (no test peeking):
- Every config is fit on train and scored on validation; the decision threshold is the one
  maximising validation F1. Selection (best config per algorithm, and V1) uses validation F1
  only.
- Test metrics are computed once, only for the already-selected model of each algorithm.
- Each experiment is run with the production feature set and with all 29 features.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import time
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from lightgbm import LGBMClassifier  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import FunctionTransformer, StandardScaler  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from adaptivephish.features.url_features import (  # noqa: E402
    DATASET_ARTIFACT_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    PRODUCTION_FEATURE_NAMES,
)

ALGOS = ("logreg", "random_forest", "xgboost", "lightgbm")
# Types skops must be told to trust when MLflow serialises our own freshly trained models
# (reviewed: all are the model classes we instantiate in this script, nothing else).
SKOPS_TRUSTED = [
    "sklearn.tree._tree.Tree",
    "xgboost.core.Booster",
    "xgboost.sklearn.XGBClassifier",
    "collections.OrderedDict",
    "lightgbm.basic.Booster",
    "lightgbm.sklearn.LGBMClassifier",
]
REPORT_KEYS = ("f1", "precision", "recall", "roc_auc", "fpr")


def make_estimator(algo: str, hp: dict, seed: int):
    if algo == "logreg":
        return Pipeline([
            ("log1p", FunctionTransformer(np.log1p)),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, random_state=seed, **hp)),
        ])
    if algo == "random_forest":
        return RandomForestClassifier(random_state=seed, n_jobs=-1, **hp)
    if algo == "xgboost":
        return XGBClassifier(random_state=seed, n_jobs=-1, eval_metric="logloss", **hp)
    if algo == "lightgbm":
        return LGBMClassifier(random_state=seed, n_jobs=-1, verbose=-1, **hp)
    raise ValueError(algo)


def configs(grid: dict) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*grid.values())]


def best_threshold(y, p) -> float:
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    return float(thr[int(np.argmax(f1))])


def metrics(y, p, thr: float) -> dict[str, float]:
    pred = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "f1": float(f1_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred)),
        "roc_auc": float(roc_auc_score(y, p)),
        "fpr": float(fp / (fp + tn)),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def bootstrap_f1_ci(y, p, thr: float, seed: int, n: int = 1000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    y, pred = np.asarray(y), (np.asarray(p) >= thr).astype(int)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        vals.append(f1_score(y[i], pred[i]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def git_info() -> dict[str, str]:
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()

    return {"git_commit": run("rev-parse", "HEAD"), "git_dirty": str(bool(run("status", "-s")))}


def dvc_md5(path: str) -> str:
    lock = yaml.safe_load(Path("dvc.lock").read_text())
    for stage in lock["stages"].values():
        for out in stage.get("outs", []):
            if out["path"] == path:
                return out["md5"]
    return "unknown"


def run_experiment(exp_name, parts, boundaries, feature_sets, P, base_tags):
    """Returns {featureset: {algo: record}} where record holds the selected model + metrics."""
    mlflow.set_experiment(exp_name)
    seed = P["seed"]
    out: dict = {}
    tr, va, te = (parts[k] for k in ("train", "val", "test"))
    for fs_name, cols in feature_sets.items():
        out[fs_name] = {}
        for algo in ALGOS:
            best = None
            for hp in configs(P["grids"][algo]):
                est = make_estimator(algo, hp, seed)
                t0 = time.time()
                est.fit(tr[cols], tr["y"])
                dur = time.time() - t0
                pv = est.predict_proba(va[cols])[:, 1]
                thr = best_threshold(va["y"], pv)
                vm = metrics(va["y"], pv, thr)
                with mlflow.start_run(run_name=f"{fs_name}-{algo}-{hp}") as run:
                    mlflow.set_tags({**base_tags, "feature_set": fs_name, "algorithm": algo})
                    mlflow.log_params({
                        "algorithm": algo, "seed": seed, "feature_set": fs_name,
                        "n_features": len(cols), "threshold": round(thr, 6),
                        **{f"hp_{k}": str(v) for k, v in hp.items()},
                        **{f"split_{k}": str(v) for k, v in boundaries.items()},
                    })
                    mlflow.log_metrics({f"val_{k}": v for k, v in vm.items()})
                    mlflow.log_metric("train_seconds", dur)
                    run_id = run.info.run_id
                if best is None or vm["f1"] > best["val"]["f1"]:
                    best = {"algo": algo, "hp": hp, "est": est, "threshold": thr, "val": vm,
                            "run_id": run_id, "cols": cols, "train_seconds": dur}
            # Final evaluation of the already-selected model: the only time test is scored.
            pt = best["est"].predict_proba(te[cols])[:, 1]
            best["test"] = metrics(te["y"], pt, best["threshold"])
            best["pt"] = pt
            with mlflow.start_run(run_id=best["run_id"]):
                mlflow.set_tag("selected_for_algorithm", "true")
                mlflow.log_metrics({f"test_{k}": v for k, v in best["test"].items()})
                mlflow.sklearn.log_model(
                    best["est"], name="model", skops_trusted_types=SKOPS_TRUSTED)
            out[fs_name][algo] = best
            print(f"[{exp_name}] {fs_name:10s} {algo:13s} val_f1={best['val']['f1']:.4f} "
                  f"test_f1={best['test']['f1']:.4f} hp={best['hp']}", flush=True)
    return out


def univariate_diagnostics(parts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    tr = parts["train"]
    for f in FEATURE_NAMES:
        r = {"feature": f}
        for role, d in parts.items():
            x = d[f]
            r[f"auc_{role}"] = float(roc_auc_score(d["y"], x)) if x.nunique() > 1 else 0.5
        z = tr[f] == 0
        r["zero_rate_benign_train"] = float(z[tr.y == 0].mean())
        r["zero_rate_phish_train"] = float(z[tr.y == 1].mean())
        rows.append(r)
    df = pd.DataFrame(rows)
    df["auc_strength_train"] = (df.auc_train - 0.5).abs() * 2
    df["auc_shift_train_to_test"] = (df.auc_test - df.auc_train).abs()
    df["zero_rate_gap"] = (df.zero_rate_benign_train - df.zero_rate_phish_train).abs()
    df["is_known_artifact"] = df.feature.isin(DATASET_ARTIFACT_FEATURES)
    df["flag_strong_univariate"] = df.auc_strength_train >= 0.5  # AUC >= 0.75 or <= 0.25
    df["flag_zero_inflated_one_class"] = df.zero_rate_gap >= 0.3
    df["flag_unstable"] = df.auc_shift_train_to_test >= 0.1
    return df


def table(res):
    return {
        fs: {
            a: {
                "hp": r["hp"],
                "threshold": r["threshold"],
                "val": {k: r["val"][k] for k in REPORT_KEYS},
                "test": {k: r["test"][k] for k in REPORT_KEYS},
            }
            for a, r in algs.items()
        }
        for fs, algs in res.items()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    args = ap.parse_args()

    P = yaml.safe_load(Path(args.params).read_text())["train"]
    assert tuple(P["exclude_features"]) == DATASET_ARTIFACT_FEATURES, "params/code mismatch"
    seed = P["seed"]
    mlflow.set_tracking_uri(args.tracking_uri)

    df = pd.read_parquet(args.features)
    manifest = json.loads(Path("reports/results/subset_manifest.json").read_text())
    meta_tags = {
        "dataset_revision": manifest["dataset_revision"],
        "subset_sha256": manifest["subset_sha256"],
        "features_dvc_md5": dvc_md5("data/processed/features.parquet"),
        "feature_version": FEATURE_VERSION,
        **git_info(),
    }
    feature_sets = {"production": list(PRODUCTION_FEATURE_NAMES), "all": list(FEATURE_NAMES)}

    # ---- Experiment B: temporal ----
    tparts = {r: df[df.role == r].reset_index(drop=True) for r in ("train", "val", "test")}
    tb = {
        r: f"{d.date.min():%Y-%m-%d}..{d.date.max():%Y-%m-%d} n={len(d)}"
        for r, d in tparts.items()
    }
    temporal = run_experiment(
        P["mlflow_experiment_temporal"], tparts, tb, feature_sets, P,
        {**meta_tags, "split": "temporal"},
    )

    # ---- Experiment A: stratified random split, same sizes as the temporal one ----
    sizes = {r: len(d) for r, d in tparts.items()}
    rest, rtest = train_test_split(df, test_size=sizes["test"], stratify=df.y, random_state=seed)
    rtrain, rval = train_test_split(rest, test_size=sizes["val"], stratify=rest.y,
                                    random_state=seed)
    rparts = {
        k: v.reset_index(drop=True)
        for k, v in (("train", rtrain), ("val", rval), ("test", rtest))
    }
    rb = {r: f"random stratified seed={seed} n={len(d)}" for r, d in rparts.items()}
    random_ = run_experiment(
        P["mlflow_experiment_random"], rparts, rb, feature_sets, P,
        {**meta_tags, "split": "random"},
    )

    # ---- V1: best production-feature-set temporal model by VALIDATION F1 only ----
    prod = temporal["production"]
    v1_algo = max(prod, key=lambda a: prod[a]["val"]["f1"])
    v1 = prod[v1_algo]
    print(f"V1 selected by validation F1: {v1_algo} {v1['hp']} val_f1={v1['val']['f1']:.4f}")
    mlflow.set_experiment(P["mlflow_experiment_temporal"])
    with mlflow.start_run(run_id=v1["run_id"]):
        mlflow.set_tags({
            "selected_model": "V1",
            "selection_rule": "max validation F1, temporal, production features",
        })

    # ---- Extra check: V1 hyperparameters on all 29 features (artifact features included) ----
    all_cols = feature_sets["all"]
    est_all = make_estimator(v1_algo, v1["hp"], seed)
    est_all.fit(tparts["train"][all_cols], tparts["train"]["y"])
    pv_all = est_all.predict_proba(tparts["val"][all_cols])[:, 1]
    thr_all = best_threshold(tparts["val"]["y"], pv_all)
    pt_all = est_all.predict_proba(tparts["test"][all_cols])[:, 1]
    m_all_val = metrics(tparts["val"]["y"], pv_all, thr_all)
    m_all_test = metrics(tparts["test"]["y"], pt_all, thr_all)
    ci_prod = bootstrap_f1_ci(tparts["test"]["y"], v1["pt"], v1["threshold"], seed)
    ci_all = bootstrap_f1_ci(tparts["test"]["y"], pt_all, thr_all, seed)
    with mlflow.start_run(run_name=f"v1-artifact-check-{v1_algo}"):
        mlflow.set_tags({**meta_tags, "split": "temporal", "purpose": "v1_artifact_feature_check",
                         "feature_set": "all", "algorithm": v1_algo})
        mlflow.log_params({"algorithm": v1_algo, "seed": seed, "threshold": round(thr_all, 6),
                           **{f"hp_{k}": str(v) for k, v in v1["hp"].items()}})
        mlflow.log_metrics({**{f"val_{k}": v for k, v in m_all_val.items()},
                            **{f"test_{k}": v for k, v in m_all_test.items()}})

    # ---- Diagnostics: which other features look suspiciously class-dependent ----
    diag = univariate_diagnostics(tparts)
    diag.to_csv("reports/results/feature_diagnostics.csv", index=False)
    val = tparts["val"]
    pi = permutation_importance(
        v1["est"], val[v1["cols"]], val["y"], scoring="roc_auc", n_repeats=5,
        random_state=seed, n_jobs=-1)
    imp = (pd.DataFrame({"feature": v1["cols"], "perm_importance_val_auc": pi.importances_mean})
           .sort_values("perm_importance_val_auc", ascending=False))
    imp.to_csv("reports/results/v1_permutation_importance_val.csv", index=False)

    # ---- Save V1 ----
    Path("models/v1").mkdir(parents=True, exist_ok=True)
    joblib.dump(v1["est"], "models/v1/model.joblib")
    production = {
        "model_version": "v1",
        "model_path": "models/v1/model.joblib",
        "algorithm": v1_algo,
        "hyperparameters": v1["hp"],
        "threshold": v1["threshold"],
        "positive_class": "phish (y=1)",
        "feature_version": FEATURE_VERSION,
        "feature_names": v1["cols"],
        "excluded_features": list(DATASET_ARTIFACT_FEATURES),
        "dataset_revision": manifest["dataset_revision"],
        "subset_sha256": manifest["subset_sha256"],
        "features_dvc_md5": meta_tags["features_dvc_md5"],
        "train_period": tb["train"],
        "val_period": tb["val"],
        "validation_metrics": {k: v1["val"][k] for k in REPORT_KEYS},
        "mlflow_tracking_uri": args.tracking_uri,
        "mlflow_run_id": v1["run_id"],
        "selection_rule": "max validation F1 among temporal-split production-feature models",
        **git_info(),
    }
    Path("models/production.json").write_text(json.dumps(production, indent=2))

    # ---- Summary + figure ----
    def check(m, thr_m, ci):
        return {"val_f1": m["val_f1"], "test_f1": m["test_f1"], "test_f1_ci95": ci,
                "test_precision": thr_m["precision"], "test_recall": thr_m["recall"],
                "test_fpr": thr_m["fpr"]}

    summary = {
        "v1": {"algorithm": v1_algo, "hp": v1["hp"], "threshold": v1["threshold"]},
        "temporal": table(temporal),
        "random_split": table(random_),
        "v1_artifact_check": {
            "without_artifact_features": check(
                {"val_f1": v1["val"]["f1"], "test_f1": v1["test"]["f1"]}, v1["test"], ci_prod),
            "with_artifact_features": check(
                {"val_f1": m_all_val["f1"], "test_f1": m_all_test["f1"]}, m_all_test, ci_all),
        },
        "split_boundaries": {"temporal": tb, "random": rb},
    }
    Path("reports/results/experiments_summary.json").write_text(json.dumps(summary, indent=2))

    fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for a, fs in zip(ax, ("production", "all"), strict=True):
        w = 0.38
        xs = np.arange(len(ALGOS))
        a.bar(xs - w / 2, [random_[fs][g]["test"]["f1"] for g in ALGOS], w, label="random split")
        a.bar(xs + w / 2, [temporal[fs][g]["test"]["f1"] for g in ALGOS], w, label="temporal")
        a.set_xticks(xs, ALGOS, rotation=20)
        a.set_title(f"{fs} features ({len(feature_sets[fs])})")
        a.set_ylim(0.5, 1.0)
    ax[0].set_ylabel("test F1")
    ax[0].legend()
    fig.tight_layout()
    Path("reports/figures").mkdir(parents=True, exist_ok=True)
    fig_path = "reports/figures/f1_random_vs_temporal.png"
    fig.savefig(fig_path, dpi=130)
    with mlflow.start_run(run_name="summary"):
        mlflow.set_tags({**meta_tags, "purpose": "summary", "selected_model": f"V1={v1_algo}"})
        for f in ("reports/results/experiments_summary.json",
                  "reports/results/feature_diagnostics.csv",
                  "reports/results/v1_permutation_importance_val.csv",
                  "models/production.json", fig_path):
            mlflow.log_artifact(f)
    print(json.dumps(summary["v1_artifact_check"], indent=2))


if __name__ == "__main__":
    main()
