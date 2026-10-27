"""Fetch URL-level metadata (no HTML) for every PhreshPhish parquet shard.

Uses parquet column projection over HfFileSystem range reads, so only the small
columns are transferred. Output: data/interim/phreshphish_meta.parquet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfApi, HfFileSystem

REPO = "phreshphish/phreshphish"
COLUMNS = ["sha256", "url", "label", "target", "date", "lang", "lang_score"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/interim/phreshphish_meta.parquet")
    args = ap.parse_args()

    info = HfApi().dataset_info(REPO)
    print(f"revision={info.sha} lastModified={info.last_modified}")
    shards = sorted(
        s.rfilename for s in info.siblings if s.rfilename.startswith("data/")
    )
    fs = HfFileSystem()
    tables = []
    for i, name in enumerate(shards, 1):
        split = "train" if "/train-" in name else "test"
        with fs.open(f"datasets/{REPO}/{name}", "rb") as f:
            t = pq.ParquetFile(f).read(columns=COLUMNS)
        t = t.append_column("split", pa.array([split] * t.num_rows))
        t = t.append_column("shard", pa.array([name] * t.num_rows))
        tables.append(t)
        print(f"[{i}/{len(shards)}] {name} rows={t.num_rows}", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.concat_tables(tables), out, compression="zstd")
    print(f"wrote {out} revision={info.sha}")


if __name__ == "__main__":
    main()
