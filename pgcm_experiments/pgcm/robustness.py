"""Experiment 5. Pointwise support polarity, not an unjustified CER monotonicity."""
from collections import Counter
import random
from .dataset import load_traces
from .engine import CounterEngine
from .experiments import gold_states
from .io import write_json
from .model import Graph, Rule


def corrupt(g,kind,eta,seed):
    if not 0<=eta<=1:raise ValueError('noise rate outside [0,1]')
    rng=random.Random(seed);rules=[];applied=0;skipped=0
    rank={v:i for i,v in enumerate(g.topological)}
    for r in g.rules:
        if kind=='disjunctive_drop':
            if rng.random()<eta:applied+=1;continue
            ps=r.premises
        elif kind=='conjunctive_drop':
            chosen=[p for p in r.premises if rng.random()<eta]
            if len(chosen)==len(r.premises):
                # Never turn a singleton into an empty, unconditional justification.
                chosen=chosen[:-1];skipped+=1
            ps=tuple(p for p in r.premises if p not in chosen);applied+=len(chosen)
        elif kind=='spurious_conjunction':
            ps=r.premises
            if rng.random()<eta:
                h=g.index[r.head]
                candidates=[n.id for i,n in enumerate(g.nodes) if rank[i]<rank[h] and n.created_epoch<=g.nodes[h].created_epoch and n.id not in ps]
                if candidates:ps=ps+(rng.choice(candidates),);applied+=1
                else:skipped+=1
        else:raise ValueError('unsupported corruption')
        rules.append(Rule(r.id,r.head,ps))
    # Corruption can make two clauses equal; semantic set union removes duplicates.
    seen=set();unique=[]
    for r in rules:
        key=(r.head,frozenset(r.premises))
        if key not in seen:seen.add(key);unique.append(r)
    return Graph(g.nodes,tuple(unique)),applied,skipped


def corruption_experiment(dataset,out,noise=(.05,.15,.30),max_traces=200,seed=20261008):
    totals={(kind,eta):Counter() for kind in ('disjunctive_drop','conjunctive_drop','spurious_conjunction') for eta in noise}
    cases=[]
    for ti,tr in enumerate(load_traces(dataset)):
        if ti>=max_traces:break
        g=Graph.from_dict(tr['graph']);states,_,_=gold_states(tr,g)
        for ci,((kind,eta),c) in enumerate(totals.items()):
            damaged,applied,skipped=corrupt(g,kind,eta,seed+1000*ti+ci)
            m=CounterEngine(damaged,tr['initial_roots'])
            c['applied_perturbations']+=applied;c['skipped_empty_or_unavailable']+=skipped;c['traces']+=1
            for e in range(len(tr['events'])+1):
                if e:
                    ev=tr['events'][e-1];m.change(ev['retract'],ev['activate']);m.verify()
                false_inactive={g.nodes[i].id for i,(gold,pred) in enumerate(zip(states[e],m.active)) if gold and not pred}
                false_active={g.nodes[i].id for i,(gold,pred) in enumerate(zip(states[e],m.active)) if pred and not gold}
                violations=len(false_inactive) if kind=='conjunctive_drop' else len(false_active)
                c['false_inactive']+=len(false_inactive);c['false_active']+=len(false_active)
                c['label_comparisons']+=len(g.nodes);c['polarity_violations']+=violations;c['snapshots']+=1
                cases.append({'trace_id':tr['trace_id'],'epoch':e,'kind':kind,'eta':eta,
                              'false_inactive_ids':sorted(false_inactive),'false_active_ids':sorted(false_active),'polarity_violations':violations})
                if violations:raise RuntimeError('provenance polarity bound violated')
    result={'status':'measured_structural_corruption','conditions':[{'kind':k,'eta':eta,'counts':dict(c)} for (k,eta),c in totals.items()],
            'limitations':'Pointwise comparison to oracle, shared roots. No LLM-induced corruption distribution. Facet collisions are tested as admission errors, not assigned invented leakage rates.'}
    write_json(__import__('pathlib').Path(out)/'corruptions.json',result);write_json(__import__('pathlib').Path(out)/'corruption_cases.json',cases)
    return result
