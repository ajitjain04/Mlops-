"""Lifecycle state (drift status, retraining and promotion counters) shared with the API's /metrics.

The replay writes a small JSON file after every batch; the API reads it at scrape time through a
custom Prometheus collector (`LifecycleCollector`). Without a state file nothing is exported, so
dashboards never show invented zeros.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

log = logging.getLogger("adaptivephish.lifecycle")

LIFECYCLE_ENV = "ADAPTIVEPHISH_LIFECYCLE"

COUNTER_FIELDS = ("alerts", "attempts", "promotions", "suppressed", "batches_scored")


def new_arm_state(model_version: str) -> dict:
    return {
        "model_version": model_version, "drift_alert": 0, "drifted_features": 0, "max_psi": 0.0,
        "alerts": 0, "attempts": 0, "promotions": 0, "suppressed": 0, "batches_scored": 0,
        "rejections": {}, "retrain_seconds": 0.0,
    }


class LifecycleState:
    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None
        self.arms: dict[str, dict] = {}

    def set_arm(self, arm: str, state: dict) -> None:
        self.arms[arm] = state
        self.flush()

    def flush(self) -> None:
        if self.path is None:
            return
        # Exported metrics must never break the replay. On Windows the rename fails while a
        # bind-mounted container holds the file open, so retry, then fall back to a direct
        # (non-atomic) write; a scrape that catches a partial file reports lifecycle_state_ok 0
        # and the next scrape recovers.
        payload = json.dumps({"updated_at": time.time(), "arms": self.arms})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(payload, encoding="utf-8")
            for _ in range(5):
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError:
                    time.sleep(0.1)
            self.path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            log.warning("could not write lifecycle state: %s", exc)


class LifecycleCollector:
    """Prometheus collector reading the state file on every scrape."""

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def collect(self):
        if self.path is None:
            return
        ok = GaugeMetricFamily("adaptivephish_lifecycle_state_ok",
                               "1 if the lifecycle state file was read")
        try:
            arms = json.loads(self.path.read_text(encoding="utf-8"))["arms"]
        except (OSError, ValueError, KeyError):
            ok.add_metric([], 0)
            yield ok
            return
        ok.add_metric([], 1)
        yield ok

        def counter(name, doc, key):
            m = CounterMetricFamily(name, doc, labels=["arm"])
            for arm, s in arms.items():
                m.add_metric([arm], s.get(key, 0))
            return m

        yield counter("adaptivephish_drift_alerts", "Batches whose drift rule alerted", "alerts")
        yield counter("adaptivephish_retrain_attempts", "Candidate retraining attempts", "attempts")
        yield counter("adaptivephish_promotions", "Candidates promoted to production", "promotions")
        yield counter("adaptivephish_retrain_suppressed",
                      "Triggers suppressed by cooldown or too little labelled history",
                      "suppressed")
        yield counter("adaptivephish_replay_batches_scored", "Batches scored in the replay",
                      "batches_scored")
        rej = CounterMetricFamily("adaptivephish_rejections",
                                  "Candidates rejected, by failed check",
                                  labels=["arm", "reason"])
        status = GaugeMetricFamily("adaptivephish_drift_status",
                                   "1 if the latest batch alerted under the arm's drift rule",
                                   labels=["arm"])
        nfeat = GaugeMetricFamily("adaptivephish_drifted_features",
                                  "Features flagged as drifted in the latest batch", labels=["arm"])
        psi = GaugeMetricFamily("adaptivephish_drift_max_psi",
                                "Largest per-feature PSI in the latest batch", labels=["arm"])
        info = GaugeMetricFamily("adaptivephish_arm_model_version",
                                 "Model version in production for the arm",
                                 labels=["arm", "model_version"])
        for arm, s in arms.items():
            for reason, n in s.get("rejections", {}).items():
                rej.add_metric([arm, reason], n)
            status.add_metric([arm], s.get("drift_alert", 0))
            nfeat.add_metric([arm], s.get("drifted_features", 0))
            psi.add_metric([arm], s.get("max_psi", 0.0))
            info.add_metric([arm, s.get("model_version", "unknown")], 1)
        yield from (rej, status, nfeat, psi, info)
