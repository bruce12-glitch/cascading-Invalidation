"""SQLite/WAL immutable snapshots and serialized local action admission.

The external-world exactly-once problem is NOT solved by this local protocol.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from time import perf_counter_ns
from .engine import CounterEngine
from .model import Graph


class EpochConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    epoch: int
    active: bytes
    roots: bytes


class SQLiteMemory:
    def __init__(self, path: str | Path, graph: Graph, roots: dict | None = None):
        self.path, self.graph = str(path), graph
        if self.path == ':memory:':
            raise ValueError("use a file: each reader owns a separate connection")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript('''
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS epochs(epoch INTEGER PRIMARY KEY, labels BLOB NOT NULL, roots BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS updates(operation_id TEXT PRIMARY KEY, payload TEXT NOT NULL, epoch INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, required TEXT NOT NULL, principals TEXT NOT NULL, scope TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS action_audit(id INTEGER PRIMARY KEY, action TEXT NOT NULL, epoch INTEGER NOT NULL,
              principal TEXT NOT NULL, executed INTEGER NOT NULL, reason TEXT NOT NULL, required_labels TEXT NOT NULL);
            ''')
            con.execute("BEGIN IMMEDIATE")
            payload = json.dumps(graph.to_dict(), sort_keys=True)
            existing = con.execute("SELECT value FROM metadata WHERE key='graph'").fetchone()
            if existing:
                if existing[0] != payload:
                    raise ValueError("this database belongs to another immutable graph")
            else:
                if roots is None:
                    raise ValueError("initial root values required")
                m = CounterEngine(graph, roots)
                con.execute("INSERT INTO metadata VALUES('graph',?)", (payload,))
                con.execute("INSERT INTO metadata VALUES('epoch','0')")
                con.execute("INSERT INTO epochs VALUES(0,?,?)", (bytes(m.active), bytes(m.root_values)))
            con.commit()

    def connect(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def snapshot(self, epoch=None):
        con = self.connect()
        try:
            con.execute("BEGIN")
            if epoch is None:
                epoch = int(con.execute("SELECT value FROM metadata WHERE key='epoch'").fetchone()[0])
            row = con.execute("SELECT labels,roots FROM epochs WHERE epoch=?", (epoch,)).fetchone()
            if row is None:
                raise KeyError(f"epoch {epoch} is not committed")
            con.commit()
            return Snapshot(epoch, bytes(row[0]), bytes(row[1]))
        finally:
            con.close()

    def transact(self, retract=(), activate=(), *, expected_epoch=None, operation_id=None, before_publish=None):
        off, on = tuple(sorted(set(retract))), tuple(sorted(set(activate)))
        payload = json.dumps({"retract": off, "activate": on}, sort_keys=True)
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            if operation_id is not None:
                prior = con.execute("SELECT payload,epoch FROM updates WHERE operation_id=?", (operation_id,)).fetchone()
                if prior:
                    if prior[0] != payload:
                        raise ValueError("operation ID reused with different contents")
                    con.rollback()
                    return {"epoch": prior[1], "idempotent_retry": True}
            epoch = int(con.execute("SELECT value FROM metadata WHERE key='epoch'").fetchone()[0])
            if expected_epoch is not None and expected_epoch != epoch:
                raise EpochConflict(f"expected epoch {expected_epoch}, actual {epoch}")
            row = con.execute("SELECT roots FROM epochs WHERE epoch=?", (epoch,)).fetchone()
            roots = {n.id: bool(row[0][i]) for i, n in enumerate(self.graph.nodes) if i in self.graph.roots}
            t = perf_counter_ns()
            engine = CounterEngine(self.graph, roots)
            initialization_ns = perf_counter_ns() - t
            change = engine.change(off, on)
            # Hook is only for deterministic concurrency/fault tests, never model-generated.
            if before_publish:
                before_publish()
            t = perf_counter_ns()
            con.execute("INSERT INTO epochs VALUES(?,?,?)", (epoch + 1, bytes(engine.active), bytes(engine.root_values)))
            if operation_id is not None:
                con.execute("INSERT INTO updates VALUES(?,?,?)", (operation_id, payload, epoch + 1))
            con.execute("UPDATE metadata SET value=? WHERE key='epoch'", (str(epoch + 1),))
            con.commit()
            return {"epoch": epoch + 1, "idempotent_retry": False,
                    "invalidated": sorted(change.invalidated), "activated": sorted(change.activated),
                    "incidence_visits": change.visits, "initialization_ns": initialization_ns,
                    "propagation_ns": change.propagation_ns, "commit_ns": perf_counter_ns() - t}
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def register_action(self, action_id, required, principals=("researcher",), scope=None):
        req = tuple(sorted(set(required)))
        if not action_id or not req or any(x not in self.graph.index for x in req) or not principals:
            raise ValueError("registered actions require known nonempty preconditions and authorized principals")
        scopes={self.graph.nodes[self.graph.index[v]].scope for v in req}
        if scope is None:
            if len(scopes)!=1:raise ValueError('action scope must be explicit and all required records must share it')
            scope=next(iter(scopes))
        if not isinstance(scope,str) or not scope or scopes!={scope}:raise ValueError('action precondition scope mismatch')
        payload = (json.dumps(req), json.dumps(tuple(sorted(set(principals)))),scope)
        with closing(self.connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT required,principals,scope FROM actions WHERE id=?", (action_id,)).fetchone()
            if existing and existing != payload:
                raise ValueError("action registration is immutable; use a new action ID")
            con.execute("INSERT OR IGNORE INTO actions VALUES(?,?,?,?)", (action_id, *payload))
            con.commit()

    def dispatch(self, action_id, principal, callback, *, scope=None):
        """Validate against latest epoch and run LOCAL callback under the same write lock.

        Required IDs come from a trusted registry, not from the LLM's tool arguments.
        Do not run blocking external API operations or recursively call this store
        in callback. Distributed admission needs a reservation/coordination protocol.
        """
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            epoch = int(con.execute("SELECT value FROM metadata WHERE key='epoch'").fetchone()[0])
            labels = con.execute("SELECT labels FROM epochs WHERE epoch=?", (epoch,)).fetchone()[0]
            registered = con.execute("SELECT required,principals,scope FROM actions WHERE id=?", (action_id,)).fetchone()
            reasons, required_labels = [], {}
            if not registered:
                reasons.append("unregistered_action")
            else:
                req, principals = map(json.loads, registered[:2])
                registered_scope=registered[2]
                required_labels = {v: bool(labels[self.graph.index[v]]) for v in req}
                if principal not in principals:
                    reasons.append("unauthorized")
                if any(principal not in self.graph.nodes[self.graph.index[v]].permissions for v in req):
                    reasons.append('unauthorized_precondition')
                if scope is not None and scope!=registered_scope:
                    reasons.append('scope_mismatch')
                if not all(required_labels.values()):
                    reasons.append("unsupported_precondition")
                if any(self.graph.nodes[self.graph.index[v]].created_epoch > epoch for v in req):
                    reasons.append("future_precondition")
            executed = False
            if not reasons:
                try:
                    callback()
                    executed = True
                except Exception:
                    reasons.append("callback_failed")
            reason = ";".join(reasons) if reasons else "completed"
            con.execute("INSERT INTO action_audit(action,epoch,principal,executed,reason,required_labels) VALUES(?,?,?,?,?,?)",
                        (action_id, epoch, principal, int(executed), reason, json.dumps(required_labels)))
            con.commit()
            return {"epoch": epoch, "executed": executed, "reason": reason, "required_labels": required_labels}
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()
