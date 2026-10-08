"""Count-based estimators and paired trace-level bootstrap. Undefined is None."""
from __future__ import annotations
from collections import Counter
import numpy as np
from .model import Graph


def ratio(n, d):
    return n / d if d else None


def prf(tp, fp, fn):
    p, r = ratio(tp, tp + fp), ratio(tp, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r,
            "f1": ratio(2*tp, 2*tp + fp + fn)}


def align_nodes(gold: Graph, predicted: Graph):
    lookup = {n.semantic_key: n.id for n in gold.nodes}
    return {n.id: lookup[n.semantic_key] for n in predicted.nodes if n.semantic_key in lookup}


def extraction_counts(gold: Graph, pred: Graph, gold_updates, prediction):
    mapping = align_nodes(gold, pred)
    mapped = set(mapping.values())
    gc, pc = {n.id: n.kind for n in gold.nodes}, {n.id: n.kind for n in pred.nodes}
    counts = {kind: [0, 0, 0] for kind in ('R', 'D', 'A')}
    for pid, gid in mapping.items():
        if pc[pid] == gc[gid]: counts[gc[gid]][0] += 1
        else:
            counts[pc[pid]][1] += 1
            counts[gc[gid]][2] += 1
    for n in pred.nodes:
        if n.id not in mapping: counts[n.kind][1] += 1
    for n in gold.nodes:
        if n.id not in mapped: counts[n.kind][2] += 1
    gold_edges = {(r.head, frozenset(r.premises)) for r in gold.rules}
    pred_edges = set()
    for r in pred.rules:
        # Unmatched IDs remain false predictions, never silently discarded.
        h = mapping.get(r.head, ('unmatched_head', r.head))
        ps = frozenset(mapping.get(p, ('unmatched_premise', p)) for p in r.premises)
        pred_edges.add((h, ps))
    multi_heads = {h for h, _ in gold_edges if sum(r.head == h for r in gold.rules) > 1}
    alternative_edges = {r for r in gold_edges if r[0] in multi_heads}
    result = {"node_classes": counts,
              "scoped_key_match": [len(mapping), len(gold.nodes)],
              "hyperedges": [len(gold_edges & pred_edges), len(pred_edges - gold_edges), len(gold_edges - pred_edges)],
              "alternative_clause_recall": [len(alternative_edges & pred_edges), len(alternative_edges)],
              "alternative_head_exact": [sum(all(e in pred_edges for e in gold_edges if e[0] == h) for h in multi_heads), len(multi_heads)]}
    for op in ('retract', 'activate'):
        target = set(gold_updates[op])
        emitted = {mapping.get(p, ('unmatched_update', p)) for p in prediction[op]}
        result[op] = [len(target & emitted), len(emitted-target), len(target-emitted)]
    return result


def sum_extraction(records):
    cls = {k: [0, 0, 0] for k in ('R', 'D', 'A')}
    fields = ('scoped_key_match', 'hyperedges', 'alternative_clause_recall', 'alternative_head_exact', 'retract', 'activate')
    totals = {k: None for k in fields}
    for r in records:
        for k in cls: cls[k] = [a+b for a, b in zip(cls[k], r['node_classes'][k])]
        for k in fields:
            totals[k] = r[k].copy() if totals[k] is None else [a+b for a,b in zip(totals[k],r[k])]
    out = {"node_classification": {k: prf(*c) for k,c in cls.items()}}
    f1s = [d['f1'] for d in out['node_classification'].values() if d['f1'] is not None]
    out['node_macro_f1'] = float(np.mean(f1s)) if f1s else None
    for k, vals in totals.items():
        out[k] = None if vals is None else prf(*vals) if len(vals) == 3 else {"numerator": vals[0], "denominator": vals[1], "value": ratio(*vals)}
    return out


METRICS = {
    'CLR': ('leaked_queries', 'current_queries'),
    'SCF': ('unsupported_context_records', 'context_records'),
    'VER': ('valid_relevant_returned', 'valid_relevant_total'),
    'CER': ('cascade_tp', 'cascade_gold'),
    'CEP': ('cascade_tp', 'cascade_predicted'),
    'retrieval_coverage': ('nonempty_contexts', 'current_queries'),
    'access_violation_rate': ('access_violations', 'context_records'),
}


def summarize_counts(rows):
    counts = Counter()
    for row in rows: counts.update(row['counts'])
    return {k: {'numerator': counts[a], 'denominator': counts[b], 'value': ratio(counts[a], counts[b])}
            for k, (a,b) in METRICS.items()}


def paired_bootstrap(rows, method_a, method_b, metric, replicates=10000, seed=20261008):
    """Difference A-B, recomputing each pooled ratio on matched resampled traces."""
    num, den = METRICS[metric]
    pools = {}
    for r in rows:
        if r['method'] not in (method_a, method_b): continue
        key = (r['trace_id'], r['method'])
        if key in pools: raise ValueError("rows must be aggregated once per trace/method")
        pools[key] = (r['counts'].get(num,0), r['counts'].get(den,0))
    aid = {t for t,m in pools if m == method_a}
    bid = {t for t,m in pools if m == method_b}
    if aid != bid or not aid: raise ValueError("paired bootstrap requires exactly matched nonempty trace sets")
    ids = sorted(aid)
    a = np.array([pools[(t,method_a)] for t in ids], dtype=np.float64)
    b = np.array([pools[(t,method_b)] for t in ids], dtype=np.float64)
    point = ratio(a[:,0].sum(),a[:,1].sum())
    point_b = ratio(b[:,0].sum(),b[:,1].sum())
    if point is None or point_b is None:
        return {'metric': metric, 'difference_A_minus_B': None, 'ci95': None,
                'reason': 'undefined original denominator', 'independent_traces': len(ids)}
    if replicates < 1: raise ValueError("positive replicate count")
    rng, differences, undefined = np.random.default_rng(seed), [], 0
    for start in range(0,replicates,128):
        idx = rng.integers(0,len(ids),size=(min(128,replicates-start),len(ids)))
        sa, sb = a[idx].sum(axis=1), b[idx].sum(axis=1)
        valid = (sa[:,1]>0) & (sb[:,1]>0)
        undefined += int((~valid).sum())
        differences.extend((sa[valid,0]/sa[valid,1]-sb[valid,0]/sb[valid,1]).tolist())
    ci = np.quantile(differences,[.025,.975]).tolist() if differences else None
    return {'metric': metric, 'method_a':method_a, 'method_b':method_b,
            'difference_A_minus_B':float(point-point_b), 'ci95':ci,
            'independent_traces':len(ids),'replicates':replicates,'undefined_replicates':undefined,'seed':seed}
