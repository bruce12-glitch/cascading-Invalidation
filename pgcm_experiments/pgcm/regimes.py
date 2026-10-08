"""Provenance replay regimes. Model calls are deliberately separate from scoring.

Recompile a prefix graph on each event: honest reference for graph growth, not an
incremental structural mutation algorithm. Strict admission fails closed.
"""
from collections import Counter
import gzip
import json
from pathlib import Path
from .dataset import load_traces,prefix_graph
from .experiments import gold_states
from .engine import CounterEngine
from .model import Graph,extraction_from_dict,AdmissionError
from .metrics import align_nodes,summarize_counts
from .retrieval import HashEmbeddings,Query,VectorIndex,retrieve,eligible
from .io import read_jsonl,write_json

REGIMES=('gold_graph_gold_targets','gold_graph_inferred_targets','inferred_graph_inferred_targets')


def evaluate_regimes(dataset,predictions,out,k_values=(5,10,20)):
    traces=list(load_traces(dataset));allowed={(t['trace_id'],e) for t in traces for e in range(len(t['events'])+1)}
    emitted={}
    for row in read_jsonl(predictions):
        key=(row['trace_id'],row['epoch'])
        if key not in allowed or key in emitted:raise ValueError('unknown/duplicate extraction prediction')
        emitted[key]=row
    out=Path(out);out.mkdir(parents=True,exist_ok=True);emb=HashEmbeddings();rows=[];failures=[];state_counts=Counter()
    with gzip.open(out/'regime_contexts.jsonl.gz','wt') as raw:
        for tr in traces:
            gold=Graph.from_dict(tr['graph']);oracle,_,_=gold_states(tr,gold)
            supplied=CounterEngine(gold,tr['initial_roots'])
            histories={r:{} for r in REGIMES};previous_inferred={};current={}
            counts={(r,k):Counter() for r in REGIMES for k in k_values}
            for epoch in range(len(tr['events'])+1):
                prefix=prefix_graph(gold,epoch);mapping={};pg=None
                row=emitted.get((tr['trace_id'],epoch))
                try:
                    if row is None or row.get('status')!='ok':raise AdmissionError('missing_or_failed_prediction','no admitted output')
                    pg=extraction_from_dict(row['output'])
                    if any(n.created_epoch>epoch for n in pg.nodes):raise AdmissionError('future_record','prefix contains future version')
                    mapping=align_nodes(prefix,pg)
                except (AdmissionError,KeyError,TypeError,ValueError) as e:
                    failures.append({'trace_id':tr['trace_id'],'epoch':epoch,'code':e.code if isinstance(e,AdmissionError) else 'invalid_schema'})
                    pg=None
                if epoch:
                    if pg is not None:
                        mapped={op:[mapping[v] for v in row['output'][op]
                            if v in mapping and gold.index[mapping[v]] in gold.roots] for op in ('retract','activate')}
                        supplied.change(**mapped)
                    # No unobserved gold updates supplied to inferred-target regime.
                current['gold_graph_gold_targets']=(gold,oracle[epoch],{n.id:n.id for n in gold.nodes})
                current['gold_graph_inferred_targets']=(gold,supplied.active.copy(),{n.id:n.id for n in gold.nodes})
                if pg is not None:
                    # Preserve admitted states across prefixes by semantic version, even if IDs change.
                    roots={n.id:previous_inferred.get(n.semantic_key,row['output']['root_active'][n.id])
                           for n in pg.nodes if n.kind=='R'}
                    inferred=CounterEngine(pg,roots)
                    inferred.change(row['output']['retract'],row['output']['activate'])
                    previous_inferred={n.semantic_key:inferred.root_values[i] for i,n in enumerate(pg.nodes) if i in pg.roots}
                    current['inferred_graph_inferred_targets']=(pg,inferred.active.copy(),mapping)
                else:
                    # Invalid prefix blocks retrieval at this epoch; prior valid root state is retained for repair.
                    current['inferred_graph_inferred_targets']=None
                for regime in REGIMES:
                    histories[regime][epoch]=current[regime]
                    state=current[regime]
                    predicted_supported=set() if state is None else {state[2][n.id] for i,n in enumerate(state[0].nodes)
                        if state[1][i] and n.created_epoch<=epoch and n.id in state[2]}
                    true_supported={n.id for i,n in enumerate(gold.nodes) if n.created_epoch<=epoch and oracle[epoch][i]}
                    state_counts[regime+'_false_inactive']+=len(true_supported-predicted_supported)
                    state_counts[regime+'_false_active']+=len(predicted_supported-true_supported)
                    state_counts[regime+'_visible_records']+=len(prefix.nodes)
                    state_counts[regime+'_unmatched_predicted_records']+=0 if state is None else sum(n.id not in state[2] for n in state[0].nodes)
                for spec in (s for s in tr['queries'] if s['after_epoch']==epoch):
                    q=Query(**spec['query']);view=q.as_of_epoch if q.intent=='historical' else epoch
                    if view is None or not 0<=view<=epoch:raise ValueError('invalid historical epoch')
                    true_targets={v for v in spec['target_ids'] if eligible(gold,oracle[view],gold.index[v],q,view)}
                    for regime in REGIMES:
                        state=histories[regime][view]
                        if state is not None:
                            g,labels,alignment=state
                            idx=VectorIndex(g,emb.encode([n.text for n in g.nodes]),emb.name)
                            vector=emb.encode([q.text])[0]
                        for k in k_values:
                            context=[] if state is None else retrieve(idx,vector,q,labels,view,k=k,candidate_limit=k)['context']
                            aligned=[] if state is None else [alignment[v] for v in context if v in alignment]
                            unknown=len(context)-len(aligned)
                            stale=sum(not oracle[view][gold.index[v]] for v in aligned)
                            access=sum(gold.nodes[gold.index[v]].scope!=q.scope or q.principal not in gold.nodes[gold.index[v]].permissions for v in aligned)
                            c=counts[(regime,k)]
                            if q.intent!='historical':
                                c.update(current_queries=1,leaked_queries=int(stale>0),unsupported_context_records=stale,
                                         context_records=len(context),valid_relevant_returned=len(true_targets&set(aligned)),
                                         valid_relevant_total=len(true_targets),nonempty_contexts=int(bool(context)),access_violations=access,
                                         unmatched_context_records=unknown,unmatched_queries=int(unknown>0))
                            raw.write(json.dumps({'trace_id':tr['trace_id'],'epoch':epoch,'query_id':q.id,'regime':regime,
                                'k':k,'context':context,'aligned_gold_ids':aligned,'unsupported_count':stale,'unmatched_count':unknown})+'\n')
            for (regime,k),c in counts.items():rows.append({'trace_id':tr['trace_id'],'method':regime,'k':k,'counts':dict(c)})
    summaries=[{'regime':r,'k':k,'metrics':summarize_counts([x for x in rows if x['method']==r and x['k']==k]),
        'unmatched_context_records':sum(x['counts'].get('unmatched_context_records',0) for x in rows if x['method']==r and x['k']==k)}
        for r in REGIMES for k in k_values]
    result={'status':'measured_prediction_replay','summaries':summaries,'state_counts':dict(state_counts),
            'rejected_prefixes':len(failures),'failure_codes':dict(Counter(x['code'] for x in failures)),
            'limitations':'Exact semantic-key matching; unmatched propositions have UNKNOWN gold support and are separately reported, not treated as safe. CER/CEP unavailable in these growing-graph regimes. Prefix graph reconstruction cost is not incremental maintenance latency. Offline hashed embedding control.'}
    write_json(out/'regimes.json',result);write_json(out/'regime_trace_counts.json',rows);write_json(out/'regime_failures.json',failures)
    return result
