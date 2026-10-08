"""Synthetic dialogue fixtures and scalable graphs; no human annotation claimed."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import random
import math
from .model import Graph, Node, Rule, root_vector, strict_json
from .retrieval import Query


DOMAINS = ('software_configuration','workflow_scheduling','access_policy','personal_planning')


def fixture(index: int, seed=20261008):
    rng = random.Random(seed+index)
    domain = DOMAINS[index%4]
    names = {'software_configuration': ('Node.js','Python','deployment'),
             'workflow_scheduling': ('vendor A','vendor B','dispatch'),
             'access_policy': ('write role','read role','export'),
             'personal_planning': ('Friday trip','Saturday trip','booking')}
    old,new,task = names[domain]
    namespace, entity = f'{domain}/project-{index}', f'service-{index}'
    nodes, rules = [], []
    def node(id, text, kind='R', attribute=None,value='approved',created=0,scope=None,permissions=('researcher',)):
        nodes.append(Node(id,text,kind,entity,attribute or id,scope or namespace,value,created,permissions))
    node('old',f'{entity}: the primary configuration is {old}.',attribute='primary',value=old)
    node('policy',f'{entity}: the {task} approval policy is enabled.')
    node('backup',f'{entity}: an independent backup approval is enabled.')
    node('permission',f'{entity}: permission for the {task} action is enabled.')
    node('new',f'{entity}: the primary configuration is {new}.',attribute='primary',value=new,created=1)
    node('other',f'Unrelated {entity} auxiliary configuration still uses {old}.',scope=namespace+'/aux')
    node('private',f'{entity}: confidential {task} details.',permissions=('admin',))
    depth = 1+index%5
    for d in range(depth):
        parent = 'old' if d == 0 else f'legacy-{d-1}'
        node(f'legacy-{d}',f'{entity}: legacy {task} plan step {d} is approved.',kind='D')
        rules.append(Rule(f'j-legacy-{d}',f'legacy-{d}',(parent,'policy') if d == 0 else (parent,)))
    node('fallback',f'{entity}: fallback {task} plan is approved.',kind='D')
    rules.extend((Rule('j-fallback-old','fallback',('old','policy')),Rule('j-fallback-backup','fallback',('backup',))))
    node('new-plan',f'{entity}: replacement {task} plan is approved.',kind='D',created=1)
    rules.append(Rule('j-new','new-plan',('new','policy')))
    node('action-precondition',f'{entity}: legacy {task} action precondition is satisfied.',kind='A')
    rules.append(Rule('j-action','action-precondition',(f'legacy-{depth-1}','permission')))
    graph = Graph(tuple(nodes),tuple(rules))
    roots = {n.id: n.id != 'new' for n in nodes if n.kind == 'R'}
    events = [dict(epoch=1,retract=['old'],activate=['new']),
              dict(epoch=2,retract=['backup'],activate=[]),
              dict(epoch=3,retract=['new'],activate=['old'])]
    text0 = [n.text for n in nodes if n.kind == 'R' and n.created_epoch==0]
    for r in rules:
        head = next(n.text for n in nodes if n.id == r.head)
        ps = [next(n.text for n in nodes if n.id == p) for p in r.premises]
        if next(n.created_epoch for n in nodes if n.id == r.head)==0:
            text0.append('Registered sufficient support: '+head+' Requires ALL of: '+' AND '.join(ps))
    turn0 = '\n'.join(text0)
    turn1 = f'Replace the primary configuration {old} with {new}. Retract the former primary version only; the auxiliary configuration and backup remain unchanged. '+next(n.text for n in nodes if n.id=='new-plan')+' requires the new primary and the approval policy.'
    turn2 = 'Withdraw the independent backup approval. The primary configuration is unchanged.'
    turn3 = f'Revert the primary configuration to the earlier {old} version. Withdraw the {new} primary version. The backup remains withdrawn.'
    queries = []
    for e in range(1,4):
        qs = [('current',f'What is the primary configuration of {entity}?',['new' if e<3 else 'old']),
              ('alternative',f'Is the fallback {task} plan for {entity} still approved?',['fallback']),
              ('legacy',f'Is the legacy {task} plan step {depth-1} for {entity} approved?',[f'legacy-{depth-1}']),
              ('historical',f'What was the primary configuration of {entity} before the changes?',['old'])]
        if e<3: qs.append(('stale_premise',f'Given that {entity} still uses {old}, should I use its legacy {task} plan?',['old']))
        for intent,text,targets in qs:
            queries.append({'query':asdict(Query(f'{e}:{intent}',text,namespace,intent='historical' if intent=='historical' else 'current',as_of_epoch=0 if intent=='historical' else None)),
                            'after_epoch':e,'probe':intent,'target_ids':targets})
    # All of these are synthetic integration fixtures. They are NOT a held-out
    # publication benchmark and have not been reviewed by human annotators.
    return {'trace_id':f'fixture-{index:05d}','seed':seed+index,'domain':domain,
            'template_family':f'explicit-rules-depth-{depth}', 'split':'unreviewed_fixture',
            'annotation_status':'synthetic_unreviewed', 'graph':graph.to_dict(),
            'initial_roots':roots,'events':events,'turns':[turn0,turn1,turn2,turn3],
            'queries':queries,'actions':[{'id':'legacy-action','required':['action-precondition'],'principals':['researcher']}],
            'depth':depth}


def write_fixtures(path, count=2000, seed=20261008):
    if count < 1: raise ValueError('positive trace count')
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as f:
        for i in range(count): f.write(json.dumps(fixture(i,seed),sort_keys=True)+'\n')


def load_traces(path):
    seen=set()
    with Path(path).open() as f:
        for line in f:
            tr = strict_json(line)
            if tr['trace_id'] in seen: raise ValueError('duplicate trace ID')
            seen.add(tr['trace_id'])
            g=Graph.from_dict(tr['graph']); root_vector(g,tr['initial_roots'])
            if [e['epoch'] for e in tr['events']]!=list(range(1,len(tr['events'])+1)):
                raise ValueError('event epochs must be contiguous')
            yield tr


def prefix_graph(graph, epoch):
    ids={n.id for n in graph.nodes if n.created_epoch<=epoch}
    return Graph(tuple(n for n in graph.nodes if n.id in ids),tuple(r for r in graph.rules if r.head in ids and set(r.premises)<=ids))


def scalable_graph(n, incidence_factor=3, seed=20261008, depth=5):
    if n<10 or depth<1: raise ValueError('graph too small or depth invalid')
    rng=random.Random(seed)
    root_count=min(max(100,n//10),n//2)
    ns=tuple(Node(str(i),f'record {i}','R' if i<root_count else 'D',str(i),'a','scale','v') for i in range(n))
    levels=[list(range(root_count))]
    remaining=n-root_count
    cursor=root_count
    for d in range(depth):
        width=remaining//depth+int(d<remaining%depth)
        levels.append(list(range(cursor,cursor+width)));cursor+=width
    rules=[]
    total_clauses=max(n-root_count, round(incidence_factor*n/2))
    base, extra=divmod(total_clauses,n-root_count)
    assigned=0
    for level in range(1,len(levels)):
        parents=levels[level-1]
        for h in levels[level]:
            clauses=set()
            requested=base+int(assigned<extra)
            assigned+=1
            if requested>math.comb(len(parents),min(2,len(parents))):
                raise ValueError('requested density cannot be represented at this depth/width')
            while len(clauses)<requested:
                ps=tuple(sorted(rng.sample(parents,min(2,len(parents)))))
                clauses.add(ps)
            for ps in sorted(clauses):
                rules.append(Rule(str(len(rules)),str(h),tuple(map(str,ps))))
    return Graph(ns,tuple(rules)),{str(i):True for i in range(root_count)}
