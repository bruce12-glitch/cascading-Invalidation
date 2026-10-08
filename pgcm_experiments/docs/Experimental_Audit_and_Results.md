# Cascading Invalidation: Experimental Audit and Measured Results

The original experimental methods require correction; the code does not validate
the numerical claims supplied in the abstract or attachment. This deliverable
provides a reviewed, executable experimental reference and honest offline results.
It follows sequential analysis, implementation, review, and measured execution.
No finite test suite can guarantee an error-free implementation.

## 1. Delivered code and experimental scope

The archive contains the Python package, CLI, strict schemas, counter engine,
independent full-recompute oracle, SQLite epoch store, eligibility filters,
action registry, optional model callers, extraction/QA/provenance-regime replay,
external-baseline export scorer, bootstrap metrics, structural corruption,
concurrency/scalability drivers, 21 test cases, configuration examples, and raw
measured results. See README.md for runnable commands, docs/METHODS_AUDIT.md for
the full methodological audit, and docs/PROTOCOL.md for denominator contracts.

The completed run used 2,000 generated explicit-rule traces,
with 336,000 query/method/K evaluations. These
are **synthetic unreviewed integration fixtures**, not the proposed human-reviewed
CASCADE-BENCH. Models were not called and pretrained neural embeddings were not
used. The embedding control is `blake2-token-counts-v1`. Candidate budget is K,
with no refill after gating. Controls describe the actual implementation; they
are not labeled as implementations of published memory systems.

## 2. Required methodological corrections

1. Preserve OR alternatives: withdrawing one parent does not invalidate a record
   if another sufficient justification remains live.
2. Measure closure against actual supported-to-unsupported state transitions,
   excluding direct roots; candidate filtering is a different operation.
3. Use record-kind F1 and exact support-set F1 separately. The current protocol
   cannot claim token-level F1 without token-span annotations.
4. Gate by support, scope, principal permissions and creation epoch. Historical
   queries use a requested committed snapshot rather than current labels.
5. Bind complete action preconditions and scope in a trusted registry; distinguish
   forbidden proposals from executed side effects.
6. Report incidence-sensitive propagation separately from O(n+L) counter rebuild,
   O(n) snapshot serialization and model inference. Do not reuse 19.4 ms as a
   measured write-path result.
7. Use paired trace bootstrap with explicit counts/undefined denominators; repeated
   synthetic templates do not establish population-level statistical independence.
8. Report missing/invalid model attempts rather than dropping them. Freeze cache
   identity across dataset, model, prompt, schema and demonstrations.
9. Test corruption pointwise support polarity. Never create empty conjunctions or
   infer monotonic CER from support inclusion.
10. Use both sparse and dense affected-region timing controls, actual L, warm-up,
    random method order and separate setup costs. Skip infeasible root batches.

The claimed 98.7% recall, 97.2% precision, 0.8% leakage and example comparison
numbers have no supplied raw data/logs. They remain unverified and should be
removed from the paper until the corresponding real experiments are run.

## 3. Correctness and protocol review

All 21 test cases passed in the completed pipeline. The core review includes
32,768 bounded four-node checks and 2,000 randomized mixed update steps compared
with an independent eager topological recomputation. Additional checks cover
whole-batch rejection, counter consistency, OR alternatives, semantic versions,
scoped records, historical reads, restart/idempotency/CAS, rollback, staged writes,
permissions, action/retraction serialization, strict provider parsing, cache
separation, exact extraction scoring, missing-prefix behavior and export validation.
The pipeline smoke test mocks its nested unittest subprocess to avoid recursive
execution; the full run independently invokes the actual complete suite.

Review corrected an unnecessary full-state scan, JSON tuple round-trip errors,
connection handling, sequential baseline closure counting, non-load-bearing
unsafe concurrency witness, configuration/dataset cache mixing, driver argument
ordering, and action precondition authorization. Tests validate restricted
semantics; they do not prove semantic extraction from arbitrary conversations.

## 4. Retrieval and support maintenance: measured synthetic control

The following table reports K=5. Percentages are pooled count-based ratios;
raw numerators/denominators and K=10/20 results are included in retrieval.json.

| Implemented method | CER | CEP | CLR | VER | Nonempty coverage |
|---|---:|---:|---:|---:|---:|
| pgcm_oracle | 100.00% | 100.00% | 0.00% | 100.00% | 84.53% |
| local_root_update_control | 0.00% | undefined | 69.10% | 100.00% | 100.00% |
| descendant_pruning_control | 83.33% | 83.33% | 0.00% | 83.33% | 80.87% |
| no_eligibility_gate | 100.00% | 100.00% | 96.37% | 100.00% | 100.00% |

CER/CEP measure non-root state transitions; CLR measures current queries with at
least one unsupported returned record; VER measures supported relevant targets
retained. All unsupported returned kinds are counted, including roots. The
no-gate control retains oracle state maintenance, explaining perfect closure
scores alongside contamination. Descendant pruning over-removes alternatives
and loses valid evidence. Perfect VER applies only to the fixture relevance
annotations and embedding control, not arbitrary natural-language evidence.

paired_bootstrap.json contains 10,000 paired trace-level draws for CLR and VER
contrasts. These are descriptive fixture intervals. They do not justify confidence
in real conversation populations or in the proposed benchmark.

## 5. Action and snapshot controls

- 800 scripted local action attempts over 200 traces:
  400 ineligible attempts, 0 forbidden executions;
  400/400 eligible attempts completed.
- 800 concurrent committed snapshot reads and
  100 write transactions:
  0 support-label inconsistencies observed.
- During a deliberately staged uncommitted write, readers retained the old epoch:
  True.
