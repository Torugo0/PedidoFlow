# Modelos locais

O modelo-base `Qwen/Qwen3-1.7B` nao fica nesta pasta. Ele e baixado pelo
Hugging Face e armazenado no cache do computador.

No computador usado no projeto, `models/adapter_demo` contem um adapter LoRA
preliminar treinado com 400 exemplos. Ele permite demonstrar a aplicacao sem
refazer o treino, mas nao representa o vencedor final dos experimentos A/B/C.

Os pesos sao ignorados pelo Git para manter o repositorio leve. Ao montar a
entrega compactada manualmente, inclua a pasta `models/adapter_demo`.

O experimento completo cria `models/run_a`, `models/run_b` e `models/run_c` e
registra o vencedor em `results/model-selection.json`. Depois disso, a
aplicacao passa a carregar automaticamente o adapter vencedor.
