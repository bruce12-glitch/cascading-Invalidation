import unittest
from pgcm.dataset import fixture
from pgcm.model import Graph
from pgcm.metrics import extraction_counts, sum_extraction, paired_bootstrap, ratio


class MetricsTests(unittest.TestCase):
    def test_perfect_and_missing_hyperedge(self):
        tr=fixture(0);g=Graph.from_dict(tr['graph']);up=tr['events'][0]
        c=extraction_counts(g,g,up,up)
        self.assertEqual(sum_extraction([c])['node_macro_f1'],1)
        h=Graph(g.nodes,tuple(r for r in g.rules if r.id!='j-fallback-backup'))
        result=extraction_counts(g,h,up,up)
        self.assertEqual(result['hyperedges'][2],1)
        self.assertEqual(result['alternative_head_exact'],[0,1])

    def test_undefined_and_paired_bootstrap(self):
        self.assertIsNone(ratio(0,0))
        rows=[]
        for i in range(3):
            for m,n in [('a',0),('b',2)]:
                rows.append({'trace_id':str(i),'method':m,'counts':{'leaked_queries':n,'current_queries':2}})
        b=paired_bootstrap(rows,'a','b','CLR',replicates=100)
        self.assertEqual(b['difference_A_minus_B'],-1)
        self.assertEqual(b['ci95'],[-1,-1])
        with self.assertRaises(ValueError):paired_bootstrap(rows[:-1],'a','b','CLR')