- An intentionally unsafe partial-publication witness produced
  2 inconsistent derived labels.
  This is a forced control, not an estimated real-world failure rate.

These findings apply to single-host SQLite/WAL and in-process callbacks. They
provide no distributed exactly-once, crash-atomic external side-effect, or LLM
proposal-quality guarantee.

## 6. Performance and affected-region controls

The run measured 60 sparse-topology conditions with
5 repetitions each, up to 100,000 records, plus three dense
shared-root conditions. 4 infeasible Q=100 conditions on
50-root small graphs were explicitly skipped. Setup and compilation are recorded
separately. The table lists median propagation wall time in milliseconds.

| Topology/update | L | Mean changed records | Counter incidence fraction | Counter ms | Full recompute ms | Eager rescan ms |
|---|---:|---:|---:|---:|---:|---:|
| Sparse random withdrawal, Q=1 | 300000 | 1.0 | 0.000027 | 0.0835 | 78.3965 | 0.1702 |
| Sparse random withdrawal, Q=5 | 300000 | 5.0 | 0.000115 | 0.1109 | 80.3434 | 0.2294 |
| Sparse random withdrawal, Q=25 | 300000 | 25.6 | 0.000575 | 0.3135 | 80.9587 | 0.5670 |
| Sparse random withdrawal, Q=100 | 300000 | 107.6 | 0.002487 | 0.9594 | 88.0048 | 1.6141 |
| Shared mandatory root, n=1,000, Q=1 | 4495 | 901.0 | 0.840934 | 0.6326 | 0.3534 | 0.6729 |
| Shared mandatory root, n=10,000, Q=1 | 44994 | 9001.0 | 0.840112 | 7.6835 | 6.6673 | 7.5199 |
| Shared mandatory root, n=100,000, Q=1 | 449987 | 90001.0 | 0.840024 | 116.6847 | 101.5111 | 92.7776 |

Sparse updates often change only roots. Their short latencies must not be used
as worst-case or universal speedup evidence. The shared-root control forces all
derived support to disappear and exposes dense affected-region cost. Timing is
machine-specific, and five repetitions yield coarse p95 estimates. Python object
sizes are estimates; separately measured components may share referents and must
not be summed as a unique total.

The isolated 100,000-record, 20-candidate eligibility microbenchmark had median
2.985 microseconds and p95
3.306 microseconds. This excludes candidate ranking,
vector encoding, snapshot access and generation. It is not query end-to-end time.

## 7. Corruption experiments

Across 9 corruption/rate conditions, 7,200
snapshot comparisons and 93,600 label comparisons, the run observed
0 violations of the pointwise support-polarity bounds. Clause deletion
and added conjuncts can only remove support; deleting conjuncts can only add
support under common root admissions and positive acyclic semantics. Realized
perturbations, skipped empty-conjunction operations and false-active/inactive
IDs are recorded. These experiments do not estimate the distribution of errors
made by an LLM. Scope/facet collision admission tests are not a complete semantic
merge-robustness benchmark.

## 8. Experiments still requiring scientific evidence

| Component | Infrastructure delivered | Publication evidence still needed |
|---|---|---|
| Four-model zero/3-shot lineage extraction | Prefix-safe callers, strict admission, replay scoring | Actual pinned model runs on independent annotated test traces |
| Inferred provenance retrieval | Three replay regimes; failed prefixes and unmatched propositions tracked | Actual extraction outputs and human semantic identity adjudication |
| Neural retrieval | Validated external NPZ embedding interface | Versioned encoder/pooling runs and budget-matched comparisons |
| Free-form QA / adversarial probes | Answer collection and restricted decision/evidence replay | Human factual correctness, rejection justification and proposal labels |
| Published memory baselines | Identity-qualified actual-context export scorer | Genuine pinned repository executions and faithful adapters |
| CASCADE-BENCH | Generated structural fixtures | 2,000 human-reviewed traces, agreement, adjudication, held-out templates |
| Deployment performance | Local snapshot and action controls | ANN/model/service latency, repeated hardware runs, remote tool coordination |

No missing empirical cell is filled with a fabricated zero or target number.
Unmatched inferred propositions have unknown gold support; their context counts
must accompany reported leakage. Zero leakage from an empty context is not
sufficient success: inspect coverage and valid-evidence retention.

## 9. Reproduce and extend

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pgcm run-offline --config configs/offline.json --out results/new_run
```

Use `extract-live`, `evaluate-extraction`, `evaluate-regimes`, `qa-live`,
`evaluate-qa`, `retrieval --vectors-dir`, and `evaluate-baseline` for separately
recorded external experiments. Optional callers never execute in run-offline.
Exact provider/model configuration must be set before a live call.

Run start: 2026-10-07T23:41:06.998769+00:00; finish: 2026-10-07T23:43:53.468682+00:00.
Python: 3.12.14; NumPy:
2.3.5; SQLite: 3.53.1.
Host CPU model, container CPU quota and memory limit are recorded in docs/HOST_DETAILS.json; host access was not exclusive. Configuration, environment, dataset/source/result hashes and raw samples accompany
the code. Original supplied target tables were not used to generate results.

## Reviewer Meta-Commentary

The artifact substantiates exact maintenance under explicit admitted positive
DAG provenance and demonstrates local protocol behavior. The primary unresolved
research question is whether real conversation extraction provides sufficiently
complete, correctly scoped alternative justifications. Neither formal support
correctness nor synthetic zero leakage proves natural-language agent reliability.
Publication requires audited traces, live-model measurements, faithful recent
baselines, and clear separation of correctness theorems, implementation tests,
and empirical generalization. The durable store is a reference implementation,
not a proof of affected-region total write latency.
