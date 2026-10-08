# Experimental-method audit

The submitted methods are not all correct as originally specified. The following
changes are required before publication. The code implements the corrected
restricted semantics; it does not certify the broad manuscript claims.

| Issue | Correction | Consequence for reporting |
|---|---|---|
| Unverified 98.7/97.2/0.8 percentages and 19.4 ms in abstract; attachment's example tables | Replace with measured tables after reproducible runs | Do not label supplied target numbers as observations |
| “All descendants invalid” | Positive AND within clauses, OR across clauses | A still-live alternative preserves support; ordinary descendant pruning is a negative control |
| Linear DAG claim with hyperedges | Complexity in premise incidences L, vertices n and clauses m | A dense conjunction may have many incidences per ordinary relation; report L and actual changed region |
| Fixed-point bound vs implementation | Counter updates maintain missing-premise and live-clause counts | Durable reference storage still rebuilds and serializes state; report costs separately |
| Token-level extraction F1 | Record-kind macro F1 under exact semantic-version alignment | This implementation has no token-span annotation task |
| Edge F1 conflated with support-set recovery | Exact (head, unordered conjunct set) match | Report alternative-clause recall and whole-head recovery separately |
| Root updates conflated with invalidation closure | Direct root changes excluded from CER/CEP | Compute transitions from each method's actual previous state, not candidate exclusions |
| Dense retrieval treated as inherently incapable of updates | Explicitly define implemented controls; include genuine external comparators later | Local-root and descendant controls are not published systems |
| Invalidating historical knowledge | Gate current and historical reads against different committed epochs | Exclude valid historical records from current contamination denominators |
| Missing scope/permission/time gate | Current support AND scope AND authorized principal AND creation epoch | A supported record can still be ineligible |
| Model-generated action preconditions trusted | Trusted immutable registry and latest-epoch dispatch admission | Count forbidden proposals separately from actual executions |
| SQLite correctness generalized to remote tools | Limit evidence to same-host serialized local callbacks | No distributed exactly-once or crash-safe remote side-effect result |
| Prospective benchmark called established dataset | Label generated fixtures unreviewed | Human annotation, adjudication, release and leakage-controlled splits remain necessary |
| Corruption removes final conjunct | Never admit empty conjunctions | Record skipped perturbations and realized counts |
| Corruption assumed monotonic in CER | Test pointwise state inclusion, separately from transition metrics | CER has changing denominators and can be nonmonotonic |
| Scope collapse counted as valid extraction | Preserve version/scope keys; reject duplicate semantic versions | Noncolliding incorrect merges require semantic adjudication, not merely schema checks |
| Same seeds/trace count implies independence | Identify repeated template families | Synthetic paired intervals describe this fixture distribution only |
| Bootstrap per query | Resample matched whole traces, recompute pooled ratios | Query observations within traces are not independent sampling units |
| Ratio with zero denominator | JSON null/undefined | Never report undefined precision as zero or one |
| Impossible batch silently capped | Explicit skip with requested size | Q=100 is infeasible when n=100 has only 50 roots here |
| perf_counter called hardware counter | Wall-clock timer metadata | Hardware event counts require another instrumented experiment |
| Propagation latency called end-to-end | Separate graph compile, initialization, propagation, commit, retrieval and model stages | No live-model latency in the bundled results |
| Cached calls mix configurations | Fingerprint config/system/schema/demonstrations | Reject incompatible cached predictions |

## Review findings and fixes

Review caught and corrected an O(n) pre/post label scan in the incremental engine,
non-JSON tuple round-trips, connection lifecycle issues, sequential baseline
transition scoring, an unsafe publication control with no affected descendants,
provider-cache mixing, and an incorrect positional corruption-driver call.
Regression/integration tests cover the consequential failures. Tests use an
independent topological full-recompute oracle and deterministic forced interleavings.
Bounded exhaustive checks cover 32,768 four-node configurations; randomized
checks cover 2,000 mixed activation/retraction steps. Neither constitutes an
unbounded proof, and passing tests cannot guarantee the absence of all errors.

## Reviewer meta-commentary

The strongest supported claim is exact support maintenance for admitted,
positive acyclic justification graphs under explicit root updates. The largest
scientific uncertainty is constructing those graphs from real conversations.
Exact semantic keys avoid a subjective matching judge but penalize benign
paraphrases and miss semantic distinctions. The benchmark must undergo dual
annotation with adjudication and agreement analysis; splits must hold out
linguistic and dependency templates. Evaluate real implementations of recent
memory-maintenance systems at pinned commits before making comparative novelty
or performance claims. Measure extraction failures, valid-evidence retention and
coverage alongside leakage; fail-closed retrieval can achieve zero leakage by
returning nothing. Do not generalize the synthetic results to all agent memory
systems or regard the code as a complete production memory service.

A final performance review added a dense affected-region control: every sufficient
justification includes one shared mandatory root. Withdrawing that root disables
all derived records. Random root batches alone often produce few downstream
changes in the generated OR-rich graphs, so their low propagation times must not
be interpreted as worst-case latency or universal speedup. Both topologies are
included, with actual affected counts and incidence-work ratios.
