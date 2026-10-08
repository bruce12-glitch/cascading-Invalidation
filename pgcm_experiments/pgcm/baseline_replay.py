"""Score ACTUAL exported contexts; does not impersonate a published system."""
from collections import Counter
from pathlib import Path
from .io import read_json,read_jsonl,write_json
from .dataset import load_traces
from .model import Graph
from .experiments import gold_states
from .retrieval import Query,eligible
from .metrics import summarize_counts


def baseline_replay(dataset,contexts,identity,out,k_values=(5,10,20)):
    identity=read_json(identity)
    required=('method','repository','commit','model','embedding','candidate_budget','prompt_sha256','adaptation')
    if any(not isinstance(identity.get(k),str) or not identity[k].strip() for k in required):raise ValueError('baseline identity requires all nonempty provenance fields')
    if identity['method'] in ('pgcm_oracle','local_root_update_control','descendant_pruning_control','no_eligibility_gate'):
        raise ValueError('external identity must distinguish repository implementation from local controls')
    traces=list(load_traces(dataset));emitted={};expected={(t['trace_id'],q['query']['id'],k) for t in traces for q in t['queries'] for k in k_values}
    for row in read_jsonl(contexts):
        key=(row['trace_id'],row['query_id'],row['k'])
        if key not in expected or key in emitted:raise ValueError('unknown/duplicate external context')
        ids=row['context']
        if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)) or len(ids)>row['k']:
            raise ValueError('external contexts require unique known IDs and size <= K')
        emitted[key]=row
    rows=[];missing=0
    for tr in traces:
        g=Graph.from_dict(tr['graph']);states,_,_=gold_states(tr,g)
        for k in k_values:
            c=Counter()
            for spec in tr['queries']:
                q=Query(**spec['query']);key=(tr['trace_id'],q.id,k);row=emitted.get(key)
                view=q.as_of_epoch if q.intent=='historical' else spec['after_epoch']
                if row is not None and row['epoch']!=view:raise ValueError('external context epoch differs from requested view')
                context=row['context'] if row else [];missing+=int(row is None)
                if any(v not in g.index for v in context):raise ValueError('unknown external record ID; map external records by audited semantic versions first')
                if any(g.nodes[g.index[v]].created_epoch>view for v in context):raise ValueError('external export contains future evidence')
                targets={v for v in spec['target_ids'] if eligible(g,states[view],g.index[v],q,view)}
                if q.intent=='historical':continue
                stale=sum(not states[view][g.index[v]] for v in context)
                access=sum(g.nodes[g.index[v]].scope!=q.scope or q.principal not in g.nodes[g.index[v]].permissions for v in context)
                c.update(current_queries=1,leaked_queries=int(stale>0),unsupported_context_records=stale,
                         context_records=len(context),valid_relevant_returned=len(targets&set(context)),
                         valid_relevant_total=len(targets),nonempty_contexts=int(bool(context)),access_violations=access)
            rows.append({'trace_id':tr['trace_id'],'method':identity['method'],'k':k,'counts':dict(c)})
    result={'status':'measured_external_context_replay','identity':identity,'expected_contexts':len(expected),
            'missing_contexts':missing,'summaries':[{'k':k,'metrics':summarize_counts([r for r in rows if r['k']==k])} for k in k_values],
            'limitations':'Caller must export actual pinned-system outputs and independently verify identity and mapping. Missing exports give empty contexts and reduce coverage. CER/CEP unavailable without audited state-transition exports.'}
    write_json(Path(out)/'baseline.json',result);write_json(Path(out)/'baseline_trace_counts.json',rows)
    return result
