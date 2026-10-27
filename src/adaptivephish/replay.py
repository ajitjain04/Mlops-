"""Static vs adaptive replay with fixed, pre-registered promotion rules.

Design (params.yaml `replay`, locked by replay_lock.py, recorded in PROGRESS.md):
- the held-out stream is cut into batches in time order; each batch is scored by the model that is
  in production for the arm at that moment (prequential evaluation, no re-scoring afterwards);
- labels of batch j are usable only after batch j+D has been scored (D = label_delay_batches);
- at a decision after batch i: labelled batches are <= i-D; the gate set is the last
  `gate_batches` of them, the threshold batch the one before, and training uses everything
  older plus the base data;
- a candidate is promoted only if ALL promotion checks pass; otherwise the incumbent stays.
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_curve, roc_auc_score

from adaptivephish.drift import DriftConfig, Reference, detect_drift
from adaptivephish.features.url_features import FEATURE_VERSION
from adaptivephish.lifecycle import LifecycleState, new_arm_state
from adaptivephish.model_io import LoadedModel

CACHE_MAX = 3  # candidate models kept in memory across arms
PRIMARY_K = 17  # same as params drift.locked.min_drifted_features; used only for monitoring display

# Fixed canary set: a candidate must load and score these without error and return valid
# probabilities.
CANARY_URLS = [
    "https://www.nyc.gov/site/dcas/employment/jobs.page",
    "http://paypal-secure-login.example-verify.com/signin?id=1",
    "http://192.168.0.1:8080/admin/login.php",
    "https://example.com",
    "http://xn--80ak6aa92e.com/%D0%B2%D1%85%D0%BE%D0%B4",
    "http://user:pass@bank.example.org/@login",
    "https://a.b.c.d.e.f.example.net/" + "x" * 300,
    "ftp://files.example.org/readme.txt",
]


# ----------------------------------------------------------------------------- metrics


def best_threshold(y, p) -> float:
    """Threshold maximising F1 (same rule as the experiments)."""
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    return float(thr[int(np.argmax(f1))])


def counts_metrics(y, pred, p=None) -> dict:
    y, pred = np.asarray(y).astype(int), np.asarray(pred).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    out = {
        "n": len(y), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": prec, "recall": rec,
        "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
        "fpr": fp / (fp + tn) if (fp + tn) else 0.0,
    }
    if p is not None and len(np.unique(y)) == 2:
        out["roc_auc"] = float(roc_auc_score(y, p))
    return out


def paired_bootstrap_f1_diff(y, pred_cand, pred_inc, resamples: int, seed: int, level: float):
    """Interval of F1(candidate) - F1(incumbent) over paired row resamples."""
    y = np.asarray(y).astype(np.int8)
    pc, pi = np.asarray(pred_cand).astype(np.int8), np.asarray(pred_inc).astype(np.int8)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(y), size=(resamples, len(y)))

    def f1(pred):
        yy, pp = y[idx], pred[idx]
        tp = (yy & pp).sum(1)
        fp = ((1 - yy) & pp).sum(1)
        fn = (yy & (1 - pp)).sum(1)
        d = 2 * tp + fp + fn
        return np.where(d > 0, 2 * tp / np.maximum(d, 1), 0.0)

    diff = f1(pc) - f1(pi)
    a = (1 - level) / 2 * 100
    return float(np.percentile(diff, a)), float(np.percentile(diff, 100 - a))


# ----------------------------------------------------------------------------- promotion


def evaluate_promotion(y, p_inc, thr_inc, p_cand, thr_cand, rules: dict, *,
                       feature_version_ok: bool, canary_ok: bool) -> dict:
    """All checks must pass. Returns the numbers behind every check, pass or fail."""
    pred_i = (np.asarray(p_inc) >= thr_inc).astype(int)
    pred_c = (np.asarray(p_cand) >= thr_cand).astype(int)
    mi, mc = counts_metrics(y, pred_i), counts_metrics(y, pred_c)
    lo, hi = paired_bootstrap_f1_diff(
        y, pred_c, pred_i, rules["bootstrap_resamples"], rules["bootstrap_seed"],
        rules["bootstrap_ci_level"])
    checks = {
        "f1_margin": mc["f1"] >= mi["f1"] + rules["f1_margin"],
        "bootstrap_ci": lo > 0,
        "fpr_margin": mc["fpr"] <= mi["fpr"] + rules["fpr_margin"],
        "fpr_cap": mc["fpr"] <= rules["fpr_cap"],
        "recall_margin": mc["recall"] >= mi["recall"] - rules["recall_margin"],
        "feature_version": (not rules["require_feature_version_match"]) or feature_version_ok,
        "canary": (not rules["require_canary_ok"]) or canary_ok,
    }
    return {
        "promote": all(checks.values()), "checks": checks,
        "failed": [k for k, ok in checks.items() if not ok],
        "incumbent": {k: mi[k] for k in ("f1", "precision", "recall", "fpr")},
        "candidate": {k: mc[k] for k in ("f1", "precision", "recall", "fpr")},
        "f1_diff_ci": [lo, hi], "gate_rows": len(y),
    }


def canary_ok(model: LoadedModel) -> bool:
    try:
        p = model.predict_proba(CANARY_URLS)
    except Exception:  # any failure means the candidate is not servable
        return False
    return bool(len(p) == len(CANARY_URLS) and np.all(np.isfinite(p)) and p.min() >= 0
                and p.max() <= 1)


# ----------------------------------------------------------------------------- replay


@dataclass
class Batch:
    idx: int
    X: pd.DataFrame
    y: np.ndarray
    first_date: pd.Timestamp
    last_date: pd.Timestamp


def make_batches(df: pd.DataFrame, feature_names: list[str], batch_size: int) -> list[Batch]:
    """Time-ordered batches; the final batch may be shorter."""
    df = df.sort_values(["date", "sha256"], kind="stable").reset_index(drop=True)
    out = []
    for k, start in enumerate(range(0, len(df), batch_size)):
        part = df.iloc[start:start + batch_size]
        out.append(Batch(k, part[feature_names].reset_index(drop=True), part["y"].to_numpy(),
                         part["date"].iloc[0], part["date"].iloc[-1]))
    return out


def window_indices(i: int, rules: dict) -> dict | None:
    """Batch indices usable for a decision after batch i, or None if there is too little history."""
    last = i - rules["label_delay_batches"]
    g, t = rules["gate_batches"], rules["threshold_batches"]
    gate = list(range(last - g + 1, last + 1))
    thr = list(range(gate[0] - t, gate[0]))
    if not gate or not thr or thr[0] < 0:
        return None
    return {"gate": gate, "threshold": thr, "train_last": thr[0] - 1}


@dataclass
class ArmResult:
    name: str
    batches: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)


def _proba(m: LoadedModel, X: pd.DataFrame) -> np.ndarray:
    return m.model.predict_proba(X[m.feature_names])[:, 1]


def train_candidate(X: pd.DataFrame, y, feature_names, hp: dict, seed: int):
    est = RandomForestClassifier(random_state=seed, n_jobs=-1, **hp)
    est.fit(X[feature_names], y)
    return est


def run_arm(arm: dict, batches: list[Batch], base: tuple[pd.DataFrame, np.ndarray],
            v1: LoadedModel, *, rules: dict, hp: dict, seed: int, feature_names: list[str],
            drift_by_batch: list[dict], cache: dict, lifecycle: LifecycleState | None = None,
            pace: float = 0.0, journal: Path | None = None) -> ArmResult:
    res = ArmResult(arm["name"])
    st = new_arm_state(v1.metadata.get("model_version", "v1"))
    inc = v1
    n_versions = 1
    last_attempt = -10**9
    prev_month = None
    for b in batches:
        # 1. score with the model that is in production now
        p = _proba(inc, b.X)
        pred = (p >= inc.threshold).astype(int)
        m = counts_metrics(b.y, pred, p)
        d = drift_by_batch[b.idx]
        rec = {"arm": arm["name"], "batch": b.idx, "first_date": str(b.first_date.date()),
               "last_date": str(b.last_date.date()), "model_version": inc.metadata["model_version"],
               "threshold": inc.threshold, "n_drifted": d["n_drifted"],
               "max_psi": d["max_psi"], **m}
        st["batches_scored"] += 1
        st["drifted_features"], st["max_psi"] = d["n_drifted"], d["max_psi"]

        # 2. does this arm's trigger fire?
        month = (b.first_date.year, b.first_date.month)
        if arm["trigger"] == "drift":
            fired = d["n_drifted"] >= arm["min_drifted_features"]
        elif arm["trigger"] == "schedule":
            fired = prev_month is not None and month != prev_month
        else:
            fired = False
        prev_month = month
        # drift status is monitored for every arm; static/fixed arms use the primary K
        alert = d["n_drifted"] >= arm.get("min_drifted_features", PRIMARY_K)
        st["drift_alert"] = int(alert)
        st["alerts"] += int(alert)
        rec["trigger_fired"] = bool(fired)
        rec["event"] = ""

        # 3. decision (uses labels of batches <= i-D only)
        if fired:
            w = window_indices(b.idx, rules)
            if w is None:
                reason = "insufficient_history"
            elif b.idx - last_attempt < rules["cooldown_batches"]:
                reason = "cooldown"
            else:
                reason = None
            if reason:
                st["suppressed"] += 1
                rec["event"] = f"suppressed:{reason}"
                res.events.append({"arm": arm["name"], "batch": b.idx, "type": "suppressed",
                                   "reason": reason})
            else:
                last_attempt = b.idx
                st["attempts"] += 1
                ev = _attempt(arm["name"], b.idx, w, batches, base, inc, rules, hp, seed,
                              feature_names, cache, n_versions)
                st["retrain_seconds"] += ev["train_seconds"]
                res.events.append(ev)
                if ev["promote"]:
                    inc = ev.pop("_model")
                    n_versions += 1
                    st["promotions"] += 1
                    st["model_version"] = inc.metadata["model_version"]
                    rec["event"] = f"promoted:{inc.metadata['model_version']}"
                else:
                    ev.pop("_model", None)
                    for k in ev["failed"]:
                        st["rejections"][k] = st["rejections"].get(k, 0) + 1
                    rec["event"] = "rejected:" + ",".join(ev["failed"])
        res.batches.append(rec)
        if journal is not None:  # one flushed JSON line per batch survives a crash/restart
            with open(journal, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"batch_record": rec, "state": st}, default=float) + "\n")
        if lifecycle is not None:
            lifecycle.set_arm(arm["name"], dict(st))
            if pace:
                time.sleep(pace)
    res.state = st
    return res


def _attempt(arm_name, i, w, batches, base, inc, rules, hp, seed, feature_names, cache, n_versions):
    key = (w["train_last"], tuple(w["threshold"]))
    if key not in cache:
        while len(cache) >= CACHE_MAX:  # candidates are large; eviction only costs a retrain
            cache.pop(next(iter(cache)))
        t0 = time.time()
        Xs = [base[0]] + [batches[j].X for j in range(w["train_last"] + 1)]
        ys = [base[1]] + [batches[j].y for j in range(w["train_last"] + 1)]
        X, y = pd.concat(Xs, ignore_index=True), np.concatenate(ys)
        est = train_candidate(X, y, feature_names, hp, seed)
        tb = pd.concat([batches[j].X for j in w["threshold"]], ignore_index=True)
        ty = np.concatenate([batches[j].y for j in w["threshold"]])
        thr = best_threshold(ty, est.predict_proba(tb[feature_names])[:, 1])
        cache[key] = (est, thr, time.time() - t0, len(y))
        hit = False
    else:
        hit = True
    est, thr, secs, n_train = cache[key]
    version = f"{arm_name}-v{n_versions + 1}"
    cand = LoadedModel(est, list(feature_names), thr,
                       {"model_version": version, "feature_version": FEATURE_VERSION})
    gX = pd.concat([batches[j].X for j in w["gate"]], ignore_index=True)
    gy = np.concatenate([batches[j].y for j in w["gate"]])
    out = evaluate_promotion(
        gy, _proba(inc, gX), inc.threshold, _proba(cand, gX), thr, rules["promotion"],
        feature_version_ok=cand.metadata["feature_version"] == FEATURE_VERSION,
        canary_ok=canary_ok(cand))
    return {"arm": arm_name, "batch": i, "type": "attempt", "candidate_version": version,
            "candidate_threshold": thr, "incumbent_version": inc.metadata["model_version"],
            "incumbent_threshold": inc.threshold, "gate_batches": w["gate"],
            "threshold_batches": w["threshold"], "train_through_batch": w["train_last"],
            "n_train_rows": n_train, "train_seconds": secs,
            "labelled_rows_used": int(sum(len(batches[j].y) for j in range(w["gate"][-1] + 1))),
            "candidate_cache_hit": hit,
            **{k: out[k] for k in ("promote", "checks", "failed", "incumbent", "candidate",
                                   "f1_diff_ci", "gate_rows")},
            "_model": cand}


def compute_drift(batches: list[Batch], ref: Reference, cfg: DriftConfig) -> list[dict]:
    """Label-free drift statistics per batch (independent of any arm's K)."""
    out = []
    for b in batches:
        r = detect_drift(ref, b.X, dataclasses.replace(cfg, min_drifted_features=10**9))
        out.append({"n_drifted": r["n_drifted"], "max_psi": r["max_psi"],
                    "drifted_features": r["drifted_features"], "n_rows": r["n_rows"]})
    return out


def summarize(res: ArmResult) -> dict:
    df = pd.DataFrame(res.batches)
    tot = {k: int(df[k].sum()) for k in ("tp", "fp", "tn", "fn", "n")}
    pooled = counts_metrics(
        np.r_[np.ones(tot["tp"]), np.zeros(tot["fp"]), np.zeros(tot["tn"]), np.ones(tot["fn"])],
        np.r_[np.ones(tot["tp"]), np.ones(tot["fp"]), np.zeros(tot["tn"]), np.zeros(tot["fn"])])
    attempts = [e for e in res.events if e["type"] == "attempt"]
    return {
        "pooled": pooled,
        "mean_batch_f1": float(df.f1.mean()),
        "rows_scored_by_non_v1": int(df.loc[df.model_version != "v1", "n"].sum()),
        "alerts": res.state["alerts"], "attempts": len(attempts),
        "promotions": res.state["promotions"],
        "rejections": len(attempts) - res.state["promotions"],
        "rejections_by_check": res.state["rejections"], "suppressed": res.state["suppressed"],
        "replay_labels_used_rows": max([e["labelled_rows_used"] for e in attempts], default=0),
        "retrain_seconds_total": float(res.state["retrain_seconds"]),
        "final_model_version": res.state["model_version"],
    }
