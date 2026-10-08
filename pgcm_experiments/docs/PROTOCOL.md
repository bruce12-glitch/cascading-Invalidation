# Scoring and protocol contracts

For current queries, CLR is the fraction containing at least one gold-unsupported
record. SCF is unsupported returned records divided by returned records. These
count both stale roots and stale derived records. Report this convention; a
derived-only contamination definition would require a separate counter. VER is
returned gold-supported relevant target records divided by all gold-supported
relevant target records. Nonempty-context coverage prevents an empty-result
system from appearing unconditionally successful. Scope/access violations have
separate counts. All ratios include numerators and denominators; a denominator
of zero gives null. Historical queries use their requested epoch and have separate
valid-target counts, not current CLR entries.

CER and CEP score non-root supported-to-unsupported transitions. TP is intersection
with gold transitions. CER=TP/gold transitions; CEP=TP/predicted transitions.
A control that was incorrectly inactive already has no new invalidation on the
next event. Consequently CER is not identical to a pointwise inactive-label recall.
K does not alter support maintenance; identical CER/CEP across K is expected.
The no-retrieval-gate ablation retains oracle support maintenance, so its CER/CEP
can be perfect while retrieved context leaks. Do not interpret that as successful
memory use.

Candidate budget is K; fetch the first K creation-visible cosine candidates, then
filter, returning at most K with no refill. This isolates gate effects at equal
retrieval budgets but can lower retention. Oversampling/refill is a separate
experimental condition, not an implicit optimization. Timing includes cosine,
ranking and eligibility in retrieval outputs; it is not isolated gate latency.
Record exact-search scale separately from counter-maintenance scalability.

All inference prefixes contain only turns available at that epoch. Gold graphs
and query target annotations stay in the scorer. Future record versions are
predeclared in offline fixtures but cannot enter candidate retrieval before their
creation epochs. Gold-output replay tests are infrastructure validation, not
model extraction results. Inferred-target regimes map extracted IDs to gold
semantic-version keys. Inferred-graph regimes preserve prior root admissions by
semantic version across recompilation. Malformed prefixes fail closed for the
inferred graph; missing target updates in supplied-graph replay leave the previous
state, exposing the error. Unmatched inferred propositions have unknown gold
support and are explicitly reported; they do not prove zero contamination.

The replay reference exposes no CER/CEP for growing inferred graphs: record
omission, graph mutation and root withdrawal are not conflated into one closure
score. Add annotated identity and deletion semantics before reporting those
metrics in that regime. Prefix structural recompilation is not claimed to have
affected-region runtime.

For a genuine published-system comparison, run the original implementation or
a documented faithful adaptation with a pinned repository commit. Export the
actual returned record IDs and state transitions; preserve the model, retrieval
budget, embeddings, admission scope, data split and prompting. Do not relabel
this repository's controls as MemGPT, Zep, A-MEM, PACMI or MemTX. No adapter for
those repositories is supplied or claimed to have been executed.

Action admission uses a trusted action registry and complete required ID sets.
Local callbacks execute while the write lock prevents concurrent root withdrawal.
The action experiment contains scripted proposals, not LLM-generated proposals;
therefore it measures forbidden execution and permitted completion only. A
callback can perform a partial side effect and then fail, or a process can crash
after a side effect and before audit commit. Remote production actions require
idempotency, reservations and/or coordinated transactions. These are outside
this experimental local callback protocol.

The paired percentile bootstrap resamples whole matched trace rows and recomputes
pooled ratios using 10,000 draws. CI signs refer to PG-CM minus control. Current
fixtures share scripted families, so even trace-level resampling cannot justify
population inference about real conversations. Treat these intervals as
controlled-fixture diagnostics, not publication confidence in deployment quality.

The external-context scorer is available through `evaluate-baseline`. Supply
`--dataset`, `--contexts`, `--identity`, and `--out`. Context JSONL rows contain
`trace_id`, `query_id`, `k`, `epoch`, `context` (unique immutable gold IDs after an
audited mapping). Identity JSON requires nonempty strings `method`, `repository`,
`commit`, `model`, `embedding`, `candidate_budget`, `prompt_sha256`, `adaptation`.
An identity file documents provenance; the scorer cannot authenticate that the
caller genuinely ran that repository. Historical exports must specify their
requested view epoch. Missing exports are empty contexts and counted as missing;
future evidence and unknown IDs raise errors.

`gate_overhead.json` isolates eligibility filtering over preselected candidate
IDs. It excludes vectors, ranking, snapshot acquisition and model calls. The
retrieval trace logs measure ranking plus filtering; neither is model end-to-end
latency. Five propagation repetitions per condition support descriptive timing
summaries only; tail-latency estimates from five samples are coarse. Repeat on
identified hardware with larger repetitions for publication tail measurements.

Action registration binds a trusted scope. All required record scopes must agree
with that scope; every required record must authorize the executing principal.
An explicitly supplied mismatched dispatch scope is denied. The registry supplies
the action scope when the caller omits it; a model cannot invent cross-scope
requirements by passing its own precondition list.
