import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_hf_embeddings.py"
SPEC = importlib.util.spec_from_file_location("build_hf_embeddings", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeCuda:
    def __init__(self, available):
        self.available = available

    def is_available(self):
        return self.available


class FakeTorch:
    def __init__(self, available):
        self.cuda = FakeCuda(available)


class NeuralStageTests(unittest.TestCase):
    def test_auto_device_selection(self):
        self.assertEqual(MODULE.resolve_device("auto", FakeTorch(True)), "cuda")
        self.assertEqual(MODULE.resolve_device("auto", FakeTorch(False)), "cpu")
        with self.assertRaises(RuntimeError):
            MODULE.resolve_device("cuda:0", FakeTorch(False))

    def test_bge_query_prefix(self):
        self.assertTrue(MODULE.default_query_prefix("BAAI/bge-small-en-v1.5"))
        self.assertEqual(MODULE.default_query_prefix("sentence-transformers/all-MiniLM-L6-v2"), "")

    def test_atomic_npz_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.npz"
            MODULE.atomic_save(
                path,
                record_ids=np.asarray(["r1"], dtype=np.str_),
                record_vectors=np.asarray([[1.0, 0.0]], dtype=np.float32),
                query_ids=np.asarray(["q1"], dtype=np.str_),
                query_vectors=np.asarray([[1.0, 0.0]], dtype=np.float32),
                embedding_name=np.asarray("model@revision", dtype=np.str_),
            )
            MODULE.validate_existing(path, ["r1"], ["q1"], "model@revision")
            with self.assertRaises(ValueError):
                MODULE.validate_existing(path, ["other"], ["q1"], "model@revision")


if __name__ == "__main__":
    unittest.main()
