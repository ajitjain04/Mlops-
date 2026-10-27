"""Write reports/results/replay_lock.json from params.yaml (run once, then commit)."""

import sys

from adaptivephish.replay_lock import LOCK_PATH, write_lock

if LOCK_PATH.exists() and "--force" not in sys.argv:
    sys.exit(f"{LOCK_PATH} exists; refusing to overwrite "
             "(a re-lock is a deviation and must be documented)")
print(write_lock(locked_at="2026-10-27")["sha256"])
