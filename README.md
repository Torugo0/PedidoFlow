# PedidoFlow Local

O PedidoFlow e uma prova de conceito de automacao de pedidos com uma LLM
pequena executada localmente. O usuario escreve uma solicitacao em portugues,
o modelo escolhe uma operacao e extrai seus argumentos, e o backend valida e
executa a acao em um banco SQLite.

Ele nao e um chatbot generico. O modelo so pode selecionar cinco saidas:

- `criar_pedido`;
- `consultar_pedido`;
- `cancelar_pedido`;
- `alterar_entrega`;
- `nao_suportada`.

## Estado atual do projeto

A implementacao funcional esta concluida: interface, interpretacao por LLM ou
fallback deterministico, confirmacao de datas, regras de negocio e persistencia
SQLite funcionam de ponta a ponta. A verificacao local mais recente executou os
**49 testes automatizados com sucesso**.

O dataset final tambem esta pronto, com **2.400 exemplos de treino, 300 de
validacao e 600 de teste**. As 3.300 entradas sao unicas, e os splits usam
familias de templates separadas para reduzir vazamento entre treino e
avaliacao.

As evidencias de treino disponiveis ate agora sao preliminares: ha um smoke
test, um treino reduzido do run B e um piloto reduzido A/B/C concluido na GPU.
Eles demonstram que o pipeline funciona, mas nao
substituem os experimentos completos. Antes da entrega academica ainda e
necessario executar `scripts/run_experiments.ps1`, que gera
`reports/validation`, seleciona o vencedor somente pela validacao e depois cria
`reports/final` com a avaliacao de teste.

Tambem permanecem externas ao codigo duas tarefas do grupo: capturar no VS Code
o print da GPU funcionando e publicar o repositorio em uma URL real do GitHub.

## Exemplo

Entrada:

> Cadastre para o Mercado Central duas caixas de cafe. Entregar na Avenida
> Brasil, 500 ate sexta.

Chamada interna produzida pela LLM:

```json
{
  "acao": "criar_pedido",
  "argumentos": {
    "cliente": "Mercado Central",
    "itens": [
      {"produto": "cafe", "quantidade": 2, "unidade": "caixa"}
    ],
    "endereco_entrega": "Avenida Brasil, 500",
    "prazo_texto": "sexta"
  },
  "campos_faltantes": []
}
```

Se a data de referencia for `14/10/2026`, o backend resolve `sexta` para
`16/10/2026` e pergunta:

> Voce quis dizer sexta-feira, 16/10/2026? Confirma a criacao do pedido?

O estoque e o banco so sao alterados depois da confirmacao.

## Arquitetura

```text
Solicitacao em PT-BR
        |
        v
OrderInterpreter (Qwen3-1.7B + adapter LoRA)
        |
        v
ToolCall: acao + argumentos + campos_faltantes
        |
        v
PedidoService + DateResolver + validacoes de negocio
        |
        v
Previa protegida por token e confirmacao explicita
        |
        v
SQLiteRepository: pedidos, itens e estoque
```

A LLM interpreta texto. Ela nao calcula preco, nao decide estoque, nao grava no
banco e nao converte datas. Essas responsabilidades ficam em codigo
deterministico e testavel.

## Requisitos

- Windows 10/11;
- Python 3.10;
- GPU NVIDIA compativel com CUDA;
- aproximadamente 12 GB livres para ambiente, cache do modelo e checkpoints;
- Git.

Ambiente validado neste computador:

- NVIDIA GeForce RTX 4060, 8 GB;
- PyTorch 2.11.0 com CUDA 12.8;
- compute capability 8.9;
- QLoRA em BF16;
- pico de 3,14 GB de VRAM no smoke training.

O pacote PyTorch `cu128` ja inclui o runtime CUDA usado por este projeto; por
isso o Toolkit completo e o comando `nvcc` nao sao necessarios para executar
treino e inferencia. O driver 610.88 e compativel e o teste matricial CUDA foi
executado com sucesso. Se a disciplina exigir especificamente um print de
`nvcc --version`, a instalacao do CUDA Toolkit e uma evidencia adicional,
separada do runtime que ja esta funcionando.

## Instalacao

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Valide a GPU com uma operacao CUDA real:

```powershell
.\.venv\Scripts\python.exe scripts\check_gpu.py --output reports\gpu-info.json
```

O resultado deve conter `"status": "GPU CUDA funcionando"` e o nome da placa.

## Executar a aplicacao

```powershell
.\.venv\Scripts\python.exe app.py
```

O navegador abrira em `http://127.0.0.1:7860`.

Fluxo da tela:

1. Digite uma solicitacao.
2. Clique em **Analisar solicitacao**.
3. Confira a chamada de funcao e a data resolvida.
4. Marque a confirmacao.
5. Clique em **Executar operacao**.
6. Consulte o protocolo, pedidos e estoque.

Enquanto nenhum adapter escolhido estiver disponivel, a tela usa um parser local
deterministico e identifica claramente esse modo. Depois dos experimentos,
`training/select_best.py` registra o vencedor em `reports/model-selection.json`.
Tambem e possivel definir explicitamente o caminho em `PEDIDOFLOW_ADAPTER`.

