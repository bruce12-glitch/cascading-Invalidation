# Neural Retrieval Results

Embedding: `BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a;query_prefix='Represent this sentence for searching relevant passages: ';normalized=true`

| K | Method | CER | CEP | CLR | VER | Coverage | SCF | Access violation |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 5 | pgcm_oracle | 100.00% | 100.00% | 0.00% | 100.00% | 81.47% | 0.00% | 0.00% |
| 5 | local_root_update_control | 0.00% | NA | 72.80% | 100.00% | 100.00% | 49.34% | 0.00% |
| 5 | descendant_pruning_control | 83.33% | 83.33% | 0.00% | 83.33% | 80.66% | 0.00% | 0.00% |
| 5 | no_eligibility_gate | 100.00% | 100.00% | 96.60% | 100.00% | 100.00% | 49.88% | 10.23% |
| 10 | pgcm_oracle | 100.00% | 100.00% | 0.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| 10 | local_root_update_control | 0.00% | NA | 99.67% | 100.00% | 100.00% | 42.54% | 0.00% |
| 10 | descendant_pruning_control | 83.33% | 83.33% | 0.00% | 83.33% | 100.00% | 0.00% | 0.00% |
| 10 | no_eligibility_gate | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 42.61% | 14.00% |
| 20 | pgcm_oracle | 100.00% | 100.00% | 0.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| 20 | local_root_update_control | 0.00% | NA | 100.00% | 100.00% | 100.00% | 37.86% | 0.00% |
| 20 | descendant_pruning_control | 83.33% | 83.33% | 0.00% | 83.33% | 100.00% | 0.00% | 0.00% |
| 20 | no_eligibility_gate | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 39.86% | 15.38% |
