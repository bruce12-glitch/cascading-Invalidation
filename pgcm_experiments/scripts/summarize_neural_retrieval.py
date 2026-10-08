"""Produce a compact, paper-facing audit table from retrieval.json."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


METRICS = ("CER", "CEP", "CLR", "VER", "retrieval_coverage", "SCF", "access_violation_rate")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neural", required=True, help="Neural retrieval.json")
    parser.add_argument("--hash", help="Optional hash-control retrieval.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    neural = json.loads(Path(args.neural).read_text(encoding="utf-8"))
    controls = json.loads(Path(args.hash).read_text(encoding="utf-8")) if args.hash else None
    rows = []
    for source, payload in (("neural", neural), ("hash", controls)):
        if payload is None:
            continue
        for item in payload["summaries"]:
            row = {"source": source, "embedding": payload["embedding"], "k": item["k"], "method": item["method"]}
            for metric in METRICS:
                row[metric] = item["metrics"][metric]["value"]
            rows.append(row)
    pgcm = [row for row in rows if row["source"] == "neural" and row["method"] == "pgcm_oracle"]
    checks = {
        "neural_status_measured": neural.get("status") == "measured_synthetic_integration",
        "pgcm_zero_context_leakage_all_k": bool(pgcm) and all(row["CLR"] == 0 for row in pgcm),
        "pgcm_zero_access_violations_all_k": bool(pgcm) and all(row["access_violation_rate"] == 0 for row in pgcm),
        "all_values_bounded": all(value is None or 0 <= value <= 1 for row in rows for value in (row[m] for m in METRICS)),
    }
    if not all(checks.values()):
        raise RuntimeError(f"retrieval audit failed: {checks}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "retrieval_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Neural Retrieval Results",
        "",
        f"Embedding: `{neural['embedding']}`",
        "",
        "| K | Method | CER | CEP | CLR | VER | Coverage | SCF | Access violation |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in [item for item in rows if item["source"] == "neural"]:
        fmt = lambda value: "NA" if value is None else f"{100 * value:.2f}%"
        formatted = {metric: fmt(row[metric]) for metric in METRICS}
        lines.append("| {k} | {method} | {CER} | {CEP} | {CLR} | {VER} | {retrieval_coverage} | {SCF} | {access_violation_rate} |".format(**{**row, **formatted}))
    (out / "NEURAL_RETRIEVAL_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    audit = {"status": "passed", "checks": checks, "row_count": len(rows), "neural_embedding": neural["embedding"]}
    (out / "retrieval_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
