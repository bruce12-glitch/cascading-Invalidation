"""Optional live model callers and replayable outputs.

No automatic live calls in the offline pipeline. No secret headers are logged.
Tool schemas constrain structure; admission remains an independent local check.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter_ns
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from .dataset import load_traces
from .io import read_json,read_jsonl
from .model import strict_json


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


STR={'type':'string'};STRINGS={'type':'array','items':STR}
NODE_SCHEMA=object_schema({'id':STR,'text':STR,'kind':{'type':'string','enum':['R','D','A']},
    'entity':STR,'attribute':STR,'scope':STR,'value':STR,'created_epoch':{'type':'integer','minimum':0},'permissions':STRINGS})
RULE_SCHEMA=object_schema({'id':STR,'head':STR,'premises':{'type':'array','items':STR,'minItems':1}})
EXTRACTION_SCHEMA=object_schema({'graph':object_schema({'nodes':{'type':'array','items':NODE_SCHEMA},'rules':{'type':'array','items':RULE_SCHEMA}}),
    'root_active':{'type':'object','additionalProperties':{'type':'boolean'}},'retract':STRINGS,'activate':STRINGS})
QA_SCHEMA=object_schema({'decision':{'type':'string','enum':['answer','abstain','reject_premise']},'evidence_ids':STRINGS,'answer':STR})


EXTRACTION_SYSTEM='''Extract a versioned positive justification memory from the supplied dialogue prefix only.
Return the result through emit_result. Do not invent premises or include future turns.
Use stable IDs of your choice. Record kind R is an observation or declared policy;
D is a derived record; A is an action precondition. A justification is one sufficient
AND set. Distinct sufficient alternatives must be separate rules with the same head.
Record entity, attribute, operational scope, value and creation epoch explicitly.
Preserve superseded versions rather than overwriting their text. All nodes mentioned
at or before the current epoch should be retained. Set root_active to the CURRENT
Boolean admission status of every R node. Set retract and activate to ROOT IDs
affected by ONLY the latest event (both empty at epoch 0). Unsupported is not false.
The input epochs are transaction-order epochs, not event-time dates. Include all
required policy and permission premises. Scope is the explicitly supplied namespace.
Default authorized reader is researcher; explicitly confidential records are admin-only.
Do not merge auxiliary scope with the primary scope. Reject unsupported semantic
assumptions rather than interpreting topical similarity as logical implication.'''

QA_SYSTEM='''Answer the current query using only the supplied eligible evidence.
Emit decision answer, abstain, or reject_premise. Identify evidence record IDs used.
Historical evidence is labeled with its requested epoch and must not be treated as
current. If the context lacks sufficient evidence, abstain. Reject an outdated premise
only when supported by available evidence. Do not invent source IDs. Return emit_result.'''


class JsonProvider:
    def __init__(self,config,transport=None):
        self.config=dict(config);self.transport=transport
        if config['provider'] not in ('openai_compatible','anthropic','command'):raise ValueError('unknown provider')
        if config['provider']!='command' and (not config.get('model') or config['model'].startswith('SET_')):
            raise ValueError('configure an exact available model ID')

    def request_payload(self,system,user,schema):
        c=self.config
        if c['provider']=='openai_compatible':
            tool={'type':'function','function':{'name':'emit_result','description':'Emit the requested JSON experiment output.',
                                              'parameters':schema,'strict':False}}
            payload={'model':c['model'],'messages':[{'role':'system','content':system},{'role':'user','content':user}],
                     'tools':[tool],'tool_choice':{'type':'function','function':{'name':'emit_result'}},
                     c.get('token_parameter','max_completion_tokens'):c.get('max_tokens',4096)}
        elif c['provider']=='anthropic':
            payload={'model':c['model'],'system':system,'messages':[{'role':'user','content':user}],
                     'max_tokens':c.get('max_tokens',4096),
                     'tools':[{'name':'emit_result','description':'Emit the requested JSON output.','input_schema':schema}],
                     'tool_choice':{'type':'tool','name':'emit_result'}}
        else:return {'system':system,'user':user,'schema':schema}
        if 'temperature' in c:payload['temperature']=c['temperature']
        if c.get('extra_body'):
            collision=set(payload)&set(c['extra_body'])
            if collision:raise ValueError('extra_body overwrites controlled request fields')
            payload.update(c['extra_body'])
        return payload

    def call(self,system,user,schema):
        body=self.request_payload(system,user,schema);start=perf_counter_ns();c=self.config
        if c['provider']=='command':
            argv=c.get('command')
            if not isinstance(argv,list) or not argv or any(not isinstance(v,str) for v in argv):raise ValueError('command must be an argv array; shell execution is disabled')
            p=subprocess.run(argv,input=json.dumps(body),capture_output=True,text=True,timeout=c.get('timeout_seconds',120),check=False)
            if p.returncode:raise RuntimeError(f'provider command failed with exit code {p.returncode}')
            response=strict_json(p.stdout);output=response['output'];usage=response.get('usage',{})
        else:
            if self.transport:
                response=self.transport(body)
            else:
                env=c.get('api_key_env','OPENAI_API_KEY' if c['provider']=='openai_compatible' else 'ANTHROPIC_API_KEY')
                key=os.environ.get(env)
                if not key:raise RuntimeError(f'missing credential environment variable {env}')
                endpoint=c.get('endpoint','https://api.openai.com/v1/chat/completions' if c['provider']=='openai_compatible' else 'https://api.anthropic.com/v1/messages')
                headers={'Content-Type':'application/json'}
                if c['provider']=='openai_compatible':headers['Authorization']='Bearer '+key
                else:headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
                req=Request(endpoint,data=json.dumps(body).encode(),headers=headers,method='POST')
                try:
                    with urlopen(req,timeout=c.get('timeout_seconds',120)) as r:response=strict_json(r.read().decode())
                except HTTPError as e:raise RuntimeError(f'provider HTTP status {e.code}; response body not logged') from None
                except URLError:raise RuntimeError('provider connection failed') from None
            if c['provider']=='openai_compatible':
                choice=response['choices'][0]
                if choice['finish_reason'] in ('length','content_filter'):raise ValueError('truncated or filtered model output')
                calls=choice['message'].get('tool_calls',[])
                if len(calls)!=1 or calls[0]['function']['name']!='emit_result':raise ValueError('expected one emit_result tool call')
                output=strict_json(calls[0]['function']['arguments'])
            else:
                if response.get('stop_reason')=='max_tokens':raise ValueError('truncated model output')
                calls=[b for b in response['content'] if b['type']=='tool_use']
                if len(calls)!=1 or calls[0]['name']!='emit_result':raise ValueError('expected one emit_result tool use')
                output=calls[0]['input']
            usage=response.get('usage',{})
        if not isinstance(output,dict):raise ValueError('provider output must be a JSON object')
        return {'output':output,'latency_ns':perf_counter_ns()-start,'usage':usage,
                'provider':c['provider'],'model':c.get('model','external-command'),
                'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()}


def collect_extractions(dataset,config,out,examples=None,max_requests=None):
    provider=JsonProvider(read_json(config));traces=list(load_traces(dataset))
    demonstration=read_json(examples) if examples else []
    if examples and (not isinstance(demonstration,list) or len(demonstration)!=3):raise ValueError('3-shot file must contain exactly three examples')
    if any(ex['trace_id'] in {t['trace_id'] for t in traces} for ex in demonstration):raise ValueError('demonstration overlaps evaluated trace IDs')
    fingerprint=hashlib.sha256(json.dumps({'config':provider.config,'dataset_sha256':hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),'demonstrations':demonstration,
        'system':EXTRACTION_SYSTEM,'schema':EXTRACTION_SCHEMA},sort_keys=True).encode()).hexdigest()
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);seen=set()
    if out.exists():
        for row in read_jsonl(out):
            key=(row['trace_id'],row['epoch'])
            if key in seen:raise ValueError('duplicate cached prediction key')
            if row.get('provider')!=provider.config['provider'] or row.get('model')!=provider.config.get('model','external-command'):
                raise ValueError('cache belongs to another provider/model; choose a new output path')
            if row.get('configuration_sha256')!=fingerprint:
                raise ValueError('cache prompt/configuration mismatch; choose a new output path')
            seen.add(key)
    completed=0
    with out.open('a') as f:
        for tr in traces:
            for epoch in range(len(tr['events'])+1):
                key=(tr['trace_id'],epoch)
                if key in seen:continue
                if max_requests is not None and completed>=max_requests:return completed
                visible={'namespace':tr['graph']['nodes'][0]['scope'],'epoch':epoch,
                         'dialogue':[{'epoch':e,'text':text} for e,text in enumerate(tr['turns'][:epoch+1])]}
                user=json.dumps({'demonstrations':demonstration,'task':visible})
                row={'trace_id':tr['trace_id'],'epoch':epoch,'shots':len(demonstration),
                     'configuration_sha256':fingerprint,
                     'provider':provider.config['provider'],'model':provider.config.get('model','external-command')}
                try:row.update(provider.call(EXTRACTION_SYSTEM,user,EXTRACTION_SCHEMA));row['status']='ok'
                except (ValueError,RuntimeError,KeyError,subprocess.TimeoutExpired) as e:
                    row.update(status='error',error=type(e).__name__+': '+str(e))
                f.write(json.dumps(row,allow_nan=False)+'\n');f.flush();completed+=1
    return completed


def collect_qa(dataset,contexts,config,out,k=5,method='pgcm_oracle',max_requests=None):
    provider=JsonProvider(read_json(config));traces={t['trace_id']:t for t in load_traces(dataset)}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise ValueError('use a new output file for this QA configuration')
    done=0
    with out.open('w') as f:
        for ctx in read_jsonl(contexts):
            if ctx['k']!=k or ctx['method']!=method:continue
            if max_requests is not None and done>=max_requests:break
            tr=traces[ctx['trace_id']];spec=next(q for q in tr['queries'] if q['query']['id']==ctx['query_id'])
            records={n['id']:n for n in tr['graph']['nodes']}
            task={'query':spec['query'],'context':[records[v] for v in ctx['context']],
                  'evidence_epoch':spec['query']['as_of_epoch'] if spec['query']['intent']=='historical' else ctx['epoch']}
            row={'trace_id':ctx['trace_id'],'query_id':ctx['query_id'],'k':k,'method':method}
            try:row.update(provider.call(QA_SYSTEM,json.dumps(task),QA_SCHEMA));row['status']='ok'
            except (ValueError,RuntimeError,KeyError,subprocess.TimeoutExpired) as e:row.update(status='error',error=type(e).__name__+': '+str(e))
            f.write(json.dumps(row,allow_nan=False)+'\n');f.flush();done+=1
    return done
