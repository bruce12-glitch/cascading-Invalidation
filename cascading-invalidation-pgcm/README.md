# Cascading Invalidation in PG-CM: Reproduction Artifact

This artifact validates the symbolic support-maintenance implementation and
its structural conformance: a counter-based incremental engine
(`src/pgcm_core.py`, Algorithm 1) checked transition-for-transition against
an independent eager topological recomputation (`src/oracle_evaluator.py`)
over 32,768 bounded configurations and 2,000 frozen structural traces
(6,000 retraction events, seed 20261008).

## Prerequisites

- Python 3.10+ (tested on 3.11 and 3.13).
- Zero external dependencies: `reproduce_all.py` uses only the standard
  library (see `requirements.txt`).

## Quick start / reproduction

```bash
# To reproduce the 32,768 bounded checks and Table 1 metrics:
python reproduce_all.py
```

The script fails fast: any label mismatch, counter-invariant violation, or
deviation from the frozen logs stops execution with exit code 1. On success
it prints Table 1, writes `data/results/table1_results.json`, and writes
`data/results/exhaustive_log.txt`.

Measured output (this machine):

```text
Table 1 (measured by this script, fail-fast on any mismatch)
  bounded exhaustive checks : 32768
  traces                    : 2000
  retraction events         : 6000
  CER (exact / retractions) : 1.0000
  CEP (exact / predicted)   : 1.0000
  Exact events              : 6000
  False invalidations       : 0
Work-count verification (Section 7.2)
  Eager full-incidence scan : 66000
  Counter-based processed   : 26000
  Ratio                     : 0.3939
PASSED: engine and oracle agree on all checks and events.
```

Definitions: CER = exact events / retraction events; CEP = exact events /
events where the engine changed any label; an event is exact when the
engine's reported transitions equal the oracle's; false invalidations are
engine-reported invalidations the oracle did not make.

## Directory structure

- `reproduce_all.py`: master script (bounded checks + trace replay + Table 1).
- `src/pgcm_core.py`: counter-based root retraction, insertion/dual
  notification rules (Algorithm 1, Equation 2).
- `src/oracle_evaluator.py`: independent topological recomputation
  (ground-truth oracle; shares no counter state with the engine).
- `src/trace_generator.py`: deterministic fixture generator (5 depth
  families across 4 domains, master seed 20261008, per-trace seed
  20261008 + i). The replay uses the frozen `data/traces/` files.
- `src/metrics.py`: count-based cascade metrics (standard library only).
- `data/traces/structural_traces.jsonl`: 2,000 frozen traces (SHA-256
  `c7fe0e27b17b963d4499fc08f441b8de9776196d455e616db5c6cb0dbffc1c23`).
- `data/traces/structural_events.jsonl`: 6,000 frozen per-event oracle
  transitions the replay asserts against.
- `data/results/`: `table1_results.json`, `exhaustive_log.txt` (regenerated
  on each run).
- `appendix/`: slot for `full_proofs.pdf` (Propositions 1-3, Theorems 1-3;
  supplied from the manuscript, not generated).
- `anonymized_submission/Artifact_A1_Anonymous.zip`: clean zipped copy of
  this structure for supplementary material.

## Artifact scope disclaimer

This artifact validates the symbolic implementation and structural
conformance only. It is not an end-to-end conversational extraction
benchmark, has no human annotation review, and makes no production-latency
claim (timings here are incidence-visit counts, not wall-clock benchmarks).

## Citation

```bibtex
@inproceedings{anonymous2026pgcm,
  title   = {[PAPER TITLE]},
  author  = {[ANONYMIZED FOR REVIEW]},
  booktitle = {Proceedings of the AAAI Conference on Artificial Intelligence},
  year    = {2026}
}
```
