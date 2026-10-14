# Comparacao de resultados

| run | dataset_split | total_examples | partial_evaluation | schema_valid_rate | action_accuracy | argument_field_accuracy | exact_match_rate | mean_latency_seconds | peak_vram_gb |
|---|---|---|---|---|---|---|---|---|---|
| base-preliminary | test | 20 | True | 0.0 | 1.0 | 0.112245 | 0.0 | 6.162322 | 1.318 |
| run_b-preliminary | test | 20 | True | 0.9 | 0.9 | 0.983051 | 0.85 | 6.453891 | 1.351 |

Gerado automaticamente por `training/compare_results.py`.
Diretorios com `smoke` sao excluidos por padrao.
