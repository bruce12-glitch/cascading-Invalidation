"""Immutable records, strict admission, and explicit AND/OR hypergraphs."""
from __future__ import annotations
from collections import deque
from dataclasses import asdict, dataclass
import json
from types import MappingProxyType
from typing import Any


class AdmissionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def strict_json(text: str) -> Any:
    def object_hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise AdmissionError("duplicate_json_key", k)
            out[k] = v
        return out
    def bad_constant(s):
        raise AdmissionError("nonfinite_json", s)
    try:
        return json.loads(text, object_pairs_hook=object_hook, parse_constant=bad_constant)
    except json.JSONDecodeError as e:
        raise AdmissionError("invalid_json", str(e)) from e


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    text: str
    kind: str
    entity: str
    attribute: str
    scope: str
    value: str
    created_epoch: int = 0
    permissions: tuple[str, ...] = ("researcher",)

    @property
    def semantic_key(self):
        # Versions of a slot may coexist. Value and creation epoch distinguish them.
        return (self.scope, self.entity, self.attribute, self.value, self.created_epoch)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    head: str
    premises: tuple[str, ...]


class Graph:
    """Compiled immutable graph; all runtime support is kept outside the graph."""
    def __init__(self, nodes: tuple[Node, ...], rules: tuple[Rule, ...]):
        for n in nodes:
            if not isinstance(n, Node) or not all(isinstance(v, str) for v in
                (n.id, n.text, n.kind, n.entity, n.attribute, n.scope, n.value)):
                raise AdmissionError("node_fields", "string fields required")
        ids = [n.id for n in nodes]
        if not nodes or len(ids) != len(set(ids)):
            raise AdmissionError("duplicate_or_empty_nodes", "node IDs must be unique")
        keys = [n.semantic_key for n in nodes]
        if len(keys) != len(set(keys)):
            raise AdmissionError("duplicate_version", "same semantic record version repeated")
        for n in nodes:
            if n.kind not in {"R", "D", "A"}:
                raise AdmissionError("node_kind", n.id)
            if type(n.created_epoch) is not int or n.created_epoch < 0:
                raise AdmissionError("creation_epoch", n.id)
            if not all(isinstance(v, str) and v.strip() for v in
                       (n.id, n.text, n.entity, n.attribute, n.scope, n.value)):
                raise AdmissionError("node_fields", n.id)
            if not n.permissions or any(not isinstance(p, str) or not p for p in n.permissions):
                raise AdmissionError("permissions", n.id)
            if len(n.permissions) != len(set(n.permissions)):
                raise AdmissionError("duplicate_permission", n.id)
        self.nodes, self.rules = tuple(nodes), tuple(rules)
        self.index = MappingProxyType({v: i for i, v in enumerate(ids)})
        self.roots = frozenset(i for i, n in enumerate(nodes) if n.kind == "R")
        byhead, incidence, children = ([[] for _ in nodes] for _ in range(3))
        ruleids, clauses = set(), set()
        for j, r in enumerate(rules):
            if not isinstance(r.id, str) or not r.id or r.id in ruleids:
                raise AdmissionError("duplicate_rule", str(r.id))
            ruleids.add(r.id)
            if r.head not in self.index or any(p not in self.index for p in r.premises):
                raise AdmissionError("dangling_reference", r.id)
            if not r.premises or len(r.premises) != len(set(r.premises)):
                raise AdmissionError("empty_or_duplicate_premises", r.id)
            if r.head in r.premises:
                raise AdmissionError("self_loop", r.id)
            h = self.index[r.head]
            if h in self.roots:
                raise AdmissionError("root_has_justification", r.head)
            key = (r.head, frozenset(r.premises))
            if key in clauses:
                raise AdmissionError("duplicate_justification", r.id)
            clauses.add(key)
            byhead[h].append(j)
            for p in r.premises:
                pi = self.index[p]
                if nodes[pi].created_epoch > nodes[h].created_epoch:
                    raise AdmissionError("future_premise", r.id)
                incidence[pi].append(j)
                children[pi].append(h)
        # Kahn works with duplicate ordinary edges by counting/decrementing each occurrence.
        indegree = [0] * len(nodes)
        for cs in children:
            for h in cs:
                indegree[h] += 1
        queue = deque(i for i, deg in enumerate(indegree) if not deg)
        order = []
        while queue:
            p = queue.popleft()
            order.append(p)
            for h in children[p]:
                indegree[h] -= 1
                if not indegree[h]:
                    queue.append(h)
        if len(order) != len(nodes):
            raise AdmissionError("cycle", "positive support graph must be acyclic")
        self.topological = tuple(order)
        self.byhead = tuple(tuple(x) for x in byhead)
        self.incidence = tuple(tuple(x) for x in incidence)
        self.children = tuple(tuple(x) for x in children)
        self.heads = tuple(self.index[r.head] for r in rules)
        self.parents = tuple(tuple(self.index[p] for p in r.premises) for r in rules)
        self.incidence_count = sum(map(len, self.parents))

    def to_dict(self):
        return {"nodes": [{**asdict(n), "permissions": list(n.permissions)} for n in self.nodes],
                "rules": [{**asdict(r), "premises": list(r.premises)} for r in self.rules]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"nodes", "rules"}:
            raise AdmissionError("graph_schema", "required keys: nodes, rules")
        if not isinstance(value["nodes"], list) or not isinstance(value["rules"], list):
            raise AdmissionError("graph_schema", "nodes and rules must be arrays")
        nodes, rules = [], []
        required = {"id", "text", "kind", "entity", "attribute", "scope", "value", "created_epoch", "permissions"}
        for n in value["nodes"]:
            if not isinstance(n, dict) or set(n) != required or not isinstance(n["permissions"], list):
                raise AdmissionError("node_schema", "node keys/types do not match schema")
            nodes.append(Node(**{**n, "permissions": tuple(n["permissions"])}))
        for r in value["rules"]:
            if not isinstance(r, dict) or set(r) != {"id", "head", "premises"} or not isinstance(r["premises"], list):
                raise AdmissionError("rule_schema", "rule keys/types do not match schema")
            if not all(isinstance(x, str) for x in r["premises"]) or not isinstance(r["head"], str):
                raise AdmissionError("rule_schema", "head and premises must be IDs")
            rules.append(Rule(r["id"], r["head"], tuple(r["premises"])))
        return cls(tuple(nodes), tuple(rules))


def root_vector(graph: Graph, state: dict[str, bool]) -> list[bool]:
    expected = {graph.nodes[i].id for i in graph.roots}
    if not isinstance(state, dict) or set(state) != expected or any(type(v) is not bool for v in state.values()):
        raise AdmissionError("root_state", "explicit Boolean value required for every root, and only roots")
    return [state[n.id] if i in graph.roots else False for i, n in enumerate(graph.nodes)]


def extraction_from_dict(value):
    if not isinstance(value, dict) or set(value) != {"graph", "root_active", "retract", "activate"}:
        raise AdmissionError("extraction_schema", "unexpected or missing output keys")
    graph = Graph.from_dict(value["graph"])
    root_vector(graph, value["root_active"])
    for field in ("retract", "activate"):
        batch = value[field]
        if not isinstance(batch, list) or any(not isinstance(x, str) for x in batch):
            raise AdmissionError("update_schema", field)
        if len(batch) != len(set(batch)) or any(x not in value["root_active"] for x in batch):
            raise AdmissionError("update_target", field)
    if set(value["retract"]) & set(value["activate"]):
        raise AdmissionError("conflicting_update", "one root cannot be activated and retracted in one event")
    return graph
