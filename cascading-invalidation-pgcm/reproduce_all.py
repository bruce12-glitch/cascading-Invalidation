#!/usr/bin/env python3
"""Master reproduction script. Standard library only; fails fast.

Phase A: bounded exhaustive validation of the counter engine against the
independent oracle over all 32,768 four-node support configurations
(support-clause shapes x root assignments x update batches x operations).

Phase B: replay of the 2,000 frozen structural traces
(data/traces/structural_traces.jsonl, seed 20261008). Every event is applied
through CounterEngine.change, cross-checked against an independent
full topological recomputation, and compared transition-for-transition.
Any label mismatch, counter-invariant violation, or deviation from the
frozen event log stops execution with exit code 1.

Outputs (data/results/): table1_results.json, exhaustive_log.txt.
"""
from __future__ import annotations
import json
import sys
from itertools import combinations, product
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import pgcm_core as core
import oracle_evaluator as oracle
from metrics import event_scores, fmt, ratio

ROOT = Path(__file__).resolve().parent
TRACES = ROOT / "data" / "traces" / "structural_traces.jsonl"
FROZEN_EVENTS = ROOT / "data" / "traces" / "structural_events.jsonl"
RESULTS = ROOT / "data" / "results"


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def nodes(n: int, roots: int = 2):
    return tuple(
        core.Node(str(i), f"record {i}", "R" if i < roots else "D",
                  f"e{i}", "a", "s", "v")
        for i in range(n)
    )


def subsets(xs):
    xs = list(xs)
    return [c for k in range(len(xs) + 1) for c in combinations(xs, k)]


def phase_bounded_exhaustive(log_lines: list) -> int:
    """All four-node support configurations. Returns the check count."""
    checks = 0
    for a in subsets(subsets(range(2))[1:]):
        for b in subsets(subsets(range(3))[1:]):
            rules = [(2, ps) for ps in a] + [(3, ps) for ps in b]
            graph = core.Graph(
                nodes(4),
                tuple(core.Rule(str(j), str(h), tuple(map(str, ps)))
                      for j, (h, ps) in enumerate(rules)),
            )
            for bits in product((False, True), repeat=2):
                roots = {str(i): bits[i] for i in range(2)}
                for batch in subsets(("0", "1")):
                    for operation in ("retract", "activate"):
                        engine = core.CounterEngine(graph, roots)
                        engine.change(**{operation: batch})
                        try:
                            engine.verify()
                        except RuntimeError as error:
                            fail(f"counter/oracle mismatch: {error}")
                        for record in batch:
                            expected = operation == "activate"
                            if engine.active[graph.index[record]] != expected:
                                fail(f"update not applied to {record}")
                        checks += 1
    log_lines.append(f"bounded four-node configurations checked: {checks}")
    if checks != 32768:
        fail(f"expected 32768 bounded checks, ran {checks}")
    return checks


def label_sets(graph: core.Graph, before: list, after: list):
    ids = [n.id for n in graph.nodes]
    inv = frozenset(nid for nid, b, a in zip(ids, before, after) if b and not a)
    act = frozenset(nid for nid, b, a in zip(ids, before, after) if a and not b)
    return inv, act


