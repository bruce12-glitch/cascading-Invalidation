# PG-CM Neural Retrieval Stage on Kaggle

This stage preserves the completed 2,000-trace structural run and changes only
the embedding representation used by exact cosine retrieval.

## Kaggle settings

1. Create a new Kaggle notebook.
2. Select **Accelerator: GPU T4 x2**. The experiment uses `cuda:0`; one T4 is sufficient.
3. Enable **Internet** for the initial package and model download.
4. Add `PGCM_Neural_Stage.zip` as notebook input.

## Cell 1: locate and extract

```python
from pathlib import Path
import shutil, zipfile

candidates = list(Path("/kaggle/input").rglob("PGCM_Neural_Stage.zip"))
assert len(candidates) == 1, f"Expected one package, found: {candidates}"
root = Path("/kaggle/working/pgcm_neural_stage")
shutil.rmtree(root, ignore_errors=True)
root.mkdir(parents=True)
with zipfile.ZipFile(candidates[0]) as archive:
    archive.extractall(root)
print(root)
```

## Cell 2: install and preflight

```python
%cd /kaggle/working/pgcm_neural_stage
!python -m pip install -q -e pgcm_experiments "sentence-transformers>=3,<6" "huggingface-hub>=0.25,<2"
!python -m unittest discover -s pgcm_experiments/tests -v
!python - <<'PY'
import torch
assert torch.cuda.is_available(), "Enable a Kaggle GPU accelerator"
print(torch.__version__, torch.cuda.get_device_name(0))
PY
```

Do not continue unless every test passes.

## Cell 3: smoke test on 25 traces

```python
!python pgcm_experiments/scripts/build_hf_embeddings.py \
  --dataset fixtures.jsonl --out outputs/embeddings_smoke \
  --model BAAI/bge-small-en-v1.5 --device cuda:0 --batch-size 128 --max-traces 25
```

The smoke directory is intentionally separate from the paper run.

## Cell 4: full embeddings

```python
!python pgcm_experiments/scripts/build_hf_embeddings.py \
  --dataset fixtures.jsonl --out outputs/embeddings_bge \
  --model BAAI/bge-small-en-v1.5 --device cuda:0 --batch-size 128
```

This command is resumable. Re-run the same cell after an interruption. It fails
closed if the model revision, prompt, dataset, or vector IDs differ.

## Cell 5: validate before evaluation

```python
!python pgcm_experiments/scripts/verify_neural_stage.py \
  --dataset fixtures.jsonl --vectors-dir outputs/embeddings_bge \
  --out outputs/embedding_audit.json
```

Expected: `status: passed`, `trace_count: 2000`, and one 384-dimensional
embedding matrix per trace for `bge-small-en-v1.5`.

## Cell 6: neural retrieval replay

```python
!python -m pgcm retrieval \
  --dataset fixtures.jsonl --vectors-dir outputs/embeddings_bge \
  --out outputs/neural_retrieval --bootstrap 10000
```

## Cell 7: paper-facing checks and table

```python
!python pgcm_experiments/scripts/summarize_neural_retrieval.py \
  --neural outputs/neural_retrieval/retrieval.json \
  --hash hash_control_retrieval.json --out outputs/neural_summary
from pathlib import Path
print(Path("outputs/neural_summary/NEURAL_RETRIEVAL_RESULTS.md").read_text())
```

The audit must report zero PG-CM context leakage and zero access violations for
all candidate budgets. VER and coverage are measured outcomes and are not
pre-assumed.

## Cell 8: download the immutable result bundle

```python
import shutil
archive = shutil.make_archive("/kaggle/working/PGCM_Neural_Results", "zip", "outputs")
print(archive)
```

Download `PGCM_Neural_Results.zip` from the Kaggle Output panel. Also use
**Save Version** so Kaggle retains the executed notebook and console logs.
