# M11 replay report: static vs adaptive (test period, Sep-Oct 2025)

Produced by `python scripts/run_replay.py --mode test` at commit 652b217 under the locked design
(`reports/results/replay_lock.json`, sha256 `3127dc13...`; criteria in PROGRESS.md and `params.yaml`
`replay`). Raw numbers: `replay_results.json` (per-arm summaries, every retrain attempt with its gate
numbers and failed checks) and `replay_batches.csv` (per-batch, per-arm metrics). Figure:
`reports/figures/replay_timeline.png`. The test period was read once, by this run. No threshold, K,
criterion or arm was changed before or after seeing these results. Before this run I ran the same code
in a validation-only dry run (`--mode dryrun`, no test rows) to debug it; the criteria were not touched
after that either.

Setup: 37,501 test rows in 19 batches of 2,000 (last batch 1,501), 2025-09-01 to 2025-10-31. Base
training data 51,485 rows (train + validation). V1 threshold 0.1833. Label delay D=1, gate set = 2
batches, cooldown 3 batches.

## Results

| arm | alerts (K) | attempts | promoted | rejected | suppressed | pooled F1 | recall | FPR | rows scored by non-V1 |
|---|---|---|---|---|---|---|---|---|---|
| static_v1 | 0 (K=17) | 0 | 0 | 0 | 0 | 0.8377 | 0.8915 | 0.2073 | 0 |
| adaptive_primary (K=17) | 0 | 0 | 0 | 0 | 0 | 0.8377 | 0.8915 | 0.2073 | 0 |
| adaptive_sensitivity (K=10) | 4 | 3 | 0 | 3 | 1 (cooldown) | 0.8377 | 0.8915 | 0.2073 | 0 |
| fixed_monthly | n/a | 1 | 1 | 0 | 0 | 0.8400 | 0.8969 | 0.2087 | 17,501 |

(Pooled over all test rows; mean per-batch F1 0.786 for the first three arms, 0.788 for fixed_monthly.
The static pooled F1 0.8377 matches the V1 test F1 from M5, which is a consistency check on the replay.)

**Headline: drift-triggered adaptation did not help in this replay, and the only arm that changed the
model gained 0.002 pooled F1.**

- **adaptive_primary never alerted.** The largest drifted-feature count in any batch was 15 of 20
  (K=17 needed), so it behaved exactly like static V1. K=17 was calibrated to be conservative (0/10
  validation alerts), and on this stream it was silent.
- **adaptive_sensitivity (K=10)** alerted on 4 batches (5, 13, 14 [suppressed by cooldown], 18) and made
  3 attempts, all rejected:
  - batch 5: candidate F1 0.687 vs incumbent 0.689, no gain (failed f1_margin, bootstrap_ci, recall_margin);
  - batch 13: candidate F1 0.858 vs 0.833, bootstrap interval of the F1 difference [0.008, 0.042] above 0,
    FPR 0.018 vs 0.197, but recall 0.774 vs 0.944 (a 0.17 drop against the 0.02 allowed), so it failed
    **only** `recall_margin`;
  - batch 18: candidate worse than the incumbent (F1 0.920 vs 0.936, interval [-0.025, -0.008]).
  Incumbent V1 stayed in production, as required.
- **fixed_monthly** made its single attempt at batch 9 (first batch of October; with a two-month window the
  monthly schedule has only one boundary). The candidate passed all checks (gate F1 0.755 vs 0.701,
  interval [0.041, 0.069], recall 0.878 vs 0.776, FPR 0.205 vs 0.201) and V2 served batches 10-18. On those
  9 batches V2 had a higher F1 than V1 in 9 of 9 (differences 0.000 to 0.013), pooled 0.9095 vs 0.9058,
  recall 0.976 vs 0.966, FPR 0.214 vs 0.210. The effect is small, from one retrain, one seed and one replay;
  I would not call it conclusive.

## What the replay shows about drift and performance

- Per-batch F1 swings from 0.40 to 0.97 for every arm, and it tracks the **phishing share of the batch**
  (correlation 0.91 with static F1): the batches with 8-11% phishing (batches 9-10, early October) have the
  worst F1, the batches with 60-90% phishing (late October) the best. F1 is prevalence-sensitive, and the
  dataset's class/date confounding (known from M2) shows up here. Absolute per-batch F1 is therefore not a
  clean measure of drift damage; the arms are compared on identical batches, which is fair.
- **The drifted-feature count is nearly unrelated to F1** (correlation 0.17). The worst F1 trough (batches
  9-10) had only 7-8 drifted features; the highest counts (15 and 14, batches 14 and 18) came with the best F1.
  This supports "a drift alert means investigate, not accuracy loss", and shows the K rule does not predict
  the performance dips seen here.
- Most of the stream's drift is class-mix-driven (consistent with M6), so a label-free feature rule mostly
  reflects the mix of benign and phishing URLs.

## Design observations (reported, not acted on)

- The promotion rule is strict on recall: V1 sits at a high-recall, high-FPR operating point (FPR ~0.21),
  and a candidate that cuts FPR sharply by giving up recall fails `recall_margin` even when its F1
  improvement is significant (batch 13). Whether that is the right policy is a product decision. The
  criteria were locked and approved before the run; a revision would be a new, separately reported design,
  not a change to this result.
- 19 batches and at most 3 attempts per arm is a small sample. Differences of a few thousandths in pooled
  F1 are within what a different seed or batch boundary could change.
- The gate set comes from the replay's own recent batches, with a one-batch label delay; it is one replay of
  one dataset with one seed. Labels are assumed to arrive exactly one batch late, which is optimistic for real
  phishing labelling.
- The fixed-schedule baseline has one decision point because the test window spans two months.

## Cost

Retraining took 10.8 s (3 candidates, sensitivity arm) and 3.3 s (1 candidate, fixed arm) of compute on
this machine; labels consumed by the last attempt: 36,000 replay rows (sensitivity), 18,000 (fixed).
