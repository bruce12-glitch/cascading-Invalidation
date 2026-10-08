"""Command-line drivers. Offline runs never contact a model provider."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
from .dataset import write_fixtures,load_traces
from .io import read_json,write_json,digest,environment
from .experiments import retrieval_experiment,action_experiment,extraction_experiment,qa_replay
from .performance import scalability_experiment,affected_region_experiment
from .robustness import corruption_experiment
from .concurrency import concurrency_experiment
from .providers import collect_extractions,collect_qa
from .regimes import evaluate_regimes
from .gate_benchmark import gate_benchmark
from .baseline_replay import baseline_replay


def source_manifest():
    root=Path(__file__).resolve().parents[1]
    return {str(p.relative_to(root)):digest(p) for folder in ('pgcm','tests','configs')
            for p in sorted((root/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def run_offline(config,out):
    c=read_json(config);out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('choose an empty result directory; results are never silently overwritten')
    out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    print('REVIEW: running independent unit and integration checks',flush=True)
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(root/'tests'),'-v'],cwd=root,capture_output=True,text=True)
    (out/'test_review.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:raise RuntimeError('review failed; see test_review.txt; experiment pipeline halted')
    write_json(out/'configuration.json',c)
    manifest={'started_utc':datetime.now(timezone.utc).isoformat(),'environment':environment(),'source_sha256':source_manifest(),
              'test_returncode':tests.returncode,'phases':{},'status':'running'}
    write_json(out/'manifest.json',manifest)
    def phase(name,fn):
        print('ANALYSE / WRITE / REVIEW: '+name,flush=True)
        try:
            result=fn()
            manifest['phases'][name]={'status':'passed','result_status':result.get('status','generated')}
        except Exception as error:
            manifest['phases'][name]={'status':'failed','exception_type':type(error).__name__}
            manifest['status']='failed';write_json(out/'manifest.json',manifest);raise
        write_json(out/'manifest.json',manifest)
        print('REVIEW PASSED: '+name,flush=True)
        return result
    dataset=out/'fixtures.jsonl'
    phase('fixture_generation',lambda:write_fixtures(dataset,c['fixture_count'],c['seed']) or {'status':'generated'})
    manifest['dataset_sha256']=digest(dataset)
    phase('retrieval',lambda:retrieval_experiment(dataset,out,c['k_values'],c['bootstrap_replicates'],c['seed']))
    phase('actions',lambda:action_experiment(dataset,out,c['action_trace_count']))
    phase('corruptions',lambda:corruption_experiment(dataset,out,noise=c['noise_rates'],max_traces=c['corruption_trace_count'],seed=c['seed']))
    phase('concurrency',lambda:concurrency_experiment(out,c['concurrent_writes'],c['reads_per_worker'],c['reader_workers']))
    phase('scalability',lambda:scalability_experiment(out,c['sizes'],c['batch_sizes'],c['incidence_factors'],c['depths'],c['timing_repeats'],c['seed']))
    phase('gate_overhead',lambda:gate_benchmark(out,sizes=c['sizes'],budgets=c['k_values'],seed=c['seed']))
    phase('dense_affected_region',lambda:affected_region_experiment(out,sizes=[n for n in c['sizes'] if n>=1000] or [100],repeats=c['timing_repeats'],seed=c['seed']))
    manifest['status']='completed';manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
    manifest['unexecuted']=['live lineage extraction','pretrained embedding retrieval','LLM answer/action proposal generation',
                            'published-system baselines','human-reviewed 2000-trace CASCADE-BENCH']
    manifest['result_sha256']={p.name:digest(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json'}
    write_json(out/'manifest.json',manifest)
    print('COMPLETED: '+str(out),flush=True)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('run-offline');p.add_argument('--config',default='configs/offline.json');p.add_argument('--out',required=True)
    p=subs.add_parser('generate');p.add_argument('--out',required=True);p.add_argument('--count',type=int,default=2000);p.add_argument('--seed',type=int,default=20261008)
    p=subs.add_parser('validate');p.add_argument('--dataset',required=True)
    for name in ('evaluate-extraction','evaluate-regimes','extract-live'):
        p=subs.add_parser(name);p.add_argument('--dataset',required=True);p.add_argument('--out',required=True)
        if name=='extract-live':
            p.add_argument('--config',required=True);p.add_argument('--examples');p.add_argument('--max-requests',type=int)
        else:p.add_argument('--predictions',required=True)
    for name in ('qa-live','evaluate-qa'):
        p=subs.add_parser(name);p.add_argument('--dataset',required=True);p.add_argument('--contexts',required=True)
        p.add_argument('--out',required=True);p.add_argument('--k',type=int,default=5);p.add_argument('--method',default='pgcm_oracle')
        if name=='qa-live':p.add_argument('--config',required=True);p.add_argument('--max-requests',type=int)
        else:p.add_argument('--predictions',required=True)
    p=subs.add_parser('retrieval');p.add_argument('--dataset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--vectors-dir');p.add_argument('--bootstrap',type=int,default=10000)
    p=subs.add_parser('evaluate-baseline');p.add_argument('--dataset',required=True);p.add_argument('--contexts',required=True)
    p.add_argument('--identity',required=True);p.add_argument('--out',required=True)
    a=parser.parse_args()
    if a.command=='run-offline':run_offline(a.config,a.out)
    elif a.command=='generate':write_fixtures(a.out,a.count,a.seed)
    elif a.command=='validate':print(json.dumps({'valid_traces':sum(1 for _ in load_traces(a.dataset))}))
    elif a.command=='evaluate-extraction':extraction_experiment(a.dataset,a.predictions,a.out)
    elif a.command=='evaluate-regimes':evaluate_regimes(a.dataset,a.predictions,a.out)
    elif a.command=='extract-live':collect_extractions(a.dataset,a.config,a.out,a.examples,a.max_requests)
    elif a.command=='retrieval':retrieval_experiment(a.dataset,a.out,bootstrap_replicates=a.bootstrap,vectors_dir=a.vectors_dir)
    elif a.command=='qa-live':collect_qa(a.dataset,a.contexts,a.config,a.out,a.k,a.method,a.max_requests)
    elif a.command=='evaluate-qa':qa_replay(a.dataset,a.contexts,a.predictions,a.out,a.k,a.method)
    elif a.command=='evaluate-baseline':baseline_replay(a.dataset,a.contexts,a.identity,a.out)

if __name__=='__main__':main()
