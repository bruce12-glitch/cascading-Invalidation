"""Incremental counters plus independent eager topological recomputation."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from time import perf_counter_ns
from .model import AdmissionError, Graph, root_vector


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


@dataclass(frozen=True)
class Change:
    invalidated: frozenset[str]
    activated: frozenset[str]
    visits: int
    propagation_ns: int


class CounterEngine:
    def __init__(self, graph: Graph, roots: dict[str, bool]):
        self.graph = graph
        self.root_values = root_vector(graph, roots)
        self.active, _ = full_recompute(graph, self.root_values)
        self.missing = [sum(not self.active[p] for p in ps) for ps in graph.parents]
        self.live = [0] * len(graph.nodes)
        for j, m in enumerate(self.missing):
            if m == 0:
                self.live[graph.heads[j]] += 1

    def clone(self):
        other = object.__new__(type(self))
        other.graph = self.graph
        for name in ("root_values", "active", "missing", "live"):
            setattr(other, name, getattr(self, name).copy())
        return other

    def change(self, retract=(), activate=()) -> Change:
        g = self.graph
        # Validate the whole request before mutating any state.
        off, on = tuple(dict.fromkeys(retract)), tuple(dict.fromkeys(activate))
        if set(off) & set(on):
            raise AdmissionError("conflicting_update", "disjoint batches required")
        if any(x not in g.index or g.index[x] not in g.roots for x in off+on):
            raise AdmissionError("update_target", "only registered roots may be directly updated")
        original = {}
        t0, visits = perf_counter_ns(), 0
        def flip(i,value,queue):
            if self.active[i] != value:
                original.setdefault(i,self.active[i])
                self.active[i]=value
                queue.append(i)
        for batch, value in ((off, False), (on, True)):
            queue = deque()
            for node_id in batch:
                r = g.index[node_id]
                self.root_values[r] = value
                flip(r,value,queue)
            while queue:
                u = queue.popleft()
                for j in g.incidence[u]:
                    visits += 1
                    old = self.missing[j]
                    self.missing[j] += -1 if value else 1
                    h = g.heads[j]
                    if value and self.missing[j] == 0:
                        self.live[h] += 1
                        if not self.active[h]:
                            flip(h,True,queue)
                    elif not value and old == 0:
                        self.live[h] -= 1
                        if self.live[h] == 0 and self.active[h]:
                            flip(h,False,queue)
        invalidated=frozenset(g.nodes[i].id for i,a in original.items() if a and not self.active[i])
        activated=frozenset(g.nodes[i].id for i,a in original.items() if not a and self.active[i])
        return Change(invalidated,activated,visits,perf_counter_ns()-t0)

    def verify(self):
        oracle, _ = full_recompute(self.graph, self.root_values)
        if self.active != oracle:
            raise RuntimeError("support labeling differs from full recomputation")
        expected = [sum(not self.active[p] for p in ps) for ps in self.graph.parents]
        live = [0] * len(self.active)
        for j, m in enumerate(expected):
            live[self.graph.heads[j]] += int(m == 0)
        if self.missing != expected or self.live != live:
            raise RuntimeError("counter invariant violated")


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
