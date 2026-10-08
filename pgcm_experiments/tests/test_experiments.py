import json
import tempfile
import unittest
from pathlib import Path
from pgcm.dataset import write_fixtures,load_traces,prefix_graph
from pgcm.model import Graph
from pgcm.experiments import gold_states,extraction_experiment,retrieval_experiment,qa_replay
from pgcm.regimes import evaluate_regimes
from pgcm.cli import run_offline
from pgcm.io import write_json,read_json
from pgcm.providers import collect_extractions

class ExperimentTests(unittest.TestCase):
    def test_perfect_replay_and_missing_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);data=p/'data.jsonl';write_fixtures(data,2)
            rows=[]
            for tr in load_traces(data):
                g=Graph.from_dict(tr['graph']);_,roots,_=gold_states(tr,g)
                for e in range(4):
                    prefix=prefix_graph(g,e)
                    ev=tr['events'][e-1] if e else {'retract':[],'activate':[]}
                    rows.append({'trace_id':tr['trace_id'],'epoch':e,'status':'ok','output':{
                        'graph':prefix.to_dict(),'root_active':{n.id:roots[e][g.index[n.id]] for n in prefix.nodes if n.kind=='R'},
                        'retract':ev['retract'],'activate':ev['activate']}})
            pred=p/'predictions.jsonl';pred.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            ex=extraction_experiment(data,pred,p/'extract')
            self.assertEqual(ex['failed_attempts'],0);self.assertEqual(ex['metrics']['hyperedges']['f1'],1)
            result=evaluate_regimes(data,pred,p/'regimes')
            for key,value in result['state_counts'].items():
                if 'false_' in key or 'unmatched' in key:self.assertEqual(value,0,key)
            pred.write_text(''.join(json.dumps(r)+'\n' for r in rows if r['epoch']!=1))
            missing=evaluate_regimes(data,pred,p/'missing')
            self.assertEqual(missing['rejected_prefixes'],2)
            self.assertGreater(missing['state_counts']['gold_graph_inferred_targets_false_active'],0)

    def test_no_silent_provider_cache_change(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);data=p/'data';write_fixtures(data,1)
            config=p/'config.json';write_json(config,{'provider':'command','command':['unused']})
            out=p/'pred';out.write_text(json.dumps({'trace_id':'fixture-00000','epoch':0,'provider':'command','model':'external-command','configuration_sha256':'wrong'})+'\n')
            with self.assertRaises(ValueError):collect_extractions(data,config,out,max_requests=0)

    def test_pipeline_smoke_and_missing_qa(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);config=p/'config.json';out=p/'run'
            write_json(config,{'seed':20261008,'fixture_count':2,'k_values':[5],'bootstrap_replicates':10,
                'action_trace_count':2,'corruption_trace_count':2,'noise_rates':[.3],'sizes':[100],
                'batch_sizes':[1,100],'incidence_factors':[3],'depths':[2],'timing_repeats':1,
                'concurrent_writes':4,'reads_per_worker':4,'reader_workers':2})
            # The CLI's subprocess review is exercised by the full external run;
            # do not recursively invoke unittest from within its own smoke test.
            from unittest.mock import patch
            import subprocess
            with patch('pgcm.cli.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','review mocked in pipeline smoke only')):
                result=run_offline(config,out)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(read_json(out/'scalability.json')['skipped'][0]['batch'],100)
            pred=p/'empty';pred.write_text('')
            q=qa_replay(out/'fixtures.jsonl',out/'retrieval_queries.jsonl.gz',pred,p/'qa')
            self.assertEqual(q['counts']['invalid_or_missing'],28)
            self.assertEqual(q['structured_behavior_accuracy'],0)
            with self.assertRaises(ValueError):run_offline(config,out)

class ExternalBaselineTests(unittest.TestCase):
    def test_audited_export_scoring_and_identity(self):
        from pgcm.baseline_replay import baseline_replay
        from pgcm.io import read_jsonl
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);data=p/'data';write_fixtures(data,1)
            retrieval_experiment(data,p/'retrieval',k_values=(5,),bootstrap_replicates=10)
            identity=p/'identity';write_json(identity,{'method':'fixture_export_test','repository':'fixture-test-only',
                'commit':'not-a-published-system','model':'none','embedding':'hash-control','candidate_budget':'5',
                'prompt_sha256':'not-applicable','adaptation':'unit test of export scorer; not real baseline'})
            rows=[]
            for row in read_jsonl(p/'retrieval/retrieval_queries.jsonl.gz'):
                if row['method']=='pgcm_oracle':
                    rows.append({'trace_id':row['trace_id'],'query_id':row['query_id'],'k':row['k'],
                        'epoch':0 if row['probe']=='historical' else row['epoch'],'context':row['context']})
            contexts=p/'contexts';contexts.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            scored=baseline_replay(data,contexts,identity,p/'score',k_values=(5,))
            self.assertEqual(scored['missing_contexts'],0)
            self.assertEqual(scored['summaries'][0]['metrics']['CLR']['value'],0)
            self.assertIsNone(scored['summaries'][0]['metrics']['CER']['value'])
            rows[0]['context']=['unknown']
            contexts.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):baseline_replay(data,contexts,identity,p/'invalid',k_values=(5,))
