"""Lock for the pre-registered M11 replay design.

The replay design, promotion criteria and drift rule are fixed in params.yaml before any
test-period replay. The canonical hash of those sections is stored in
reports/results/replay_lock.json. The replay calls `verify()` first and refuses to run if the
locked values changed, or if results already exist that were produced under a different lock.
Deviations must be made openly, as a new documented lock, never silently.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

LOCK_PATH = Path("reports/results/replay_lock.json")
RESULTS_PATH = Path("reports/results/replay_results.json")


class ReplayLockError(RuntimeError):
    pass


def locked_section(params_path: str | Path = "params.yaml") -> dict:
    with open(params_path, encoding="utf-8") as f:
        p = yaml.safe_load(f)
    return {"replay": p["replay"], "drift_locked": p["drift"]["locked"]}


def lock_hash(section: dict) -> str:
    blob = json.dumps(section, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def write_lock(params_path="params.yaml", lock_path=LOCK_PATH, locked_at: str = "") -> dict:
    section = locked_section(params_path)
    lock = {"locked_at": locked_at, "sha256": lock_hash(section), "section": section}
    Path(lock_path).write_text(json.dumps(lock, indent=2, sort_keys=True), encoding="utf-8")
    return lock


def _committed_unchanged(path: Path) -> bool | None:
    """True/False if inside a git repo (file equals HEAD), None if git is unavailable."""
    try:
        r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], capture_output=True)
    except OSError:
        return None
    return r.returncode == 0 if r.returncode in (0, 1) else None


def verify(params_path="params.yaml", lock_path=LOCK_PATH, results_path=RESULTS_PATH,
           check_git: bool = True) -> str:
    """Return the lock hash, or raise ReplayLockError."""
    lock_path, results_path = Path(lock_path), Path(results_path)
    if not lock_path.exists():
        raise ReplayLockError(f"{lock_path} missing: the design must be locked and committed first")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    current = lock_hash(locked_section(params_path))
    if current != lock["sha256"]:
        raise ReplayLockError(
            f"locked replay/drift values in {params_path} differ from {lock_path} "
            f"({current[:12]} != {lock['sha256'][:12]}); refusing to run. A change after the "
            "design was fixed must be reported as a deviation, not applied silently.")
    if check_git and _committed_unchanged(lock_path) is False:
        raise ReplayLockError(f"{lock_path} has uncommitted changes; it must match the commit")
    if results_path.exists():
        res = json.loads(results_path.read_text(encoding="utf-8"))
        if res.get("lock_sha256") != lock["sha256"]:
            raise ReplayLockError(
                f"{results_path} exists from a different lock "
                f"({str(res.get('lock_sha256'))[:12]}); refusing to overwrite or mix results")
    return current
