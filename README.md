# PG-CM GPU Experimental Stage

This package executes the remaining pretrained dense-retrieval experiment on
the exact fixtures from the completed structural run.

- `fixtures.jsonl`: 2,000 traces; SHA-256
  `c7fe0e27b17b963d4499fc08f441b8de9776196d455e616db5c6cb0dbffc1c23`.
- `source_run_manifest.json`: provenance for the accepted structural run.
- `hash_control_retrieval.json`: hash-control measurements used only for a
  matched comparison table.
- `pgcm_experiments/`: implementation, tests, embedding builder, verifier, and
  retrieval evaluator.
- `RUN_ON_KAGGLE.md`: exact notebook cells.
- `RUN_PGCM_NEURAL_KAGGLE.ipynb`: runnable Kaggle notebook (GPU T4 x2, Internet On).
- `PGCM_Neural_Stage.zip`: source bundle (SHA-256 `9dc6c3e7a357f642d1e621d85655dbc1a1d32f5cc7718645a57544b905f5d108`).
- `PGCM_Colab_Kaggle_Ready.zip`: original structural-stage bundle.
- `results/`: paper-facing neural outputs (audits, `retrieval.json`,
  comparison table). Full 60 MB bundle with per-trace NPZ
  (`PGCM_Neural_Results.zip`: 2,025 NPZ, embedding
  `BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`)
  is a GitHub Release asset, not stored in git; regenerate NPZ with
  `pgcm_experiments/scripts/build_hf_embeddings.py`.

The neural run is supplementary to, not a replacement for, the structural
conformance experiment. Do not describe the generated fixtures as a
human-reviewed conversational benchmark or the local controls as published
memory systems.
