"""Embed a trimmed copy of reports/results/replay_results.json into the frontend page.

The page is self-contained (no fetch of the results file), so the numbers are copied in here.
Run after a new replay; tests/test_frontend.py fails if the embedded copy is out of sync.
"""

import json
import re
from pathlib import Path

PAGE = Path("src/adaptivephish/api/static/index.html")
RESULTS = Path("reports/results/replay_results.json")

ARMS = [
    ("static_v1", "Static V1"),
    ("adaptive_primary", "Adaptive, K=17 (primary)"),
    ("adaptive_sensitivity", "Adaptive, K=10 (sensitivity)"),
    ("fixed_monthly", "Fixed monthly retrain"),
]


def trimmed(res: dict) -> dict:
    arms = []
    for key, label in ARMS:
        s = res["arms"][key]["summary"]
        scheduled = res["arms"][key]["arm"]["trigger"] == "schedule"
        arms.append({
            "id": key, "label": label, "alerts": None if scheduled else s["alerts"],
            "attempts": s["attempts"], "promotions": s["promotions"],
            "f1": round(s["pooled"]["f1"], 4),
        })
    n = res["arms"]["static_v1"]["summary"]["pooled"]["n"]
    return {
        "source": "reports/results/replay_results.json", "stream_window": res["stream_window"],
        "n_batches": res["n_batches"], "rows": n, "arms": arms,
        "notes": [
            "Pooled F1 over all replayed URLs; one seed, one replay, 19 batches.",
            "The K=17 rule never alerted, so that arm behaved exactly like static V1.",
            "K=10 made 3 retrain attempts; all were rejected by the fixed promotion checks.",
            "The monthly schedule promoted one candidate: +0.002 pooled F1, not conclusive.",
        ],
    }


def main() -> None:
    data = trimmed(json.loads(RESULTS.read_text(encoding="utf-8")))
    text = PAGE.read_text(encoding="utf-8")
    block = "\n".join([
        "<!--REPLAY-DATA-START-->",
        '<script type="application/json" id="replay-data">',
        json.dumps(data, indent=2),
        "</script>",
        "<!--REPLAY-DATA-END-->",
    ])
    new = re.sub(r"<!--REPLAY-DATA-START-->.*?<!--REPLAY-DATA-END-->", lambda m: block, text,
                 flags=re.S)
    PAGE.write_text(new, encoding="utf-8", newline="\n")
    print("embedded", [a["id"] for a in data["arms"]])


if __name__ == "__main__":
    main()
