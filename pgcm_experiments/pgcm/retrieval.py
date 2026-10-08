"""Deterministic exact dense cosine retrieval with explicitly named embeddings."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import re
import numpy as np
from .model import Graph


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    scope: str
    principal: str = "researcher"
    intent: str = "current"
    as_of_epoch: int | None = None


class HashEmbeddings:
    """Offline integration control. This is NOT a pretrained neural embedder."""
    name = "blake2-token-counts-v1"
    def __init__(self, dimensions=256):
        if dimensions < 1:
            raise ValueError("positive embedding dimension required")
        self.dimensions = dimensions

    def encode(self, texts):
        out = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in re.findall(r"\w+", text.casefold()):
                col = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), 'little') % self.dimensions
                out[i, col] += 1
        return out


def normalize(vectors):
    x = np.asarray(vectors, dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("finite matrix required")
    norms = np.linalg.norm(x.astype(np.float64), axis=1, keepdims=True)
    return np.divide(x, norms, out=np.zeros_like(x), where=norms > 0)


class VectorIndex:
    def __init__(self, graph: Graph, vectors, embedding_name: str):
        self.graph = graph
        self.vectors = normalize(vectors)
        if len(self.vectors) != len(graph.nodes) or not embedding_name:
            raise ValueError("one immutable-version vector per graph node required")
        self.embedding_name = embedding_name

    def candidates(self, vector, epoch, limit=None):
        q = normalize(np.asarray(vector).reshape(1, -1))[0]
        if q.shape[0] != self.vectors.shape[1]:
            raise ValueError("query embedding dimension differs from record embedding dimension")
        scores = self.vectors @ q
        visible = [i for i, n in enumerate(self.graph.nodes) if n.created_epoch <= epoch]
        ranked = sorted(visible, key=lambda i: (-float(scores[i]), self.graph.nodes[i].id))
        return ranked if limit is None else ranked[:limit]


def eligible(graph, labels, i, query, epoch):
    n = graph.nodes[i]
    return (n.created_epoch <= epoch and bool(labels[i]) and n.scope == query.scope
            and query.principal in n.permissions)


def retrieve(index: VectorIndex, vector, query: Query, labels, epoch: int, k=5,
             candidate_limit=None, gate=True):
    if k <= 0 or (candidate_limit is not None and candidate_limit < k):
        raise ValueError("k positive; candidate budget must be at least k")
    if len(labels) != len(index.graph.nodes):
        raise ValueError("label vector size")
    if query.intent == "historical" and query.as_of_epoch != epoch:
        raise ValueError("historical intent requires the requested committed epoch")
    candidates = index.candidates(vector, epoch, candidate_limit)
    chosen = [i for i in candidates if not gate or eligible(index.graph, labels, i, query, epoch)][:k]
    return {"candidates": [index.graph.nodes[i].id for i in candidates],
            "context": [index.graph.nodes[i].id for i in chosen], "epoch": epoch,
            "embedding": index.embedding_name, "gate": gate}


def load_precomputed(path, record_ids, query_ids):
    """NPZ IDs bind vectors to immutable records/queries; object pickles forbidden."""
    with np.load(path, allow_pickle=False) as f:
        required = {"record_ids", "record_vectors", "query_ids", "query_vectors", "embedding_name"}
        if set(f.files) != required:
            raise ValueError("NPZ keys do not match the precomputed-vector contract")
        rids, qids = list(map(str, f['record_ids'])), list(map(str, f['query_ids']))
        if len(set(rids)) != len(rids) or len(set(qids)) != len(qids):
            raise ValueError("duplicate vector IDs")
        if set(rids) != set(record_ids) or set(qids) != set(query_ids):
            raise ValueError("vector IDs must exactly match this trace and its queries")
        rv, qv = normalize(f['record_vectors']), normalize(f['query_vectors'])
        if len(rv) != len(rids) or len(qv) != len(qids) or rv.shape[1] != qv.shape[1]:
            raise ValueError("vector shape mismatch")
        ri, qi = {v: i for i, v in enumerate(rids)}, {v: i for i, v in enumerate(qids)}
        name = str(f['embedding_name'].item())
        return rv[[ri[v] for v in record_ids]], {v: qv[qi[v]] for v in query_ids}, name
