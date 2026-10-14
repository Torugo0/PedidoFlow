# PedidoFlow Local

POC acadêmica que usa uma LLM pequena, executada localmente, para interpretar pedidos escritos em português e transformá-los em operações seguras de criação, consulta, alteração e cancelamento.

O projeto não é um chatbot genérico. A LLM identifica a ação e extrai os argumentos; datas, estoque, regras de negócio, confirmação e banco ficam sob responsabilidade de código determinístico e testável.

## Integrantes

| Integrante | RM |
|---|---:|
| Gabriel Machado Carrara Pimentel | 99880 |
| Lourenzo Ramos | 99951 |
| Vitor Hugo Gonçalves Rodrigues | 97758 |

## Objetivo

Empresas recebem solicitações como texto livre:

> Cadastre para o Mercado Central duas caixas de café. Entregar na Avenida Brasil, 500 até sexta.

O PedidoFlow interpreta a mensagem, valida os dados, apresenta uma prévia e somente executa a operação após a confirmação do usuário.

O JSON não é o resultado final e não aparece para o usuário do comércio. Ele é apenas o contrato interno entre a LLM e o backend:

```json
{
  "acao": "criar_pedido",
  "argumentos": {
    "cliente": "Mercado Central",
    "itens": [{"produto": "cafe", "quantidade": 2, "unidade": "caixa"}],
    "endereco_entrega": "Avenida Brasil, 500",
    "prazo_texto": "sexta"
  }
}
```

Depois dessa etapa, o backend executa uma ação real no banco SQLite.

## Funcionalidades

- criar, consultar, alterar e cancelar pedidos;
- atualizar o estoque automaticamente;
- identificar campos ausentes e recusar ações fora do escopo;
- exigir confirmação para toda operação que modifica dados.

## Fluxo da solução

```text
Solicitação em português
          ↓
Qwen3-1.7B interpreta a intenção e os campos
          ↓
Backend valida produto, estoque, regras e data
          ↓
Usuário confere a prévia e confirma
          ↓
Operação é executada no SQLite
```

Essa separação impede que a LLM grave no banco, altere estoque ou invente regras diretamente.

## Datas relativas e confirmação

Expressões como `sexta`, `amanhã`, `depois de amanhã` e `próxima terça` são convertidas usando a data atual no fuso `America/Sao_Paulo`.

Exemplo com data de referência em **14/10/2026**:

```text
Entrada: Entregar até sexta.
Sistema: Você quis dizer sexta-feira, 16/10/2026?
```

O banco e o estoque não mudam antes da confirmação. A data exata fica vinculada à prévia para não ser recalculada caso o dia mude. Datas passadas são bloqueadas e horários são recusados, pois a POC trabalha somente com datas de entrega.

## Requisitos

Windows 10/11, Python 3.10, Git, GPU NVIDIA compatível com CUDA e cerca de 12 GB livres para ambiente, cache e treinamento.

Ambiente validado: NVIDIA GeForce RTX 4060 de 8 GB, PyTorch 2.11.0, CUDA 12.8, compute capability 8.9 e QLoRA 4-bit NF4 em BF16.

## Instalação e execução

Abra o PowerShell na pasta do projeto:

```powershell
.\setup.ps1
.\run.ps1
```

