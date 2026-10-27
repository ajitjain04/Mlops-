"""Static vs adaptive replay (M11).

  python scripts/run_replay.py --mode dryrun   # debug on the VALIDATION period; no test rows read
  python scripts/run_replay.py --mode test     # the one official replay on the test period

Both modes first call replay_lock.verify(): it refuses to run if the locked design in params.yaml
changed, if the lock file has uncommitted edits, or if results from a different lock exist.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import yaml

from adaptivephish.drift import load_reference
from adaptivephish.lifecycle import LifecycleState
from adaptivephish.model_io import load_production
from adaptivephish.replay import compute_drift, make_batches, run_arm, summarize
from adaptivephish.replay_lock import RESULTS_PATH, verify

FEATURES = "data/processed/features.parquet"


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dryrun", "test"], required=True)
    ap.add_argument("--state-file", default="artifacts/lifecycle/state.json")
    ap.add_argument("--journal", default="artifacts/replay_journal.jsonl")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds to sleep after each batch")
    args = ap.parse_args()

    params = yaml.safe_load(open("params.yaml", encoding="utf-8"))
    rules = params["replay"]
    lock_hash = verify()  # refuses on any locked-value change (both modes)
    production = load_production()
    names = production.feature_names
    hp = production.metadata["hyperparameters"]
    seed = params["train"]["seed"]

    if args.mode == "test":
        base_roles, stream_role = ["train", "val"], "test"
        out_json, out_csv = RESULTS_PATH, Path("reports/results/replay_batches.csv")
    else:
        base_roles, stream_role = ["train"], "val"
        out_dir = Path("artifacts/replay_dryrun")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_json, out_csv = out_dir / "replay_results.json", out_dir / "replay_batches.csv"

    cols = ["sha256", "date", "role", "y", *names]
    wanted = [*base_roles, stream_role]
    # read only the rows this mode may use (a dry run never touches the test period)
    df = pd.read_parquet(FEATURES, columns=cols, filters=[("role", "in", wanted)])
    assert set(df.role.unique()) == set(wanted), df.role.unique()
    if args.mode == "dryrun":
        assert "test" not in set(df.role)
    base_df = df[df.role.isin(base_roles)]
    base = (base_df[names].reset_index(drop=True), base_df["y"].to_numpy())
    batches = make_batches(df[df.role == stream_role], names, rules["batch_size"])
    print(f"mode={args.mode} base_rows={len(base[1])} stream_rows="
          f"{sum(len(b.y) for b in batches)} batches={len(batches)}")

    ref, drift_cfg = load_reference()
    drift = compute_drift(batches, ref, drift_cfg)
    lifecycle = LifecycleState(args.state_file)
    journal = Path(args.journal)
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")  # fresh journal per run (results are deterministic)
    cache: dict = {}
    results, all_batches = {}, []
    t0 = time.time()
    arms = list(rules["arms"])
    if args.mode == "dryrun":  # exercises training/gating on real features; never official
        arms.append({"name": "dryrun_k1", "trigger": "drift", "min_drifted_features": 1})
    for arm in arms:
        res = run_arm(arm, batches, base, production, rules=rules, hp=hp, seed=seed,
                      feature_names=names, drift_by_batch=drift, cache=cache,
                      lifecycle=lifecycle, pace=args.pace, journal=journal)
        results[arm["name"]] = {"arm": arm, "summary": summarize(res), "events": res.events}
        all_batches += res.batches
        print(arm["name"], json.dumps(results[arm["name"]]["summary"], default=float)[:400])

    out = {
        "lock_sha256": lock_hash, "mode": args.mode, "git_commit": git_commit(),
        "v1_threshold": production.threshold, "n_batches": len(batches),
        "batch_size": rules["batch_size"], "base_rows": len(base[1]),
        "stream_window": [str(batches[0].first_date.date()), str(batches[-1].last_date.date())],
        "drift_per_batch": [{k: d[k] for k in ("n_drifted", "max_psi")} for d in drift],
        "arms": results, "wall_seconds": time.time() - t0,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    Path(out_json).write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    pd.DataFrame(all_batches).to_csv(out_csv, index=False)
    print("wrote", out_json, out_csv)


if __name__ == "__main__":
    main()
