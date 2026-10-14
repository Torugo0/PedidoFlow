# Roteiro de apresentacao

## 1. Problema

Empresas recebem solicitacoes por texto e um operador precisa interpretar a
mensagem, abrir a funcao correta e preencher campos manualmente.

## 2. Solucao

Uma LLM local restrita escolhe a operacao e extrai argumentos. Um backend
deterministico valida data, estoque e regras antes de executar.

## 3. Evidencia da GPU

No terminal integrado do VS Code, execute:

```powershell
nvidia-smi
.\.venv\Scripts\python.exe scripts\check_gpu.py --output reports\gpu-info.json
```

Deixe visiveis no mesmo print:

- nome `NVIDIA GeForce RTX 4060`;
- versao do driver;
- PyTorch `2.11.0+cu128`;
- `GPU CUDA funcionando`;
- compute capability `8.9`.

Salve a imagem como `reports/gpu-vscode.png`.

O `nvidia-smi` mostra a versao maxima de CUDA suportada pelo driver, enquanto
`torch.version.cuda` mostra o runtime usado pelo PyTorch (`12.8`). O projeto usa
o wheel `cu128`, portanto nao depende de `nvcc`. Caso o professor exija o comando
`nvcc --version` no print, instale tambem o CUDA Toolkit 12.8; isso nao e
necessario para os scripts atuais funcionarem.

## 4. Demonstracao sugerida

1. Criar pedido usando `sexta` e mostrar `16/10/2026`.
2. Tentar executar sem confirmar e mostrar o bloqueio.
3. Confirmar, criar o pedido e mostrar a reducao do estoque.
4. Consultar o pedido criado.
5. Alterar a entrega para `proxima terca`.
6. Cancelar o pedido e mostrar a reposicao do estoque.
7. Enviar texto fora do escopo e mostrar `nao_suportada`.

## 5. Resultados

Mostrar uma tabela com modelo original, runs A/B/C, exact match, conformidade de
schema, latencia e pico de VRAM. Nao misturar o smoke test com os resultados
finais.

## 6. Divisao para cinco integrantes

1. Dataset sintetico e controle de qualidade.
2. Ambiente CUDA, QLoRA e treinamento.
3. Metricas, avaliacao e analise de erros.
4. Backend, banco e regras de data.
5. Frontend, documentacao, GitHub e apresentacao.

Com quatro integrantes, junte avaliacao e documentacao.
