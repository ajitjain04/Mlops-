import json

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.ensemble import RandomForestClassifier

from adaptivephish import replay
from adaptivephish.lifecycle import LifecycleCollector, LifecycleState
from adaptivephish.model_io import LoadedModel
from adaptivephish.replay import (
    Batch,
    evaluate_promotion,
    paired_bootstrap_f1_diff,
    run_arm,
    summarize,
    window_indices,
)

RULES = yaml.safe_load(open("params.yaml", encoding="utf-8"))["replay"]
PROMO = {**RULES["promotion"]}
FEATS = ["a", "b", "c"]


def test_window_indices_respect_label_delay():
    r = RULES
    assert window_indices(0, r) is None
    assert window_indices(2, r) is None  # threshold batch would be -1
    w = window_indices(3, r)
    # after batch 3: labelled <= 2, gate = (1, 2), threshold batch = 0, nothing older to train on
    assert w == {"gate": [1, 2], "threshold": [0], "train_last": -1}
    w = window_indices(9, r)
    assert w == {"gate": [7, 8], "threshold": [6], "train_last": 5}
    assert max(w["gate"]) <= 9 - r["label_delay_batches"]


def _rules():
    return {**PROMO, "bootstrap_resamples": 200}


def test_identical_model_is_rejected():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 1000)
    p = np.clip(y * 0.6 + rng.normal(0.2, 0.2, 1000), 0, 1)
    out = evaluate_promotion(y, p, 0.5, p, 0.5, _rules(), feature_version_ok=True, canary_ok=True)
    assert not out["promote"]
    assert "f1_margin" in out["failed"] and "bootstrap_ci" in out["failed"]


def test_clear_improvement_is_promoted_and_each_check_can_block():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 3000)
    weak = np.clip(y * 0.25 + rng.normal(0.4, 0.25, 3000), 0, 1)
    strong = np.clip(y * 0.8 + rng.normal(0.1, 0.1, 3000), 0, 1)
    ok = evaluate_promotion(y, weak, 0.5, strong, 0.5, _rules(), feature_version_ok=True,
                            canary_ok=True)
    assert ok["promote"], ok
    bad_canary = evaluate_promotion(y, weak, 0.5, strong, 0.5, _rules(), feature_version_ok=True,
                                    canary_ok=False)
    assert not bad_canary["promote"] and bad_canary["failed"] == ["canary"]
    bad_version = evaluate_promotion(y, weak, 0.5, strong, 0.5, _rules(), feature_version_ok=False,
                                     canary_ok=True)
    assert bad_version["failed"] == ["feature_version"]
    # a candidate that flags everything: great recall, FPR above the cap
    flag_all = evaluate_promotion(y, weak, 0.5, np.ones(3000), 0.5, _rules(),
                                  feature_version_ok=True, canary_ok=True)
    assert "fpr_cap" in flag_all["failed"] and not flag_all["promote"]


def test_paired_bootstrap_interval_orders():
    y = np.array([1, 0] * 500)
    good, bad = y.copy(), 1 - y
    lo, hi = paired_bootstrap_f1_diff(y, good, bad, 200, 42, 0.95)
    assert 0 < lo <= hi


# --- arm logic on a synthetic stream with a concept change ---------------------------------------


def _stream(concept_flip_at: int | None, n_batches=12, size=400, seed=0, base_n=1500):
    rng = np.random.default_rng(seed)

    def draw(n, flipped):
        X = pd.DataFrame(rng.normal(size=(n, 3)), columns=FEATS)
        y = ((X["b"] if flipped else X["a"]) + rng.normal(0, 0.2, n) > 0).astype(int).to_numpy()
        return X, y

    base_X, base_y = draw(base_n, False)
    batches = []
    for k in range(n_batches):
        flipped = concept_flip_at is not None and k >= concept_flip_at
        X, y = draw(size, flipped)
        d = pd.Timestamp("2025-09-01") + pd.Timedelta(days=3 * k)
        batches.append(Batch(k, X, y, d, d))
    return (base_X, base_y), batches


@pytest.fixture
def v1_and_hp(monkeypatch):
    monkeypatch.setattr(replay, "canary_ok", lambda m: True)
    hp = {"n_estimators": 30, "max_depth": None, "min_samples_leaf": 1}
    return hp


def _v1(base, hp):
    est = RandomForestClassifier(random_state=42, **hp).fit(base[0][FEATS], base[1])
    return LoadedModel(est, FEATS, 0.5, {"model_version": "v1", "feature_version": "1.0.0"})


def _run(arm, base, batches, hp, drift_flags, tmp_path=None):
    drift = [{"n_drifted": 20 if f else 0, "max_psi": 0.5 if f else 0.0} for f in drift_flags]
    life = LifecycleState(tmp_path / "state.json") if tmp_path else None
    return run_arm(arm, batches, base, _v1(base, hp), rules=RULES, hp=hp, seed=42,
                   feature_names=FEATS, drift_by_batch=drift, cache={}, lifecycle=life)


