import unittest
from itertools import combinations, product
import random
from pgcm.model import AdmissionError, Graph, Node, Rule, strict_json
from pgcm.engine import CounterEngine, full_recompute, eager_retract


def nodes(n, roots=2):
    return tuple(Node(str(i), f"record {i}", "R" if i < roots else "D", f"e{i}", "a", "s", "v") for i in range(n))


def subsets(xs):
    xs = list(xs)
    return [c for k in range(len(xs) + 1) for c in combinations(xs, k)]


class CoreTests(unittest.TestCase):
    def test_update_does_not_scan_all_labels(self):
        class IndexedOnly(list):
            def __iter__(self):raise RuntimeError('full scan in affected-region update')
            def copy(self):raise RuntimeError('full copy in affected-region update')
        g=Graph(nodes(100,100),())
        m=CounterEngine(g,{str(i):True for i in range(100)})
        m.active=IndexedOnly(m.active)
        c=m.change(retract=['0'])
        self.assertEqual(c.invalidated,frozenset({'0'}))
        self.assertEqual(c.visits,0)
        self.assertEqual(m.change(retract=['0']).invalidated,frozenset())
    def test_exhaustive_four_nodes(self):
        checks = 0
        for a in subsets(subsets(range(2))[1:]):
            for b in subsets(subsets(range(3))[1:]):
                rs = [(2, ps) for ps in a] + [(3, ps) for ps in b]
                g = Graph(nodes(4), tuple(Rule(str(j), str(h), tuple(map(str, ps))) for j, (h, ps) in enumerate(rs)))
                for bits in product((False, True), repeat=2):
                    roots = {str(i): bits[i] for i in range(2)}
                    for batch in subsets(("0", "1")):
                        for operation in ("retract", "activate"):
                            m = CounterEngine(g, roots)
                            m.change(**{operation: batch})
                            m.verify()
                            for r in batch:
                                self.assertEqual(m.active[g.index[r]], operation == "activate")
                            checks += 1
        self.assertEqual(checks, 32768)

    def test_random_mixed_sequences_and_eager(self):
        rng = random.Random(91)
        for _ in range(100):
            rs = []
            for h in range(5, 30):
                clauses = {tuple(sorted(rng.sample(range(h), rng.randint(1, min(3, h))))) for _ in range(3)}
                rs.extend((h, ps) for ps in clauses)
            g = Graph(nodes(30, 5), tuple(Rule(str(j), str(h), tuple(map(str, ps))) for j, (h, ps) in enumerate(rs)))
            m = CounterEngine(g, {str(i): True for i in range(5)})
            for _ in range(20):
                off = [str(i) for i in range(5) if rng.random() < .4]
                on = [str(i) for i in range(5) if str(i) not in off and rng.random() < .5]
                before = m.active.copy()
                expected, _ = eager_retract(g, before, off)
                staged = m.clone()
                staged.change(retract=off)
                self.assertEqual(staged.active, expected)
                m.change(retract=off, activate=on)
                m.verify()
                self.assertEqual(m.change(retract=off, activate=on).visits, 0)

    def test_admission(self):
        from dataclasses import replace
        a=nodes(1,1)[0]
        with self.assertRaises(AdmissionError):
            Graph((a,replace(a,id='different-id')),())
        # Distinct scopes or historical versions must remain distinct records.
        Graph((a,replace(a,id='scoped',scope='other'),replace(a,id='version',value='new',created_epoch=1)),())
        with self.assertRaises(AdmissionError):
            Graph(nodes(3), (Rule("j", "2", ("missing",)),))
        with self.assertRaises(AdmissionError):
            Graph(nodes(4), (Rule("a", "2", ("3",)), Rule("b", "3", ("2",))))
        with self.assertRaises(AdmissionError):
            Graph(nodes(3), (Rule("j", "2", ()),))
        with self.assertRaises(AdmissionError):
            strict_json('{"a":1,"a":2}')
        with self.assertRaises(AdmissionError):
            strict_json('{"a":NaN}')

    def test_rejected_batch_is_not_partially_applied(self):
        g = Graph(nodes(3), (Rule("j", "2", ("0", "1")),))
        m = CounterEngine(g, {"0": True, "1": True})
        before = m.active.copy()
        with self.assertRaises(AdmissionError):
            m.change(retract=["0", "unknown"])
        self.assertEqual(before, m.active)

    def test_roundtrip_unordered_ids_and_versions(self):
        g = Graph(nodes(4)[::-1], (Rule("j", "3", ("0", "1")),))
        h = Graph.from_dict(strict_json(__import__('json').dumps(g.to_dict())))
        m = CounterEngine(h, {"0": True, "1": True})
        m.change(retract=["0"])
        m.verify()
        self.assertFalse(m.active[h.index["3"]])


if __name__ == '__main__':
    unittest.main()
