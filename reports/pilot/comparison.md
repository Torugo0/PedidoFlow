# Comparacao de resultados

| run | dataset_split | total_examples | partial_evaluation | schema_valid_rate | action_accuracy | argument_field_accuracy | exact_match_rate | mean_latency_seconds | peak_vram_gb |
|---|---|---|---|---|---|---|---|---|---|
| run_a | validation | 10 | True | 0.0 | 0.8 | 0.054054 | 0.0 | 6.266519 | 1.349 |
| run_b | validation | 10 | True | 0.1 | 0.9 | 0.142857 | 0.1 | 9.072639 | 1.356 |
| run_c | validation | 10 | True | 0.5 | 0.9 | 0.518519 | 0.4 | 5.43086 | 1.382 |

Gerado automaticamente por `training/compare_results.py`.
Diretorios com `smoke` sao excluidos por padrao.
