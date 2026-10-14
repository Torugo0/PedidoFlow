# Modelos locais

Esta pasta pode receber manualmente um adapter publicado para demonstracao.
Pesos e checkpoints nao sao versionados no Git; o modelo base e checkpoints
podem ocupar varios gigabytes.

O fluxo normal treina em `outputs/run_*/final_adapter` e registra o vencedor em
`reports/model-selection.json`. Se o grupo quiser distribuir um adapter fora
desse fluxo, use `models/pedidoflow-qwen3-1.7b` ou defina
`PEDIDOFLOW_ADAPTER`.
