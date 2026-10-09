# Cascading Invalidation in PG-CM: Reproduction Artifact

## Research summary for reviewers

**Problem.** Long-lived AI assistants accumulate stated facts, plans, and
permissions across turns, then silently act on stale ones: a retracted
configuration keeps justifying a fallback plan, a withdrawn approval keeps
authorizing an action, a superseded value keeps answering queries. This
artifact studies *cascading invalidation*: when a root record is withdrawn,
every derived record that loses all sufficient justifications must flip to
unsupported, while records with surviving alternative justifications
(OR-branches) must stay live.

**Contribution.** A counter-based incremental maintenance engine
(`src/pgcm_core.py`, Algorithm 1) with strict fail-closed admission, checked
transition-for-transition against an independent eager topological
recomputation (`src/oracle_evaluator.py`):

- Each justification clause counts its currently-unsupported premises
  (`missing`); each record counts its live clauses (`live`). A root
  withdrawal touches only incident clauses, so propagation cost scales with
  the affected region, not the graph.
- Withdrawing one parent of an OR-branch does not invalidate the record
  while another sufficient justification remains live (correction 1 of the
  methodological audit).
- Closure is measured against actual supported-to-unsupported state
  transitions, excluding direct roots; candidate filtering is scored as a
  separate operation (correction 2).
- Retrieval is gated by support, scope, principal permissions, and creation
  epoch; historical queries read a committed snapshot (correction 4).
- Actions bind complete preconditions and scope in a trusted registry;
  forbidden proposals are denied before any side effect (correction 5).
- Malformed graphs, conflicting updates, duplicate records, cycles, and
  future-dated premises are rejected at admission; the pipeline stops on any
  mismatch rather than degrading silently.

**What this artifact validates.**

1. *Exact maintenance (this directory).* 32,768 bounded four-node support
   configurations plus 2,000 frozen structural traces (6,000 retraction
   events, seed 20261008): engine and oracle agree on every label
   transition, with zero false invalidations. Counter-based propagation
   processed 26,000 incidence visits versus 66,000 eager premise scans
   (ratio 0.3939). Run `python reproduce_all.py`.
2. *Retrieval and support maintenance (companion `pgcm_experiments/`).*
   2,000 synthetic unreviewed integration fixtures, 336,000
   query/method/K evaluations. At K=5 with the hash embedding control:
   oracle CER/CEP/VER 100% with 84.53% coverage and 0% leakage; the
   no-eligibility-gate ablation keeps perfect closure scores yet leaks
   (96.37%) — closure without gating is not successful memory use; the
   descendant-pruning control over-removes alternatives (VER 83.33%).
   With pinned BGE-small-en-v1.5 embeddings (`results/`, revision
   `5c38ec7c`): oracle stays exact with zero violations while no-gate
   violations rise to 10–15% across K=5/10/20.
3. *Actions and snapshots.* 800 scripted attempts: 0 forbidden executions,
   400/400 permitted completed; 800 concurrent snapshot reads with
   0 inconsistencies (single-host SQLite/WAL, in-process callbacks).

**What this artifact does not claim.** The fixtures are synthetic and
unreviewed — not a human-reviewed conversational benchmark. No live model
was called; lineage-extraction, neural-retrieval (beyond the reported BGE
replay), QA, published-system baselines, and deployment-latency evidence
are still open (see `appendix/` and the audit's evidence table). Bootstrap
intervals are controlled-fixture diagnostics, not deployment confidence.
The original draft's 98.7% recall / 97.2% precision / 0.8% leakage figures
had no supplied raw data and are not reproduced here.

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