Neste checkout existe um adapter **preliminar** B para demonstrar a integracao,
mas ele nao e selecionado automaticamente como vencedor final. Para testa-lo de
forma consciente no PowerShell:

```powershell
.\scripts\run_app.ps1 -AdapterPath "outputs\run_b\final_adapter"
```

## Dataset sintetico

Gere os tres conjuntos reproduziveis:

```powershell
.\.venv\Scripts\python.exe training\generate_dataset.py
```

Sao gerados:

- `data/train.jsonl`: 2.400 exemplos;
- `data/validation.jsonl`: 300 exemplos;
- `data/test.jsonl`: 600 exemplos.

As 3.300 entradas geradas sao unicas. As familias de templates sao diferentes
em cada split, portanto uma frase-modelo usada no treino nao aparece no teste.

## Treinamento

O modelo escolhido e `Qwen/Qwen3-1.7B`, ajustado com QLoRA 4-bit NF4. Os tres
experimentos variam apenas learning rate e rank LoRA:

```powershell
.\.venv\Scripts\python.exe training\train.py --config configs\run_a.json
.\.venv\Scripts\python.exe training\train.py --config configs\run_b.json
.\.venv\Scripts\python.exe training\train.py --config configs\run_c.json
```

Para validar rapidamente a instalacao antes de um treino longo:

```powershell
.\.venv\Scripts\python.exe training\train.py `
  --config configs\run_a.json `
  --output-dir outputs\smoke `
  --max-train-samples 16 `
  --max-eval-samples 8
```

Para executar um piloto comparavel A/B/C na GPU (32 exemplos por run), use:

```powershell
.\scripts\run_pilot.ps1
```

O piloto verifica os tres conjuntos de hiperparametros, mas seus numeros nao
substituem o experimento final com os 2.400 exemplos.

O piloto A/B/C ja foi concluido: cada run usou 32 exemplos de treino, 16 de
validacao e uma avaliacao parcial de 10 exemplos. O run C obteve o melhor
resultado nesse recorte, mas isso nao o torna vencedor final. Os numeros estao
em `reports/RESULTADOS_PRELIMINARES.md`.

O treino preliminar e o piloto servem como evidencia de execucao local na GPU.
Os diretorios `reports/validation`, `reports/final` e o arquivo
`reports/model-selection.json` so representam o resultado academico final
depois da execucao completa de:

```powershell
.\scripts\run_experiments.ps1
```

Enquanto esses artefatos nao existirem com status final, nenhum adapter e
anunciado automaticamente como vencedor.

Os scripts abortam se CUDA nao estiver disponivel, evitando executar os
experimentos em CPU por engano.

Avalie A/B/C no conjunto de validacao e selecione o vencedor por essas metricas,
sem consultar o conjunto de teste:

```powershell
.\.venv\Scripts\python.exe training\evaluate.py `
  --adapter-path outputs\run_b\final_adapter `
  --dataset-file data\validation.jsonl `
  --output-dir reports\validation\run_b
.\.venv\Scripts\python.exe training\select_best.py `
  --report-root reports\validation
```

## Avaliacao

Depois da selecao por validacao, avalie o modelo original e apenas o adapter
vencedor no conjunto de teste. O script `scripts/run_experiments.ps1` automatiza
essa separacao. Exemplo do modelo original:

```powershell
.\.venv\Scripts\python.exe training\evaluate.py --output-dir reports\base
```

Exemplo do adapter ja escolhido:

```powershell
.\.venv\Scripts\python.exe training\evaluate.py `
  --adapter-path outputs\run_b\final_adapter `
  --output-dir reports\final\run_b
```

Metricas calculadas:

- JSON valido;
- conformidade com o schema;
- acuracia da acao;
- acuracia de campos dos argumentos;
- exact match dos argumentos;
- exact match da chamada completa;
- deteccao de campos faltantes;
- latencia media;
- pico de VRAM;
- resultados separados por acao.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Os testes cobrem datas relativas, interpretacao, campos faltantes, confirmacao
unica, criacao do pedido, alteracao de estoque, dataset, metricas e integridade
dos artefatos. A ultima execucao local terminou com **49 testes aprovados**.

## Organizacao

```text
app.py                     Interface Gradio
src/pedidoflow/            Dominio, datas, banco, servico e interpretador
training/                  Dataset, fine-tuning, avaliacao e metricas
configs/                   Hiperparametros dos experimentos A, B e C
scripts/                   Diagnostico de GPU e automacoes PowerShell
tests/                     Testes automatizados
data/                      Splits sinteticos e banco local ignorado pelo Git
reports/                   Evidencias e resultados
models/                    Local opcional para adapters; pesos ignorados pelo Git
docs/                      Arquitetura, requisitos e roteiro de apresentacao
```

Mais detalhes estao em [docs/REQUISITOS.md](docs/REQUISITOS.md),
[docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md) e
[docs/APRESENTACAO.md](docs/APRESENTACAO.md). A publicacao esta descrita em
[docs/GITHUB.md](docs/GITHUB.md).

## Observacao sobre pesos

Checkpoints e arquivos `.safetensors` nao sao enviados ao GitHub. Eles podem ter
varios gigabytes. O repositorio versiona codigo, configuracoes, dataset,
metricas e instrucoes para reproduzir o adapter.
