"""Experiment 4. Measured CPU wall-clock samples and memory component sizes."""
from __future__ import annotations
import gc
import random
import sys
from collections.abc import Mapping
from dataclasses import fields,is_dataclass
from time import perf_counter_ns
import numpy as np
from .dataset import scalable_graph
from .engine import CounterEngine, full_recompute, eager_retract
from .io import environment,write_json
from pathlib import Path


def deep_size(obj,seen=None):
    seen=set() if seen is None else seen
    if id(obj) in seen:return 0
    seen.add(id(obj));size=sys.getsizeof(obj)
    if isinstance(obj,Mapping):return size+sum(deep_size(k,seen)+deep_size(v,seen) for k,v in obj.items())
    if isinstance(obj,(tuple,list,set,frozenset)):return size+sum(deep_size(v,seen) for v in obj)
    if is_dataclass(obj):return size+sum(deep_size(getattr(obj,f.name),seen) for f in fields(obj))
    if hasattr(obj,'__dict__'):return size+deep_size(obj.__dict__,seen)
    return size


def quantiles(samples):
    x=np.asarray(samples,dtype=float)
    return {'samples':len(samples),'median_ms':float(np.median(x)/1e6),'p95_ms':float(np.quantile(x,.95)/1e6),
            'min_ms':float(x.min()/1e6),'max_ms':float(x.max()/1e6)}


def scalability_experiment(out,sizes=(100,1000,10000,100000),batches=(1,5,25,100),densities=(3,6),depths=(5,),repeats=7,seed=20261008):
    if repeats<1:raise ValueError('positive repetition count')
    rows,raw,skipped=[],[],[]
    for n in sizes:
        for density in densities:
            for depth in depths:
                start=perf_counter_ns();g,roots=scalable_graph(n,density,seed+n+density+depth,depth)
                build_ns=perf_counter_ns()-start
                start=perf_counter_ns();base=CounterEngine(g,roots);initialization_ns=perf_counter_ns()-start
                root_ids=sorted(roots)
                for qsize in batches:
                    if qsize>len(root_ids):
                        skipped.append({'n':n,'density':density,'depth':depth,'batch':qsize,'reason':'fewer roots than requested batch'})
                        continue
                    samples={m:[] for m in ('counter','full_recompute','eager_rescan')};visits=[];changed=[]
                    # Explicit warm-up from the same pre-update state, excluded from measurements.
                    warm=base.clone();warm.change(retract=root_ids[:qsize]);warm.verify()
                    for repetition in range(repeats):
                        batch=random.Random(seed+repetition+qsize).sample(root_ids,qsize)
                        newroots=base.root_values.copy()
                        for v in batch:newroots[g.index[v]]=False
                        method_order=list(samples);random.Random(seed+repetition).shuffle(method_order)
                        outputs={};counts={}
                        for method in method_order:
                            # Construct private state BEFORE the timed propagation operation.
                            candidate=base.clone() if method=='counter' else None
                            gc.collect()
                            t=perf_counter_ns()
                            if method=='counter':
                                ch=candidate.change(retract=batch);labels=candidate.active;count=ch.visits
                            elif method=='full_recompute':labels,count=full_recompute(g,newroots)
                            else:labels,count=eager_retract(g,base.active,batch)
                            ns=perf_counter_ns()-t
                            samples[method].append(ns);outputs[method]=labels;counts[method]=count
                            raw.append({'n':n,'density':density,'depth':depth,'batch_size':qsize,'batch_ids':batch,
                                        'method':method,'repetition':repetition,'wall_ns':ns,'premise_visits_or_scans':count})
                        if not outputs['counter']==outputs['full_recompute']==outputs['eager_rescan']:
                            raise RuntimeError('timed methods disagree')
                        visits.append(counts['counter']);changed.append(sum(a and not b for a,b in zip(base.active,outputs['counter'])))
                    rows.append({'n':n,'rules':len(g.rules),'incidences':g.incidence_count,'density_requested':density,
                                 'depth':depth,'batch_size':qsize,'initialization_ms':initialization_ns/1e6,'graph_compile_ms':build_ns/1e6,
                                 'latencies':{m:quantiles(v) for m,v in samples.items()},
                                 'counter_work_ratio_mean':float(np.mean(visits)/g.incidence_count),
                                 'mean_changed_records':float(np.mean(changed)),
                                 'unique_graph_and_engine_bytes':deep_size(base),
                                 'memory_bytes_components':{'label_list':deep_size(base.active),'missing_counters':deep_size(base.missing),
                                                          'live_counters':deep_size(base.live),'inverse_incidences':deep_size(g.incidence),
                                                          'premise_arrays':deep_size(g.parents)},
                                 'memory_accounting':'Components measured separately and can share referents; do not add them as a unique total.'})
                del base,g;gc.collect()
    result={'status':'measured_wall_clock','environment':environment(),'seed':seed,'repeats':repeats,'rows':rows,'skipped':skipped,
            'limitations':'Single-process in-memory propagation. End-to-end extraction/generation latency is unavailable without model runs. Snapshot rebuilding and graph compilation reported separately.'}
    write_json(Path(out)/'scalability.json',result);write_json(Path(out)/'scalability_samples.json',raw)
    return result


