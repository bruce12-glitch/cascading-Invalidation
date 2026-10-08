"""Build auditable, resumable SentenceTransformer embeddings per trace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from pgcm.dataset import load_traces


BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
NPZ_KEYS = {"record_ids", "record_vectors", "query_ids", "query_vectors", "embedding_name"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_device(requested: str, torch_module) -> str:
    if requested != "auto":
        if requested.startswith("cuda") and not torch_module.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        return requested
    return "cuda" if torch_module.cuda.is_available() else "cpu"


def default_query_prefix(model_name: str) -> str:
    return BGE_QUERY_PREFIX if "bge-" in model_name.casefold() else ""


def validate_existing(path: Path, record_ids: list[str], query_ids: list[str], embedding_name: str) -> None:
    with np.load(path, allow_pickle=False) as bundle:
        if set(bundle.files) != NPZ_KEYS:
            raise ValueError(f"{path}: invalid NPZ keys")
        if list(map(str, bundle["record_ids"])) != record_ids:
            raise ValueError(f"{path}: record IDs do not match the dataset")
        if list(map(str, bundle["query_ids"])) != query_ids:
            raise ValueError(f"{path}: query IDs do not match the dataset")
        if str(bundle["embedding_name"].item()) != embedding_name:
            raise ValueError(f"{path}: embedding identity differs from this run")
        rv = bundle["record_vectors"]
        qv = bundle["query_vectors"]
        if rv.ndim != 2 or qv.ndim != 2 or len(rv) != len(record_ids) or len(qv) != len(query_ids):
            raise ValueError(f"{path}: invalid vector shapes")
        if rv.shape[1] != qv.shape[1] or not np.isfinite(rv).all() or not np.isfinite(qv).all():
            raise ValueError(f"{path}: incompatible or non-finite vectors")


def atomic_save(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        np.savez_compressed(temporary, **arrays)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_manifest(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--revision", help="Hugging Face commit hash; resolved and recorded when omitted")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or cuda:N")
    parser.add_argument("--max-traces", type=int)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--query-prefix", help="Override the model-specific retrieval query instruction")
    parser.add_argument("--no-resume", action="store_true", help="Reject existing trace files")
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")
    if args.max_traces is not None and args.max_traces < 1:
        raise ValueError("max traces must be positive")

    import sentence_transformers
    import torch
    from huggingface_hub import model_info
    from sentence_transformers import SentenceTransformer

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True

    dataset = Path(args.dataset)
    if not dataset.is_file():
        raise FileNotFoundError(dataset)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    device = resolve_device(args.device, torch)
    resolved_revision = model_info(args.model, revision=args.revision).sha
    model = SentenceTransformer(args.model, revision=resolved_revision, device=device)
    query_prefix = default_query_prefix(args.model) if args.query_prefix is None else args.query_prefix
    embedding_name = f"{args.model}@{resolved_revision};query_prefix={query_prefix!r};normalized=true"

    manifest = {
        "status": "running",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset),
        "dataset_sha256": sha256(dataset),
        "model": args.model,
        "requested_revision": args.revision,
        "resolved_revision": resolved_revision,
        "query_prefix": query_prefix,
        "normalized_embeddings": True,
        "device": device,
        "batch_size": args.batch_size,
        "seed": args.seed,
        "software": {
            "numpy": np.__version__,
            "sentence_transformers": sentence_transformers.__version__,
            "torch": torch.__version__,
        },
        "cuda_device": torch.cuda.get_device_name(0) if device.startswith("cuda") else None,
        "completed_traces": 0,
        "created_files": 0,
        "reused_files": 0,
    }
    write_manifest(out / "embedding_manifest.json", manifest)

    try:
        for ordinal, trace in enumerate(load_traces(dataset), start=1):
            if args.max_traces is not None and ordinal > args.max_traces:
                break
            nodes = trace["graph"]["nodes"]
            queries = [item["query"] for item in trace["queries"]]
            record_ids = [node["id"] for node in nodes]
            query_ids = [query["id"] for query in queries]
            target = out / f"{trace['trace_id']}.npz"
            if target.exists():
                if args.no_resume:
                    raise FileExistsError(target)
                validate_existing(target, record_ids, query_ids, embedding_name)
                manifest["reused_files"] += 1
            else:
                record_vectors = model.encode(
                    [node["text"] for node in nodes], batch_size=args.batch_size,
                    convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
                )
                query_vectors = model.encode(
                    [query_prefix + query["text"] for query in queries], batch_size=args.batch_size,
                    convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
                )
                atomic_save(
                    target,
                    record_ids=np.asarray(record_ids, dtype=np.str_),
                    record_vectors=np.asarray(record_vectors, dtype=np.float32),
                    query_ids=np.asarray(query_ids, dtype=np.str_),
                    query_vectors=np.asarray(query_vectors, dtype=np.float32),
                    embedding_name=np.asarray(embedding_name, dtype=np.str_),
                )
                validate_existing(target, record_ids, query_ids, embedding_name)
                manifest["created_files"] += 1
            manifest["completed_traces"] += 1
            if ordinal == 1 or ordinal % 25 == 0:
                write_manifest(out / "embedding_manifest.json", manifest)
                print(f"embedded {ordinal} traces", flush=True)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error_type"] = type(error).__name__
        write_manifest(out / "embedding_manifest.json", manifest)
        raise

    manifest["status"] = "completed"
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["npz_file_count"] = len(list(out.glob("*.npz")))
    write_manifest(out / "embedding_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
