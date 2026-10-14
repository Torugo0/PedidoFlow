# Atendimento aos requisitos do CP

| Requisito | Como foi atendido | Arquivos/evidencias |
|---|---|---|
| Escolher um problema especifico | **CONCLUIDO:** automacao de criacao, consulta, cancelamento e alteracao de pedidos por linguagem natural | `README.md`, `src/pedidoflow/service.py` |
| Selecionar uma LLM | Qwen3-1.7B, pequena, multilíngue e adequada a QLoRA em 8 GB | `configs/*.json`, `training/train.py` |
| Treinar localmente | **PARCIAL:** pipeline SFT com QLoRA 4-bit NF4 concluido e validado por smoke, treino B reduzido e piloto A/B/C; treino completo com 2.400 exemplos ainda pendente | `training/train.py`, `reports/training/*.json`, `scripts/run_experiments.ps1` |
| Testar parametros | **PARCIAL:** runs A/B/C variam learning rate e rank LoRA mantendo seed e dataset; piloto reduzido concluido, comparacao completa ainda pendente | `configs/run_a.json`, `run_b.json`, `run_c.json`, `reports/pilot/` |
| Avaliar respostas | **PARCIAL:** metricas e avaliador estao implementados e foram usados em execucoes preliminares; `reports/validation`, selecao final e `reports/final` ainda precisam ser gerados pelo experimento completo | `training/evaluate.py`, `training/metrics.py`, `training/select_best.py` |
| Usar GPU | **CONCLUIDO:** treino e avaliacao abortam sem CUDA; diagnostico executou multiplicacao de matrizes na RTX 4060 | `scripts/check_gpu.py`, `reports/gpu-info.json`, `reports/training/*.json` |
| Criar frontend | **CONCLUIDO:** tela Gradio sem interface de chat, com previa, confirmacao, resultado, pedidos e estoque | `app.py` |
| Testes automatizados | **CONCLUIDO:** 49 testes aprovados localmente, cobrindo dominio, datas, interpretacao, dataset, metricas e artefatos | `tests/` |
| Print da GPU no VS Code | **PENDENTE de captura manual:** diagnostico e comandos estao prontos, mas a imagem precisa mostrar o VS Code do grupo | `docs/APRESENTACAO.md`, `reports/gpu-info.json` |
| Codigo e documentacao no GitHub | **PENDENTE apenas de remote/push:** repositorio e commit local preparados; falta escolher a conta/URL do GitHub e publicar | `README.md`, `requirements.txt`, `.gitignore`, `docs/GITHUB.md` |

## Estado objetivo da entrega

- **Implementacao funcional:** concluida e validada por 49 testes.
- **Dataset:** concluido, com 2.400/300/600 exemplos unicos para
  treino/validacao/teste.
- **Treino preliminar e piloto:** concluidos na GPU. O piloto usou 32 exemplos
  de treino, 16 de validacao e avaliacao parcial de 10 exemplos por run; sao
  evidencias de funcionamento, nao o resultado estatistico final.
- **Experimento completo:** pendente. Deve produzir `reports/validation/`,
  `reports/model-selection.json` com status final e `reports/final/`.
- **Print da GPU no VS Code:** pendente de captura manual.
- **Publicacao no GitHub:** pendente de configurar o remote e fazer o push.

O experimento completo e iniciado por:

```powershell
.\scripts\run_experiments.ps1
```

O script treina A/B/C com o conjunto de treino completo, compara todos somente
na validacao, escolhe o vencedor e usa o conjunto de teste apenas para comparar
o modelo-base com esse vencedor. Nao se deve promover um resultado do piloto a
modelo final.

As outras duas pendencias dependem de uma acao externa do grupo. Para a
captura, abra o terminal integrado do VS Code e siga
`docs/APRESENTACAO.md`. Para publicar:

```powershell
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

Substitua a URL pelo repositorio real; nao invente nem reutilize credenciais em
arquivos do projeto.

## Requisito adicional de datas

A LLM preserva a expressao original em `prazo_texto`. O `DateResolver` usa a
data atual do fuso `America/Sao_Paulo` no frontend e converte de forma
deterministica.

Exemplo com referencia em 14/10/2026:

| Entrada | Data resolvida | Comportamento |
|---|---|---|
| `sexta` | 16/10/2026 | Pergunta se essa foi a data desejada |
| `amanha` | 15/10/2026 | Pergunta se essa foi a data desejada |
| `daqui a tres dias` | 17/10/2026 | Pergunta se essa foi a data desejada |
| `22/10/2026` | 22/10/2026 | Data explicita; ainda confirma a operacao |
| `dia 22 de outubro` | 22/10/2026 | Data explicita; ainda confirma a operacao |
| uma data passada | — | Operacao bloqueada |

Se o nome do dia for igual ao dia atual, ele e interpretado como a proxima
ocorrencia, sete dias depois, evitando agendar silenciosamente para um horario
que talvez ja tenha passado.

## Limites intencionais

- Banco e catalogo sao sinteticos.
- Nao ha integracao com ERP real.
- Toda acao que altera dados exige confirmacao.
- O modelo nao calcula valores nem altera estoque diretamente.
- A POC nao processa anexos, PDFs ou imagens.
- Os pesos do modelo nao sao versionados no Git.
