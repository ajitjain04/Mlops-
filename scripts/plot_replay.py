"""Figure for the M11 replay (reads reports/results/replay_batches.csv and replay_results.json)."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

df = pd.read_csv("reports/results/replay_batches.csv")
res = json.load(open("reports/results/replay_results.json", encoding="utf-8"))
nd = [d["n_drifted"] for d in res["drift_per_batch"]]
s = df[df.arm == "static_v1"].set_index("batch")
phish = (s.tp + s.fn) / s.n
fig, ax = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
for arm, style in [("static_v1", "-"), ("fixed_monthly", "--"), ("adaptive_sensitivity", ":")]:
    d = df[df.arm == arm]
    ax[0].plot(d.batch, d.f1, style, label=arm, lw=2)
ax[0].set_ylabel("batch F1")
ax[0].legend()
ax[0].set_title("Test-period replay, 2,000-row batches (identical arms overlap)")
ax[1].bar(s.index, phish, color="#888")
ax[1].set_ylabel("phishing share of batch")
ax[2].bar(s.index, nd, color="#c55")
ax[2].axhline(17, color="k", ls="--", label="K=17 (primary)")
ax[2].axhline(10, color="gray", ls=":", label="K=10 (sensitivity)")
ax[2].set_ylabel("drifted features (of 20)")
ax[2].set_xlabel("batch")
ax[2].legend()
plt.tight_layout()
plt.savefig("reports/figures/replay_timeline.png", dpi=130)
f1 = s.f1.reset_index(drop=True)
print("corr(n_drifted, static F1) =", round(float(pd.Series(nd).corr(f1)), 3))
print("corr(phish share, static F1) =", round(float(phish.reset_index(drop=True).corr(f1)), 3))