A interface estará em [http://127.0.0.1:7860](http://127.0.0.1:7860). Mantenha o terminal do `run.ps1` aberto enquanto estiver usando o sistema.

O `setup.ps1` cria o ambiente virtual e instala as dependências. O `run.ps1` usa `models/adapter_demo`; sem ele, a aplicação ainda funciona com o interpretador determinístico de contingência.

### Uso da interface

1. Escreva a solicitação e clique em **Entender solicitação**.
2. Confira o resumo legível e a data resolvida; não é preciso preencher campos ou editar JSON.
3. Clique no botão de confirmação exibido para a operação.
4. Confira o protocolo, os pedidos e o estoque.

### Banco de dados

O banco SQLite é criado automaticamente em `data/pedidoflow.db` quando a aplicação inicia. Ele possui as tabelas `produtos`, `pedidos` e `pedido_itens`. O arquivo do banco e seus auxiliares `-wal` e `-shm` são dados locais de execução e não são enviados ao GitHub.

Exemplos:

```text
Cadastre duas caixas de café para o Mercado Central, na Rua das Flores, 120, com entrega na sexta.
Consulte o pedido 1.
Altere a entrega do pedido 1 para a próxima terça.
```

## Modelo e dataset

Foi escolhido o `Qwen/Qwen3-1.7B` por ser pequeno, multilíngue e compatível com QLoRA em uma GPU de 8 GB.

| Conjunto | Exemplos |
|---|---:|
| Treino | 2.400 |
| Validação | 300 |
| Teste | 600 |

As 3.300 entradas são únicas. Os três conjuntos usam famílias de templates diferentes para reduzir vazamento entre treino e avaliação.

## Treinamento e parâmetros

Modelo, dataset, seed, épocas e quantização permanecem fixos. Os experimentos variam taxa de aprendizado e rank LoRA:

| Experimento | Rank | Alpha | Learning rate |
|---|---:|---:|---:|
| A | 8 | 16 | 1e-4 |
| B | 8 | 16 | 2e-4 |
| C | 16 | 32 | 2e-4 |

Execute o processo completo com:

```powershell
.\run_experiments.ps1
```

O script treina A/B/C na GPU, compara os três somente na validação, escolhe o melhor adapter e, por fim, compara o vencedor com o modelo-base no teste. Métricas e gráficos são gravados em `results/`. O conjunto de teste não é usado para escolher hiperparâmetros.

## Resultados preliminares

Uma execução reduzida validou todo o pipeline na RTX 4060. Em 20 exemplos:

| Métrica | Modelo-base | Adapter B |
|---|---:|---:|
| JSON válido | 100% | 100% |
| Schema válido | 0% | 90% |
| Ação correta | 100% | 90% |
| Campos corretos | 11,22% | 98,31% |
| Correspondência exata | 0% | 85% |

Esses números comprovam a execução do pipeline, mas não substituem o experimento completo. Consulte `results/RESULTADOS.md`. A avaliação também registra latência, pico de VRAM e resultados por ação.

## Testes automatizados

```powershell
.\.venv\Scripts\python.exe -m pytest
```

A última verificação aprovou **49 testes**, cobrindo datas, interpretação, campos ausentes, confirmação, operações no banco, dataset, métricas e artefatos.

## Evidência da GPU

No terminal integrado do VS Code, execute:

```powershell
nvidia-smi
.\.venv\Scripts\python.exe training\check_gpu.py --output results\gpu-info.json
```

O diagnóstico realiza uma multiplicação de matrizes na GPU. No print da entrega, deixe visíveis o VS Code, a RTX 4060, PyTorch, CUDA e `GPU CUDA funcionando`. Salve como `results/gpu-vscode.png`.

## Estrutura

```text
app.py                 Interface Gradio
src/pedidoflow/        Domínio, datas, banco e interpretação
training/              Dataset, treino, avaliação e diagnóstico
training/configs/      Parâmetros A, B e C
data/                  Treino, validação e teste
models/adapter_demo/   Adapter preliminar usado na demonstração
results/               Métricas, gráficos e evidências
tests/                 Testes automatizados
setup.ps1              Prepara o ambiente
run.ps1                Inicia a aplicação
run_experiments.ps1    Executa os experimentos completos
```

## Atendimento aos requisitos do CP

| Requisito | Atendimento |
|---|---|
| Problema específico | Automação de pedidos em PT-BR |
| LLM escolhida | Qwen3-1.7B |
| Treino local | Pipeline QLoRA validado na RTX 4060 |
| Parâmetros diferentes | Experimentos A, B e C |
| Avaliação | Métricas automáticas e comparação com o modelo-base |
| GPU | Treino e avaliação interrompem sem CUDA |
| Frontend | Gradio com prévia e confirmação |
| Print no VS Code | Comandos e destino preparados |
| GitHub | Código, dataset, resultados e reprodução documentados |

## Onde estão os pesos?

O modelo-base não fica no projeto: ele é baixado do Hugging Face e armazenado no cache local. O adapter de demonstração está em `models/adapter_demo` (aproximadamente 44 MB).

No GitHub, pesos e checkpoints são ignorados para evitar um repositório pesado. O código, as configurações, o dataset e as métricas permitem reproduzir o treinamento.

## GitHub e entrega

Repositório privado do projeto: [Torugo0/PedidoFlow](https://github.com/Torugo0/PedidoFlow)

Para baixar o projeto em outro computador com acesso autorizado:

```powershell
git clone https://github.com/Torugo0/PedidoFlow.git
```

O professor precisa ser adicionado como colaborador ou receber acesso antes de abrir o link. Não envie `.venv`, caches, banco SQLite, checkpoints ou credenciais.

Ao compactar a pasta manualmente, inclua `models/adapter_demo` e não inclua `.venv`, `.git`, caches, `data/pedidoflow.db` ou checkpoints intermediários.

## Estado da entrega

- aplicação, frontend, banco, datas, dataset e testes: concluídos;
- smoke test, treino reduzido e piloto A/B/C em GPU: concluídos;
- experimento completo A/B/C: pendente de execução;
- print da GPU no VS Code: pendente de captura;
- publicação no GitHub: concluída em repositório privado.

Os resultados preliminares não são apresentados como finais. Depois da execução completa, `results/RESULTADOS.md` deve receber o modelo vencedor e as métricas do conjunto de teste.