def phase_trace_replay(log_lines: list) -> dict:
    traces = [core.strict_json(line) for line in
              TRACES.read_text().splitlines() if line.strip()]
    if len(traces) != 2000:
        fail(f"expected 2000 frozen traces, found {len(traces)}")
    frozen = [json.loads(line) for line in
              FROZEN_EVENTS.read_text().splitlines() if line.strip()]
    derived = []
    totals = {"events": 0, "retraction_events": 0, "exact": 0,
              "false_invalidations": 0, "missed_invalidations": 0,
              "false_activations": 0, "missed_activations": 0,
              "gold_changed": 0, "pred_changed": 0,
              "counter_visits": 0, "eager_scans": 0}
    for trace in traces:
        graph = core.Graph.from_dict(trace["graph"])
        roots = dict(trace["initial_roots"])
        engine = core.CounterEngine(graph, roots)
        before, _ = oracle.full_recompute(graph, engine.root_values)
        for event in trace["events"]:
            epoch = event["epoch"]
            for rid in event["retract"]:
                roots[rid] = False
            for aid in event["activate"]:
                roots[aid] = True
            after, _ = oracle.full_recompute(graph, core.root_vector(graph, roots))
            gold_inv, gold_act = label_sets(graph, before, after)
            change = engine.change(retract=event["retract"],
                                   activate=event["activate"])
            try:
                engine.verify()
            except RuntimeError as error:
                fail(f"{trace['trace_id']} epoch {epoch}: {error}")
            if list(engine.active) != list(after):
                fail(f"{trace['trace_id']} epoch {epoch}: engine labels differ from oracle")
            scores = event_scores(gold_inv, gold_act,
                                  change.invalidated, change.activated)
            totals["events"] += 1
            if event["retract"]:
                totals["retraction_events"] += 1
            totals["exact"] += int(scores["exact"])
            for key in ("false_invalidations", "missed_invalidations",
                        "false_activations", "missed_activations"):
                totals[key] += scores[key]
            totals["gold_changed"] += int(scores["gold_changed"])
            totals["pred_changed"] += int(scores["pred_changed"])
            totals["counter_visits"] += change.visits
            _, scans = oracle.full_recompute(graph, engine.root_values)
            totals["eager_scans"] += scans
            derived.append({"trace_id": trace["trace_id"], "epoch": epoch,
                            "retract": event["retract"],
                            "activate": event["activate"],
                            "gold_invalidated": sorted(gold_inv),
                            "gold_activated": sorted(gold_act)})
            before = after
    if [ (d["trace_id"], d["epoch"], d["retract"], d["activate"],
          d["gold_invalidated"], d["gold_activated"]) for d in derived
       ] != [ (f["trace_id"], f["epoch"], f["retract"], f["activate"],
               f["gold_invalidated"], f["gold_activated"]) for f in frozen ]:
        fail("derived event log differs from data/traces/structural_events.jsonl")
    totals["work_ratio"] = ratio(totals["counter_visits"], totals["eager_scans"])
    totals["CER"] = ratio(totals["exact"], totals["retraction_events"])
    totals["CEP"] = ratio(totals["exact"], totals["pred_changed"])
    log_lines.append(f"traces replayed: {len(traces)}")
    log_lines.append(f"retraction events: {totals['retraction_events']}")
    log_lines.append(f"exact events: {totals['exact']}")
    log_lines.append(f"false invalidations: {totals['false_invalidations']}")
    return totals


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    log_lines: list = ["PG-CM cascading-invalidation reproduction log"]
    bounded = phase_bounded_exhaustive(log_lines)
    replay = phase_trace_replay(log_lines)
    for key in ("false_invalidations", "missed_invalidations",
                "false_activations", "missed_activations"):
        if replay[key] != 0:
            fail(f"nonzero {key}: {replay[key]}")
    table = {"bounded_checks": bounded, "traces": 2000, **replay}
    (RESULTS / "table1_results.json").write_text(json.dumps(table, indent=2) + "\n")
    (RESULTS / "exhaustive_log.txt").write_text("\n".join(log_lines) + "\n")
    print("Table 1 (measured by this script, fail-fast on any mismatch)")
    print(f"  bounded exhaustive checks : {bounded}")
    print(f"  traces                    : 2000")
    print(f"  retraction events         : {replay['retraction_events']}")
    print(f"  CER (exact / retractions) : {fmt(replay['CER'])}")
    print(f"  CEP (exact / predicted)   : {fmt(replay['CEP'])}")
    print(f"  Exact events              : {replay['exact']}")
    print(f"  False invalidations       : {replay['false_invalidations']}")
    print("Work-count verification (Section 7.2)")
    print(f"  Eager full-incidence scan : {replay['eager_scans']}")
    print(f"  Counter-based processed   : {replay['counter_visits']}")
    print(f"  Ratio                     : {fmt(replay['work_ratio'])}")
    print("PASSED: engine and oracle agree on all checks and events.")


if __name__ == "__main__":
    main()
