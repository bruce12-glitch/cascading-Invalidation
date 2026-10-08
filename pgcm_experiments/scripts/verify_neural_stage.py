"""Fail-closed validation of a completed per-trace embedding directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from pgcm.dataset import load_traces


KEYS = {"record_ids", "record_vectors", "query_ids", "query_vectors", "embedding_name"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--vectors-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    dataset, vectors_dir = Path(args.dataset), Path(args.vectors_dir)
    manifest = json.loads((vectors_dir / "embedding_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise RuntimeError("embedding manifest is not completed")
    if digest(dataset) != manifest.get("dataset_sha256"):
        raise ValueError("dataset digest differs from embedding manifest")
    names, dimensions, files, seen = set(), set(), [], set()
    traces = 0
    for trace in load_traces(dataset):
        traces += 1
        seen.add(trace["trace_id"])
        path = vectors_dir / f"{trace['trace_id']}.npz"
        if not path.is_file():
            raise FileNotFoundError(path)
        expected_records = [node["id"] for node in trace["graph"]["nodes"]]
        expected_queries = [item["query"]["id"] for item in trace["queries"]]
        with np.load(path, allow_pickle=False) as data:
            if set(data.files) != KEYS:
                raise ValueError(f"{path}: unexpected keys")
            if list(map(str, data["record_ids"])) != expected_records:
                raise ValueError(f"{path}: record ordering mismatch")
            if list(map(str, data["query_ids"])) != expected_queries:
                raise ValueError(f"{path}: query ordering mismatch")
            rv, qv = data["record_vectors"], data["query_vectors"]
            if rv.shape[0] != len(expected_records) or qv.shape[0] != len(expected_queries):
                raise ValueError(f"{path}: row count mismatch")
            if rv.ndim != 2 or qv.ndim != 2 or rv.shape[1] != qv.shape[1]:
                raise ValueError(f"{path}: dimension mismatch")
            if not np.isfinite(rv).all() or not np.isfinite(qv).all():
                raise ValueError(f"{path}: non-finite vectors")
            names.add(str(data["embedding_name"].item()))
            dimensions.add(int(rv.shape[1]))
        files.append({"trace_id": trace["trace_id"], "sha256": digest(path)})
    extra = sorted(path.name for path in vectors_dir.glob("*.npz") if path.stem not in seen)
    if extra or len(names) != 1 or len(dimensions) != 1:
        raise ValueError(f"inconsistent embedding bundle: extra={extra}, names={names}, dimensions={dimensions}")
    report = {
        "status": "passed",
        "dataset_sha256": digest(dataset),
        "trace_count": traces,
        "embedding_name": next(iter(names)),
        "dimension": next(iter(dimensions)),
        "npz_files": files,
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "npz_files"}, indent=2))


if __name__ == "__main__":
    main()
