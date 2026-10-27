import json
import shutil

import pytest

from adaptivephish.replay_lock import ReplayLockError, lock_hash, locked_section, verify, write_lock


@pytest.fixture
def setup(tmp_path):
    params = tmp_path / "params.yaml"
    shutil.copy("params.yaml", params)
    lock = tmp_path / "lock.json"
    write_lock(params, lock)
    return params, lock, tmp_path / "results.json"


def test_verify_ok(setup):
    params, lock, res = setup
    assert verify(params, lock, res, check_git=False) == lock_hash(locked_section(params))


def test_changed_locked_value_refuses(setup):
    params, lock, res = setup
    params.write_text(params.read_text().replace("f1_margin: 0.01", "f1_margin: 0.02"))
    with pytest.raises(ReplayLockError, match="differ"):
        verify(params, lock, res, check_git=False)


def test_changed_drift_k_refuses(setup):
    params, lock, res = setup
    text = params.read_text().replace("features: 17   #", "features: 16   #")
    params.write_text(text)
    with pytest.raises(ReplayLockError, match="differ"):
        verify(params, lock, res, check_git=False)


def test_unlocked_params_may_change(setup):
    params, lock, res = setup
    text = params.read_text().replace("cap_per_month_label: 10000", "cap_per_month_label: 5")
    params.write_text(text)
    verify(params, lock, res, check_git=False)


def test_missing_lock_refuses(setup):
    params, lock, res = setup
    lock.unlink()
    with pytest.raises(ReplayLockError, match="missing"):
        verify(params, lock, res, check_git=False)


def test_results_from_other_lock_refuse(setup):
    params, lock, res = setup
    res.write_text(json.dumps({"lock_sha256": "deadbeef"}))
    with pytest.raises(ReplayLockError, match="different lock"):
        verify(params, lock, res, check_git=False)


def test_results_from_same_lock_ok(setup):
    params, lock, res = setup
    res.write_text(json.dumps({"lock_sha256": json.loads(lock.read_text())["sha256"]}))
    verify(params, lock, res, check_git=False)