def test_static_arm_never_changes_model(v1_and_hp):
    base, batches = _stream(concept_flip_at=4)
    arm = {"name": "static_v1", "trigger": "none"}
    res = _run(arm, base, batches, v1_and_hp, [True] * 12)
    assert {b["model_version"] for b in res.batches} == {"v1"}
    assert res.state["attempts"] == 0 and res.state["promotions"] == 0


def test_adaptive_arm_promotes_after_concept_flip_and_uses_it_next_batch(v1_and_hp, tmp_path):
    # old concept is only a small base; the stream has the new concept from the start
    base, batches = _stream(concept_flip_at=0, base_n=300)
    arm = {"name": "adaptive_primary", "trigger": "drift", "min_drifted_features": 17}
    res = _run(arm, base, batches, v1_and_hp, [True] * 12, tmp_path)
    promos = [e for e in res.events if e["type"] == "attempt" and e["promote"]]
    assert promos, res.events
    first = promos[0]["batch"]
    by_batch = {b["batch"]: b["model_version"] for b in res.batches}
    assert by_batch[first] == "v1"  # promotion at batch i takes effect from i+1
    assert by_batch[first + 1] == promos[0]["candidate_version"]
    # labels: gate and threshold batches never reach beyond i - D
    for e in res.events:
        if e["type"] == "attempt":
            assert max(e["gate_batches"]) <= e["batch"] - RULES["label_delay_batches"]
            assert e["train_through_batch"] < min(e["threshold_batches"])
    st = json.loads((tmp_path / "state.json").read_text())["arms"]["adaptive_primary"]
    assert st["promotions"] == len(promos) and st["attempts"] == res.state["attempts"]


def test_cooldown_suppresses_attempts_within_three_batches(v1_and_hp):
    base, batches = _stream(concept_flip_at=None)
    arm = {"name": "adaptive_sensitivity", "trigger": "drift", "min_drifted_features": 10}
    res = _run(arm, base, batches, v1_and_hp, [True] * 12)
    att = [e["batch"] for e in res.events if e["type"] == "attempt"]
    assert all(b - a >= RULES["cooldown_batches"] for a, b in zip(att, att[1:], strict=False))
    assert res.state["suppressed"] > 0
    reasons = {e["reason"] for e in res.events if e["type"] == "suppressed"}
    assert reasons == {"insufficient_history", "cooldown"}


def test_no_improvement_means_rejection_and_incumbent_untouched(v1_and_hp):
    base, batches = _stream(concept_flip_at=None)  # same concept throughout: nothing to gain
    arm = {"name": "adaptive_primary", "trigger": "drift", "min_drifted_features": 17}
    res = _run(arm, base, batches, v1_and_hp, [True] * 12)
    assert res.state["attempts"] > 0 and res.state["promotions"] == 0
    assert {b["model_version"] for b in res.batches} == {"v1"}
    assert sum(res.state["rejections"].values()) >= res.state["attempts"]
    s = summarize(res)
    assert s["promotions"] == 0 and s["rejections"] == s["attempts"]


def test_fixed_schedule_fires_once_at_month_boundary(v1_and_hp):
    base, batches = _stream(concept_flip_at=None, n_batches=14)  # 3-day batches cross into October
    months = [(b.first_date.month) for b in batches]
    assert 9 in months and 10 in months
    arm = {"name": "fixed_monthly", "trigger": "schedule", "period": "monthly"}
    res = _run(arm, base, batches, v1_and_hp, [False] * 14)
    fired = [b["batch"] for b in res.batches if b["trigger_fired"]]
    assert fired == [months.index(10)]


def test_lifecycle_collector_exports_counters(tmp_path):
    st = LifecycleState(tmp_path / "s.json")
    from adaptivephish.lifecycle import new_arm_state

    s = new_arm_state("v1")
    s.update(promotions=2, attempts=5, rejections={"f1_margin": 3}, drift_alert=1)
    st.set_arm("adaptive_primary", s)
    from prometheus_client import CollectorRegistry, generate_latest

    reg = CollectorRegistry()
    reg.register(LifecycleCollector(tmp_path / "s.json"))
    text = generate_latest(reg).decode()
    assert 'adaptivephish_promotions_total{arm="adaptive_primary"} 2.0' in text
    assert 'adaptivephish_rejections_total{arm="adaptive_primary",reason="f1_margin"} 3.0' in text
    assert 'adaptivephish_drift_status{arm="adaptive_primary"} 1.0' in text
    reg2 = CollectorRegistry()
    reg2.register(LifecycleCollector(tmp_path / "missing.json"))
    assert "adaptivephish_lifecycle_state_ok 0.0" in generate_latest(reg2).decode()
    reg3 = CollectorRegistry()
    reg3.register(LifecycleCollector(None))
    assert generate_latest(reg3).decode() == ""


def test_state_write_survives_locked_file(tmp_path, monkeypatch):
    import os

    from adaptivephish.lifecycle import new_arm_state

    def locked(*a, **k):
        raise PermissionError("file in use")

    monkeypatch.setattr(os, "replace", locked)
    monkeypatch.setattr("time.sleep", lambda s: None)
    st = LifecycleState(tmp_path / "s.json")
    st.set_arm("a", new_arm_state("v1"))  # must not raise
    assert json.loads((tmp_path / "s.json").read_text())["arms"]["a"]["model_version"] == "v1"
