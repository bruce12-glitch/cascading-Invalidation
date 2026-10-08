import tempfile
from pathlib import Path
import threading
import unittest
from pgcm.engine import full_recompute
from pgcm.model import Graph, Node, Rule
from pgcm.store import SQLiteMemory, EpochConflict
from pgcm.retrieval import Query, HashEmbeddings, VectorIndex, retrieve


def graph():
    ns = tuple(Node(str(i), f"scope service policy plan {i}", "R" if i < 2 else "D",
                    f"e{i}", "a", "s", "v") for i in range(5))
    return Graph(ns, (Rule("a", "2", ("0",)), Rule("b", "3", ("2",)), Rule("c", "4", ("3", "1"))))


class IntegrationTests(unittest.TestCase):
    def test_action_gate_node_permissions_and_scope(self):
        g=Graph((Node('private','restricted','R','e','a','s','v',permissions=('admin',)),),())
        mem=SQLiteMemory(Path(self.temp.name)/'restricted.db',g,{'private':True})
        mem.register_action('restricted',['private'],principals=('researcher','admin'))
        effects=[]
        self.assertIn('unauthorized_precondition',mem.dispatch('restricted','researcher',lambda:effects.append(1))['reason'])
        self.assertIn('scope_mismatch',mem.dispatch('restricted','admin',lambda:effects.append(2),scope='wrong')['reason'])
        self.assertTrue(mem.dispatch('restricted','admin',lambda:effects.append(3),scope='s')['executed'])
        self.assertEqual(effects,[3])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.g = graph()
        self.mem = SQLiteMemory(Path(self.temp.name)/'state.db', self.g, {"0": True, "1": True})

    def tearDown(self):
        self.temp.cleanup()

    def test_history_restart_cas_and_idempotence(self):
        old = self.mem.snapshot()
        changed = self.mem.transact(retract=["0"], expected_epoch=0, operation_id='x')
        self.assertEqual(changed['invalidated'], ["0", "2", "3", "4"])
        self.assertEqual(self.mem.transact(retract=["0"], operation_id='x')['epoch'], 1)
        with self.assertRaises(EpochConflict):
            self.mem.transact(activate=["0"], expected_epoch=0)
        restored = SQLiteMemory(self.mem.path, self.g)
        self.assertEqual(restored.snapshot(0), old)
        self.assertEqual(restored.snapshot().epoch, 1)

    def test_unpublished_state_and_rollback(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def hook():
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test synchronization")
        def writer():
            try:
                self.mem.transact(retract=["0"], before_publish=hook)
            except BaseException as e:
                errors.append(e)
        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.mem.snapshot().active, bytes([1]*5))
        release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.mem.snapshot().active, bytes([0, 1, 0, 0, 0]))
        def fail():
            raise RuntimeError("injected pre-commit fault")
        with self.assertRaises(RuntimeError):
            self.mem.transact(activate=["0"], before_publish=fail)
        self.assertEqual(self.mem.snapshot().epoch, 1)

    def test_action_gate_all_preconditions_and_registry(self):
        self.mem.register_action('tool', ["0", "1", "4"])
        side_effects = []
        self.assertTrue(self.mem.dispatch('tool', 'researcher', lambda: side_effects.append(1))['executed'])
        self.mem.transact(retract=["1"])
        self.assertFalse(self.mem.dispatch('tool', 'researcher', lambda: side_effects.append(2))['executed'])
        self.assertFalse(self.mem.dispatch('tool', 'stranger', lambda: side_effects.append(3))['executed'])
        self.assertFalse(self.mem.dispatch('invented', 'researcher', lambda: side_effects.append(4))['executed'])
        self.assertEqual(side_effects, [1])

    def test_action_validation_is_serialized_with_retraction(self):
        self.mem.register_action('tool', ["4"])
        entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
        outcomes, errors = {}, []
        def action():
            try:
                def callback():
                    entered.set()
                    if not release.wait(5): raise TimeoutError()
                outcomes['action'] = self.mem.dispatch('tool', 'researcher', callback)
            except BaseException as e: errors.append(e)
        def writer():
            attempted.set()
            try: outcomes['write'] = self.mem.transact(retract=["0"])
            except BaseException as e: errors.append(e)
        a = threading.Thread(target=action); a.start()
        self.assertTrue(entered.wait(5))
        w = threading.Thread(target=writer); w.start()
        self.assertTrue(attempted.wait(5))
        release.set(); a.join(5); w.join(5)
        self.assertFalse(a.is_alive() or w.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes['action']['epoch'], 0)
        self.assertTrue(outcomes['action']['executed'])
        self.assertEqual(outcomes['write']['epoch'], 1)

    def test_retrieval_and_historical_gate(self):
        emb = HashEmbeddings()
        index = VectorIndex(self.g, emb.encode([n.text for n in self.g.nodes]), emb.name)
        q = Query('q', 'scope plan', 's')
        self.mem.transact(retract=["0"])
        current = self.mem.snapshot()
        result = retrieve(index, emb.encode([q.text])[0], q, current.active, current.epoch, k=5)
        self.assertEqual(result['context'], ['1'])
        outsider = Query('u', q.text, 's', principal='stranger')
        self.assertEqual(retrieve(index, emb.encode([q.text])[0], outsider, current.active, 1)['context'], [])
        past = self.mem.snapshot(0)
        historic = Query('h', q.text, 's', intent='historical', as_of_epoch=0)
        self.assertEqual(len(retrieve(index, emb.encode([q.text])[0], historic, past.active, 0)['context']), 5)


if __name__ == '__main__':
    unittest.main()
