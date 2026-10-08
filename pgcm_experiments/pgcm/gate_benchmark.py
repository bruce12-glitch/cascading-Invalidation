"""Isolated eligibility-filter overhead; vectors, ANN and model time excluded."""
import random
from pathlib import Path
from time import perf_counter_ns
from .dataset import scalable_graph
from .engine import CounterEngine
from .retrieval import Query,eligible
from .performance import quantiles
from .io import write_json


def gate_benchmark(out,sizes=(100,1000,10000,100000),budgets=(5,10,20),repeats=100,seed=20261008):
    rows=[]
    for n in sizes:
        graph,roots=scalable_graph(n,3,seed+n,5)
        state=CounterEngine(graph,roots)
        root_ids=sorted(roots);state.change(retract=root_ids[:max(1,len(root_ids)//4)]);state.verify()
        q=Query('gate','eligibility microbenchmark','scale')
        for budget in budgets:
            if budget>n:continue
            rng=random.Random(seed+n+budget)
            candidates=[rng.sample(range(n),budget) for _ in range(repeats)]
            oracle=[[i for i in ids if eligible(graph,state.active,i,q,0)] for ids in candidates]
            samples=[]
            for ids,expected in zip(candidates,oracle):
                t=perf_counter_ns();result=[i for i in ids if eligible(graph,state.active,i,q,0)];samples.append(perf_counter_ns()-t)
                if result!=expected:raise RuntimeError('eligibility result changed')
            rows.append({'n':n,'candidate_budget':budget,'latency':quantiles(samples),'total_filtered_candidates':budget*repeats})
    result={'status':'measured_isolated_filter','rows':rows,
            'limitations':'Microbenchmark of Python eligibility predicates over preselected candidates, excluded ranking/vector/database/model costs; not end-to-end query latency.'}
    write_json(Path(out)/'gate_overhead.json',result)
    return result
