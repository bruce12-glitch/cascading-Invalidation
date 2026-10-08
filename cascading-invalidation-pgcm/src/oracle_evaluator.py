"""Independent ground-truth oracle: eager topological recomputation.

Frozen stdlib-only snapshot of full_recompute/eager_retract/
descendant_retract from pgcm/engine.py @c5f7baa. It shares only
the Graph data type (imported under TYPE_CHECKING) and never reads
counter state, so agreement with pgcm_core is an independent check.
"""
from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pgcm_core import Graph

def full_recompute(graph: Graph, roots: list[bool]):
    if len(roots) != len(graph.nodes):
        raise ValueError("root vector size")
    active = [False] * len(roots)
    visits = 0
    for v in graph.topological:
        if v in graph.roots:
            active[v] = bool(roots[v])
        else:
            result = False
            for j in graph.byhead[v]:
                clause = True
                for p in graph.parents[j]:
                    visits += 1
                    clause = bool(active[p]) and clause  # deliberately eager
                result = clause or result
            active[v] = result
    return active, visits

def eager_retract(graph, before, batch):
    active, queue = before.copy(), deque()
    scans = 0
    for node_id in sorted(set(batch)):
        r = graph.index[node_id]
        if r not in graph.roots:
            raise ValueError("not a root")
        if active[r]:
            active[r] = False
            queue.append(r)
    while queue:
        u = queue.popleft()
        for h in sorted(set(graph.children[u])):
            if not active[h]:
                continue
            supported = False
            for j in graph.byhead[h]:
                clause = True
                for p in graph.parents[j]:
                    scans += 1
                    clause = active[p] and clause
                supported = clause or supported
            if not supported:
                active[h] = False
                queue.append(h)
    return active, scans


def descendant_retract(graph, before, batch):
    active, seen, queue = before.copy(), set(), deque(graph.index[r] for r in batch)
    while queue:
        u = queue.popleft()
        if u in seen:
            continue
        seen.add(u)
        active[u] = False
        queue.extend(graph.children[u])
    return active
