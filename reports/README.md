# Relatorios e evidencias

- `gpu-info.json`: verificacao programatica da GPU.
- `gpu-vscode.png`: captura a ser feita no terminal integrado do VS Code.
- `training/*.json`: resumos leves de cada treino (loss, GPU, CUDA e VRAM),
  versionados sem incluir os pesos.
- `validation/run_*/metrics.json`: comparacao A/B/C para escolher o adapter.
- `model-selection.json`: vencedor escolhido exclusivamente pela validacao.
- `final/base/metrics.json`: resultado final do modelo original no teste.
- `final/run_*/metrics.json`: resultado final do vencedor no teste.
- `predictions.jsonl`: previsoes individuais para analise de erros; ignoradas no Git.

Resultados cujo nome contenha `smoke` validam infraestrutura e nao representam
a qualidade final do modelo.

`RESULTADOS_PRELIMINARES.md` e `preliminary-comparison/` registram a comparacao
reduzida realmente executada nesta maquina. O nome e o documento deixam claro
que ela nao substitui os experimentos finais A/B/C.
