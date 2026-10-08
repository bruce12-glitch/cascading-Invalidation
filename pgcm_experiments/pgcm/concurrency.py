"""Forced interleavings and stress. They are local protocol experiments."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
from pathlib import Path
from time import perf_counter_ns
from .dataset import scalable_graph,fixture
from .engine import full_recompute,CounterEngine
from .model import Graph
from .store import SQLiteMemory
from .io import write_json


def concurrency_experiment(out,writes=100,reads_per_worker=200,readers=4):
    g,roots=scalable_graph(100,3,depth=5)
    with tempfile.TemporaryDirectory() as tmp:
        store=SQLiteMemory(Path(tmp)/'atomic.db',g,roots)
        ids=list(roots);start_barrier=threading.Barrier(readers+1)
        def writer():
            start_barrier.wait()
            timings=[]
            for i in range(writes):
                timings.append(store.transact(retract=[ids[i%len(ids)]] if i%2==0 else [],activate=[ids[i%len(ids)]] if i%2 else []))
            return timings
        def reader():
            start_barrier.wait();violations=0;epochs=[]
            for _ in range(reads_per_worker):
                snap=store.snapshot();gold,_=full_recompute(g,list(map(bool,snap.roots)))
                violations+=int(bytes(gold)!=snap.active);epochs.append(snap.epoch)
            return violations,epochs
        t=perf_counter_ns()
        with ThreadPoolExecutor(max_workers=readers+1) as pool:
            w=pool.submit(writer);rs=[pool.submit(reader) for _ in range(readers)]
            timings=w.result();observed=[r.result() for r in rs]
        elapsed=(perf_counter_ns()-t)/1e9
        violations=sum(v for v,_ in observed)
        if violations:raise RuntimeError('committed snapshot invariant violation')
        # Force a writer to pause before publishing and observe the OLD committed epoch.
        reached,release=threading.Event(),threading.Event()
        def pause():
            reached.set()
            if not release.wait(5):raise TimeoutError('test scheduler')
        before=store.snapshot()
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut=pool.submit(store.transact,retract=[ids[0]],before_publish=pause)
            if not reached.wait(5):raise TimeoutError('writer not staged')
            during=store.snapshot();release.set();fut.result()
        if during!=before:raise RuntimeError('unpublished state exposed')
        # Deliberately UNSAFE ablation: root changed before derived labels are updated.
        witness=fixture(0);wg=Graph.from_dict(witness['graph'])
        initial=CounterEngine(wg,witness['initial_roots'])
        hybrid=initial.active.copy();hybrid[wg.index['old']]=False
        newroots=initial.root_values.copy();newroots[wg.index['old']]=False
        oracle,_=full_recompute(wg,newroots)
        unsafe_mismatches=sum(a!=b for a,b in zip(hybrid,oracle))
        if not unsafe_mismatches:raise RuntimeError('unsafe publication control was not load-bearing')
    result={'status':'measured_local_concurrency','reader_snapshots':readers*reads_per_worker,'write_transactions':writes,
            'committed_snapshot_violations':violations,'wall_seconds':elapsed,
            'combined_operations_per_second':(readers*reads_per_worker+writes)/elapsed,
            'write_transactions_per_second_during_run':writes/elapsed,
            'old_epoch_visible_during_staged_write':during.epoch==before.epoch,
            'unsafe_forced_partial_publication_mismatched_labels':unsafe_mismatches,
            'write_timing_records':timings,
            'limitations':'SQLite/WAL on one host, bounded reads/writes; unsafe case is a forced partial-state observation, not a measured stochastic failure rate.'}
    write_json(Path(out)/'concurrency.json',result)
    return result
