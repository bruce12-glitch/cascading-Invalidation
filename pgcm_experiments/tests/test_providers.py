import json
import unittest
from pgcm.providers import JsonProvider,QA_SCHEMA


class ProviderTests(unittest.TestCase):
    def test_openai_tool_output(self):
        output={'decision':'answer','evidence_ids':['r'],'answer':'value'}
        seen=[]
        def transport(body):
            seen.append(body)
            return {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'emit_result','arguments':json.dumps(output)}}]}}], 'usage':{'completion_tokens':5}}
        p=JsonProvider({'provider':'openai_compatible','model':'test-model'},transport)
        r=p.call('system','task',QA_SCHEMA)
        self.assertEqual(r['output'],output)
        self.assertNotIn('api_key',seen[0])
        self.assertFalse(seen[0]['tools'][0]['function']['strict'])

    def test_anthropic_and_truncation(self):
        def transport(body):return {'content':[{'type':'tool_use','name':'emit_result','input':{'decision':'abstain','evidence_ids':[],'answer':''}}], 'stop_reason':'tool_use'}
        p=JsonProvider({'provider':'anthropic','model':'test-model'},transport)
        self.assertEqual(p.call('s','u',QA_SCHEMA)['output']['decision'],'abstain')
        p.transport=lambda _: {'content':[],'stop_reason':'max_tokens'}
        with self.assertRaises(ValueError):p.call('s','u',QA_SCHEMA)

    def test_no_silent_extra_body_override_or_placeholder_model(self):
        with self.assertRaises(ValueError):JsonProvider({'provider':'anthropic','model':'SET_MODEL'})
        p=JsonProvider({'provider':'openai_compatible','model':'test','extra_body':{'messages':[]}},lambda _:None)
        with self.assertRaises(ValueError):p.call('s','u',QA_SCHEMA)