def affected_region_experiment(out,sizes=(1000,10000,100000),repeats=5,seed=20261008):
    """Dense affected-region control: every derived support requires one shared root.

    Contrasts with random sparse-withdrawal graphs; no universal speedup claim.
    """
    from .model import Graph,Rule
    rows=[];raw=[]
    for n in sizes:
        base_graph,roots=scalable_graph(n,3,seed+n,5)
        # Strengthen every clause with the shared root, preserving acyclicity.
        rules=tuple(Rule(r.id,r.head,tuple(dict.fromkeys(('0',)+r.premises))) for r in base_graph.rules)
        graph=Graph(base_graph.nodes,rules);base=CounterEngine(graph,roots)
        target_roots=base.root_values.copy();target_roots[graph.index['0']]=False
        samples={m:[] for m in ('counter','full_recompute','eager_rescan')};visits=[];changed=[]
        warm=base.clone();warm.change(retract=['0']);warm.verify()
        for repetition in range(repeats):
            order=list(samples);random.Random(seed+repetition).shuffle(order);outputs={}
            for method in order:
                candidate=base.clone() if method=='counter' else None
                gc.collect();start=perf_counter_ns()
                if method=='counter':
                    change=candidate.change(retract=['0']);labels=candidate.active;work=change.visits
                    visits.append(work);changed.append(len(change.invalidated))
                elif method=='full_recompute':labels,work=full_recompute(graph,target_roots)
                else:labels,work=eager_retract(graph,base.active,['0'])
                ns=perf_counter_ns()-start;samples[method].append(ns);outputs[method]=labels
                raw.append({'n':n,'repetition':repetition,'method':method,'wall_ns':ns,'premise_visits_or_scans':work})
            if not outputs['counter']==outputs['full_recompute']==outputs['eager_rescan']:raise RuntimeError('dense affected-region methods disagree')
            if sum(not x for x in outputs['counter'])!=len(graph.nodes)-len(graph.roots)+1:raise RuntimeError('shared-root control did not invalidate all derived records')
        rows.append({'n':n,'roots':len(graph.roots),'rules':len(graph.rules),'incidences':graph.incidence_count,
            'mean_changed_records':float(np.mean(changed)),'counter_work_ratio_mean':float(np.mean(visits)/graph.incidence_count),
            'latencies':{method:quantiles(s) for method,s in samples.items()}})
    result={'status':'measured_dense_affected_region','rows':rows,'repeats':repeats,
        'limitations':'A shared mandatory root is present in every sufficient clause. This is a controlled worst-affected-region topology, not a linguistic or deployment distribution.'}
    write_json(Path(out)/'affected_region.json',result);write_json(Path(out)/'affected_region_samples.json',raw)
    return result
