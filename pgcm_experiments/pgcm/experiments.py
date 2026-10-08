"""Experiments 1-3: replayable measurements, not synthetic target numbers."""
from __future__ import annotations
from collections import Counter
from dataclasses import replace
import gzip
import json
from pathlib import Path
import tempfile
from time import perf_counter_ns
from .dataset import load_traces, prefix_graph
from .engine import CounterEngine, descendant_retract, full_recompute
from .io import read_jsonl, write_json
from .metrics import align_nodes, extraction_counts, sum_extraction, summarize_counts, paired_bootstrap
from .model import AdmissionError, Graph, extraction_from_dict
from .retrieval import HashEmbeddings, Query, VectorIndex, retrieve, eligible, load_precomputed
from .store import SQLiteMemory


METHODS=('pgcm_oracle','local_root_update_control','descendant_pruning_control','no_eligibility_gate')


def extraction_experiment(dataset,predictions,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    traces={t['trace_id']:t for t in load_traces(dataset)}
    emitted={}
    allowed={(tid,e) for tid,tr in traces.items() for e in range(len(tr['events'])+1)}
    for row in read_jsonl(predictions):
        key=(row['trace_id'],row['epoch'])
        if key in emitted or key not in allowed:raise ValueError('duplicate or unknown prediction key')
        emitted[key]=row
    valid,failures=[],[]
    expected=0
    for tid,tr in traces.items():
        full=Graph.from_dict(tr['graph'])
        for e in range(len(tr['events'])+1):
            expected+=1;row=emitted.get((tid,e))
            gold=prefix_graph(full,e)
            updates=tr['events'][e-1] if e else {'retract':[],'activate':[]}
            try:
                if row is None:raise AdmissionError('missing_prediction',tid)
                if row.get('status')!='ok':raise AdmissionError('provider_failure',str(row.get('error','missing status')))
                pred=extraction_from_dict(row['output'])
                if any(n.created_epoch>e for n in pred.nodes):raise AdmissionError('future_record','prediction uses a later epoch')
                valid.append(extraction_counts(gold,pred,updates,row['output']))
            except (AdmissionError,KeyError,TypeError,ValueError) as error:
                code=error.code if isinstance(error,AdmissionError) else 'invalid_schema'
                failures.append({'trace_id':tid,'epoch':e,'code':code})
                # Failure means zero recovered gold facts/edges/updates. No survivorship bias.
                counts={k:[0,0,sum(n.kind==k for n in gold.nodes)] for k in ('R','D','A')}
                multi={r.head for r in gold.rules if sum(s.head==r.head for s in gold.rules)>1}
                valid.append({'node_classes':counts,'scoped_key_match':[0,len(gold.nodes)],
                              'hyperedges':[0,0,len(gold.rules)],
                              'alternative_clause_recall':[0,sum(r.head in multi for r in gold.rules)],
                              'alternative_head_exact':[0,len(multi)],
                              'retract':[0,0,len(updates['retract'])],'activate':[0,0,len(updates['activate'])]})
    if len(emitted)>expected:raise ValueError('predictions contain extra epochs')
    result={'status':'measured_replay','expected_attempts':expected,'failed_attempts':len(failures),
            'failure_codes':dict(Counter(f['code'] for f in failures)),
            'admission_rejection_rate':len(failures)/expected,'metrics':sum_extraction(valid),
            'limitations':'Exact semantic-key alignment; unaligned records count as missing/extra. Human proposition matching is not implemented.'}
    write_json(out/'extraction.json',result);write_json(out/'extraction_failures.json',failures)
    return result


def gold_states(tr,g):
    m=CounterEngine(g,tr['initial_roots']);states={0:m.active.copy()};root_states={0:m.root_values.copy()}
    changes={}
    for event in tr['events']:
        ch=m.change(event['retract'],event['activate']);m.verify()
        states[event['epoch']]=m.active.copy();root_states[event['epoch']]=m.root_values.copy();changes[event['epoch']]=ch
    return states,root_states,changes


def propagate_activation(g,flags,batch):
    from collections import deque
    q=deque()
    for r in batch:
        i=g.index[r]
        if not flags[i]:flags[i]=True;q.append(i)
    while q:
        u=q.popleft()
        for h in set(g.children[u]):
            if not flags[h] and any(all(flags[p] for p in g.parents[j]) for j in g.byhead[h]):
                flags[h]=True;q.append(h)


def retrieval_experiment(dataset,out,k_values=(5,10,20),bootstrap_replicates=10000,seed=20261008,vectors_dir=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    emb=HashEmbeddings();trace_rows=[];query_count=0
    rawpath=out/'retrieval_queries.jsonl.gz'
    with gzip.open(rawpath,'wt') as raw:
        for tr in load_traces(dataset):
            g=Graph.from_dict(tr['graph']);states,root_states,changes=gold_states(tr,g)
            queries={r['query']['id']:Query(**r['query']) for r in tr['queries']}
            if vectors_dir:
                vectors,qvectors,name=load_precomputed(Path(vectors_dir)/(tr['trace_id']+'.npz'),[n.id for n in g.nodes],list(queries))
            else:
                vectors=emb.encode([n.text for n in g.nodes]);qvectors={id:emb.encode([q.text])[0] for id,q in queries.items()};name=emb.name
            index=VectorIndex(g,vectors,name)
            approx={m:states[0].copy() for m in METHODS}
            histories={m:{0:states[0].copy()} for m in METHODS}
            counters={(k,m):Counter() for k in k_values for m in METHODS}
            for event in tr['events']:
                e=event['epoch'];gold=states[e]
                previous_approx={m:flags.copy() for m,flags in approx.items()}
                local=approx['local_root_update_control']
                for r in event['retract']:local[g.index[r]]=False
                for r in event['activate']:local[g.index[r]]=True
                for i,n in enumerate(g.nodes):
                    if n.created_epoch==e:local[i]=gold[i]  # same admitted new-record labels for controls
                reach=descendant_retract(g,approx['descendant_pruning_control'],event['retract'])
                propagate_activation(g,reach,event['activate'])
                approx['descendant_pruning_control']=reach
                approx['pgcm_oracle']=gold
                approx['no_eligibility_gate']=gold
                for method in METHODS:histories[method][e]=approx[method].copy()
                old=states[e-1]
                goldcascade={i for i in range(len(g.nodes)) if i not in g.roots and old[i] and not gold[i]}
                for k in k_values:
                    for method in METHODS:
                        # Current state maintenance, not exclusion from a TopK candidate set.
                        predicted={i for i in range(len(g.nodes)) if i not in g.roots and previous_approx[method][i] and not approx[method][i]}
                        c=counters[(k,method)]
                        c['cascade_tp']+=len(predicted&goldcascade);c['cascade_gold']+=len(goldcascade);c['cascade_predicted']+=len(predicted)
                for spec in [s for s in tr['queries'] if s['after_epoch']==e]:
                    q=queries[spec['query']['id']];view=q.as_of_epoch if q.intent=='historical' else e
                    if view is None or view<0 or view>e:raise ValueError('unavailable historical epoch')
                    for k in k_values:
                        for method in METHODS:
                            labels=histories[method][view] if q.intent=='historical' else approx[method]
                            t=perf_counter_ns()
                            result=retrieve(index,qvectors[q.id],q,labels,view,k=k,candidate_limit=k,
                                            gate=method!='no_eligibility_gate')
                            gate_and_retrieval_ns=perf_counter_ns()-t
                            context=result['context'];inds=[g.index[x] for x in context]
                            oracle=states[view]
                            stale=sum(not oracle[i] for i in inds)
                            valid_targets={v for v in spec['target_ids'] if eligible(g,oracle,g.index[v],q,view)}
                            access=sum(g.nodes[i].scope!=q.scope or q.principal not in g.nodes[i].permissions for i in inds)
                            c=counters[(k,method)]
                            if q.intent!='historical':
                                c.update({'current_queries':1,'leaked_queries':int(stale>0),'unsupported_context_records':stale,
                                          'context_records':len(context),'valid_relevant_returned':len(valid_targets&set(context)),
                                          'valid_relevant_total':len(valid_targets),'nonempty_contexts':int(bool(context)),
                                          'access_violations':access})
                            else:
                                c['historical_queries']+=1;c['historical_valid_returned']+=len(valid_targets&set(context));c['historical_valid_total']+=len(valid_targets)
                            raw.write(json.dumps({'trace_id':tr['trace_id'],'epoch':e,'query_id':q.id,'probe':spec['probe'],
                                                  'method':method,'k':k,'context':context,'candidate_ids':result['candidates'],
                                                  'unsupported_count':stale,'valid_target_ids':sorted(valid_targets),
                                                  'retrieval_and_gate_ns':gate_and_retrieval_ns,'embedding':name},allow_nan=False)+'\n')
                            query_count+=1
            for (k,method),c in counters.items():
                trace_rows.append({'trace_id':tr['trace_id'],'domain':tr['domain'],'k':k,'method':method,'counts':dict(c)})
    summaries=[];bootstrap=[]
    for k in k_values:
        for method in METHODS:
            summaries.append({'k':k,'method':method,'metrics':summarize_counts([r for r in trace_rows if r['k']==k and r['method']==method])})
        subset=[r for r in trace_rows if r['k']==k]
        for control in METHODS[1:]:
            for metric in ('CLR','VER'):
                b=paired_bootstrap(subset,'pgcm_oracle',control,metric,bootstrap_replicates,seed)
                bootstrap.append({'k':k,**b})
    result={'status':'measured_synthetic_integration','trace_count':len({r['trace_id'] for r in trace_rows}),
            'query_method_k_evaluations':query_count,'embedding':name,'candidate_budget':'K, no refill',
            'summaries':summaries,'limitations':'Generated explicit-rule fixtures, supplied provenance, exact cosine search. Controls are not MemGPT, Zep, A-MEM, PACMI, or MemTX.'}
    write_json(out/'retrieval.json',result);write_json(out/'retrieval_trace_counts.json',trace_rows);write_json(out/'paired_bootstrap.json',bootstrap)
    return result


def action_experiment(dataset,out,max_traces=200):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    audits=[];c=Counter()
    with tempfile.TemporaryDirectory() as temp:
        for t,tr in enumerate(load_traces(dataset)):
            if t>=max_traces:break
            g=Graph.from_dict(tr['graph']);states,_,_=gold_states(tr,g)
            store=SQLiteMemory(Path(temp)/f'{t}.db',g,tr['initial_roots'])
            for a in tr['actions']:store.register_action(a['id'],a['required'],a['principals'])
            for e in range(len(tr['events'])+1):
                if e:
                    event=tr['events'][e-1];store.transact(event['retract'],event['activate'])
                for a in tr['actions']:
                    supported=all(states[e][g.index[v]] for v in a['required'])
                    side_effects=[]
                    result=store.dispatch(a['id'],'researcher',lambda:side_effects.append('local_completion'))
                    c['attempts']+=1;c['eligible_attempts']+=int(supported);c['ineligible_attempts']+=int(not supported)
                    c['permitted_completed']+=int(supported and result['executed']);c['forbidden_executed']+=int(not supported and result['executed'])
                    if result['executed']!=bool(side_effects):raise RuntimeError('audit/effect mismatch')
                    audits.append({'trace_id':tr['trace_id'],'oracle_permit':supported,**result})
            c['traces']+=1
    result={'status':'measured_local_action_control','counts':dict(c),
            'forbidden_execution_rate':c['forbidden_executed']/c['ineligible_attempts'] if c['ineligible_attempts'] else None,
            'permitted_completion_rate':c['permitted_completed']/c['eligible_attempts'] if c['eligible_attempts'] else None,
            'limitations':'Scripted proposals and in-process side effects; no live LLM reasoning or remote API tool dispatch.'}
    write_json(out/'actions.json',result);write_json(out/'action_audits.json',audits)
    return result


def qa_replay(dataset,contexts,predictions,out,k=5,method='pgcm_oracle'):
    traces={t['trace_id']:t for t in load_traces(dataset)}
    requests={}
    for row in read_jsonl(contexts):
        if row['k']==k and row['method']==method:
            key=(row['trace_id'],row['query_id'])
            if key in requests:raise ValueError('duplicate context key')
            requests[key]=row
    responses={}
    for row in read_jsonl(predictions):
        key=(row['trace_id'],row['query_id'])
        if key in responses or key not in requests:raise ValueError('duplicate or unknown QA prediction')
        responses[key]=row
    rows=[];counts=Counter()
    for key,ctx in requests.items():
        tr=traces[key[0]];g=Graph.from_dict(tr['graph']);spec=next(q for q in tr['queries'] if q['query']['id']==key[1])
        targets=set(ctx['valid_target_ids'])
        expected='reject_premise' if spec['probe']=='stale_premise' else 'answer' if targets else 'abstain'
        pred=responses.get(key,{});answer=pred.get('output',{})
        valid=(pred.get('status')=='ok' and isinstance(answer,dict) and set(answer)=={'decision','evidence_ids','answer'}
               and answer.get('decision') in ('answer','abstain','reject_premise')
               and isinstance(answer.get('evidence_ids'),list) and isinstance(answer.get('answer'),str))
        evidence=answer.get('evidence_ids',[]) if valid else []
        valid=valid and all(isinstance(v,str) and v in ctx['context'] for v in evidence)
        valid=valid and len(evidence)==len(set(evidence))
        correct=bool(valid and answer['decision']==expected and
                     (expected!='answer' or bool(targets&set(evidence))))
        counts['total']+=1;counts['correct_structured_behavior']+=int(correct);counts['invalid_or_missing']+=int(not valid)
        if expected=='abstain':counts['abstention_cases']+=1;counts['appropriate_abstentions']+=int(correct)
        if expected=='reject_premise':counts['stale_premise_cases']+=1;counts['correct_rejections']+=int(correct)
        if expected=='answer':counts['answerable_cases']+=1;counts['false_abstentions']+=int(valid and answer['decision']=='abstain')
        rows.append({'trace_id':key[0],'query_id':key[1],'expected':expected,'correct':correct,'output_valid':valid})
    result={'status':'measured_model_output_replay','counts':dict(counts),
            'structured_behavior_accuracy':counts['correct_structured_behavior']/counts['total'] if counts['total'] else None,
            'limitations':'Decision/evidence scoring is not a full factual correctness judge of free-form answer text. Independently adjudicate human QA correctness.'}
    write_json(Path(out)/'qa.json',result);write_json(Path(out)/'qa_cases.json',rows)
    return result
