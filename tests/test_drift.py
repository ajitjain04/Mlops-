import numpy as np
import pandas as pd
import pytest

from adaptivephish.drift import DriftConfig, build_reference, detect_drift, psi

FEATS = ["len_a", "count_b", "ratio_c", "flag_d", "rare_e"]


def make(n, seed, shift=False):
    rng = np.random.default_rng(seed)
    scale = 1.6 if shift else 1.0
    return pd.DataFrame({
        "len_a": rng.gamma(4.0, 10.0 * scale, n),
        "count_b": rng.poisson(3 * scale, n).astype(float),
        "ratio_c": rng.beta(2, 5 if not shift else 2, n),
        "flag_d": (rng.random(n) < (0.2 if not shift else 0.5)).astype(float),
        "rare_e": (rng.random(n) < 0.001).astype(float),
    })


CFG = DriftConfig(min_drifted_features=2)


def test_rare_and_constant_features_are_skipped():
    ref = build_reference(make(20000, 0), FEATS, CFG)
    assert "rare_e" in ref.skipped and "rare_e" not in ref.tested
    assert ref.tested == ["len_a", "count_b", "ratio_c", "flag_d"]
    assert ref.binary == {"flag_d"}


def test_same_distribution_does_not_alert():
    ref = build_reference(make(20000, 0), FEATS, CFG)
    for seed in range(1, 6):
        out = detect_drift(ref, make(2000, seed), CFG)
        assert out["n_drifted"] == 0 and not out["alert"]


def test_shifted_distribution_alerts_and_names_features():
    ref = build_reference(make(20000, 0), FEATS, CFG)
    out = detect_drift(ref, make(2000, 9, shift=True), CFG)
    assert out["alert"] and out["n_drifted"] >= 3
    assert {"len_a", "flag_d"} <= set(out["drifted_features"])


def test_partial_shift_below_threshold_does_not_alert():
    ref = build_reference(make(20000, 0), FEATS, DriftConfig(min_drifted_features=3))
    b = make(2000, 3)
    b["len_a"] = b["len_a"] * 1.6  # only one feature moves
    out = detect_drift(ref, b, DriftConfig(min_drifted_features=3))
    assert out["n_drifted"] == 1 and not out["alert"]


def test_tiny_shift_is_significant_but_below_psi_floor():
    ref = build_reference(make(40000, 0), FEATS, CFG)
    b = make(40000, 4)
    b["len_a"] = b["len_a"] * 1.02
    out = detect_drift(ref, b, CFG)
    row = out["table"].loc["len_a"]
    assert row.p_value < 0.05 / 4 and row.psi < 0.1 and not row.drifted


def test_decision_ignores_labels():
    ref = build_reference(make(20000, 0), FEATS, CFG)
    b = make(2000, 5, shift=True)
    a = detect_drift(ref, b, CFG)
    b["y"] = 1
    assert detect_drift(ref, b, CFG)["drifted_features"] == a["drifted_features"]


def test_psi_zero_for_identical_and_positive_for_shift():
    x = np.random.default_rng(0).normal(size=5000)
    edges = np.quantile(x, np.linspace(0, 1, 11)[1:-1])
    assert psi(x, x, edges) == pytest.approx(0, abs=1e-9)
    assert psi(x, x + 1.0, edges) > 0.25
