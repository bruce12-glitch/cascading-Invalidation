# PG-CM experimental reference implementation

This repository implements positive acyclic AND/OR support maintenance, immutable
SQLite epochs, lineage-gated retrieval, local action admission, and replayable
experiments for the cascading-invalidation manuscript. It includes measured
offline results. It does **not** assert that the manuscript's supplied numerical
claims were reproduced, or that all proposed model experiments have been run.

## Installation and reviewed execution

Use Python 3.12+ and NumPy. No paid model calls occur in this command.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pgcm run-offline --config configs/offline.json --out results/new_run
```

The driver first reviews the test suite, executes each experimental phase in
sequence, records completion or failure, and stops on errors. Output directories
must be empty. `manifest.json` records configuration, source/data/result SHA-256,
environment and execution status. Timings are machine-specific observations.
Package imports work directly from the repository without editable installation.

## Experiments and boundaries

| Experiment | Implemented | What bundled execution establishes |
|---|---|---|
| 1: extraction/admission | Strict schema, prefix-only prompts, OpenAI-compatible/Anthropic/local-command clients, zero/3-shot separation, exact node/edge/update scoring | Mock transport and gold-output replay verify infrastructure; live model accuracy is unmeasured |
| 2: retrieval | Supplied graph, three provenance replay regimes, exact cosine, K=5/10/20, paired trace bootstrap; external NPZ vectors supported | Hashed-token embedding control on generated explicit-rule traces; no neural retrieval claim |
| 3: QA/actions | QA output collection/replay; latest-epoch trusted action registry; local dispatch and audit | Scripted proposals and local effects; no free-form QA factual correctness or remote exactly-once claim |
| 4: performance | Counter/full-recompute/eager-rescan, actual incidence counts, isolated initialization/compile costs, warm-up, randomized timing order, concurrency | In-memory propagation and single-host SQLite/WAL observations; no model latency |
| 5: corruption | Drop sufficient clauses, drop conjuncts without empty rules, add spurious conjuncts; pointwise polarity tests | Structural perturbation response; not an empirically estimated LLM error distribution |

Read `docs/METHODS_AUDIT.md` and `docs/PROTOCOL.md` before transferring numbers to
the paper. The generated 2,000 fixtures repeat controlled templates with varied
entity identifiers and depth. They are **not** 2,000 independent human-reviewed
conversations, and their confidence intervals do not establish real-world
performance. Seed values identify runs; seed variation does not create distinct
linguistic templates in the current fixture generator.

## Model extraction: explicit separate step

Copy an example provider configuration, set an exact available model ID, and
supply credentials through its named environment variable. Use distinct output
files for different models, prompts, temperatures and shot conditions. Errors
remain failed attempts; no automatic output repair removes them from denominators.

```bash
python -m pgcm extract-live --dataset results/new_run/fixtures.jsonl \
  --config configs/my_model.json --out results/model_extractions.jsonl --max-requests 20
python -m pgcm evaluate-extraction --dataset results/new_run/fixtures.jsonl \
  --predictions results/model_extractions.jsonl --out results/extraction_evaluation
python -m pgcm evaluate-regimes --dataset results/new_run/fixtures.jsonl \
  --predictions results/model_extractions.jsonl --out results/regime_evaluation
```

A `--examples` JSON array must contain exactly three demonstrations with
`trace_id` values disjoint from evaluation traces. Curate demonstrations from an
independent development split. Avoid sharing template families between training,
development and test data in a publication benchmark. Model availability and
compatible token parameters vary; these clients fail explicitly rather than
silently switching models. Prefixes are four per current fixture, not one per
query. No future graph or gold target IDs are supplied to a model.

For open models, use the OpenAI-compatible endpoint of your local inference
server, or provider `command` with a JSON argv array. The command receives
`{system,user,schema}` on stdin and must return `{output,usage?}` on stdout.
Shell evaluation is disabled. The model invocation, weights, quantization,
inference library revision and hardware still need to be recorded by the caller.

## QA collection and replay

```bash
python -m pgcm qa-live --dataset results/new_run/fixtures.jsonl \
  --contexts results/new_run/retrieval_queries.jsonl.gz --config configs/my_model.json \
  --out results/model_qa.jsonl --k 5 --method pgcm_oracle
python -m pgcm evaluate-qa --dataset results/new_run/fixtures.jsonl \
  --contexts results/new_run/retrieval_queries.jsonl.gz --predictions results/model_qa.jsonl \
  --out results/qa_evaluation --k 5 --method pgcm_oracle
```

Decision/evidence correctness is a restricted automated score. It does not judge
whether the answer text faithfully states every fact. Record human-adjudicated
factual correctness separately. Correct rejections require available evidence;
empty contexts cannot establish that a premise is false. The stale-premise fixture
oracle describes the desired answer, not proof that a retrieved context contains
all evidence required to produce it.

## Pretrained embeddings

Supply one NPZ file per trace, named `<trace_id>.npz`, with arrays `record_ids`,
`record_vectors`, `query_ids`, `query_vectors`, and scalar `embedding_name`.
All vectors must be finite, dimensionalities consistent, and IDs match the trace.
The loader disables pickle. The vector encoder must encode only record/query
text, with versioned model and pooling/preprocessing details recorded separately.
The matcher is exact cosine; ANN effects are not measured by this implementation.

```bash
python -m pgcm retrieval --dataset results/new_run/fixtures.jsonl \
  --vectors-dir my_embeddings --out results/neural_retrieval
```

## Module map

`model`: admission and compiled hypergraph; `engine`: independent oracle and
incremental counters; `store`: epochs and local action serialization;
`retrieval`: embedding control and eligibility; `metrics`: estimators/bootstrap;
`dataset`: fixtures/scalable graphs; `experiments`, `regimes`: replay/evaluation;
`robustness`, `performance`, `concurrency`: structural/system experiments;
`providers`: optional callers; `cli`: sequential reviewed run.

SQLite snapshots rebuild a counter engine for each write and serialize label
vectors. These cost O(n+L) and O(n), respectively. The in-memory counter engine
operates on the affected incidence region; the durable store does **not** inherit
that total write-cost bound. Graphs in the durable store are immutable; inferred
prefix graph growth uses recompilation. Negation, nonmonotonic defaults,
probabilistic belief, cross-scope equivalence and temporal interval overlap are
outside the supported semantics. Unsupported means lacking admitted support,
not logically false.

## Affected-region and comparison controls

The performance driver also measures a shared-mandatory-root topology in
`affected_region.json`. A single root withdrawal disables every derived record.
This prevents small random update batches, which often change only roots, from
being used to claim a universal latency advantage. Report changed-record counts
and scanned-incidence ratios with latency. The isolated predicate microbenchmark
is in `gate_overhead.json`.

Actual external-system exports can be scored with `evaluate-baseline`; see the
identity and JSONL contracts in `docs/PROTOCOL.md`. This scorer is an integration
interface, not an implementation of another paper's memory architecture.
