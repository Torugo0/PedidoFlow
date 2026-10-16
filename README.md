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
(ou o modo de contingência, se o adapter não estiver disponível)
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

- Windows 10 ou 11;
- Python 3.10 de 64 bits disponível pelo comando `python`;
- GPU NVIDIA e driver compatível com CUDA 12.8;
- conexão com a internet durante a instalação e o primeiro carregamento do modelo;
- aproximadamente 12 GB livres para ambiente, cache e treinamento.

O Git só é necessário para clonar o repositório. Quem recebeu o arquivo ZIP pode executar o projeto sem instalar o Git.

Ambiente validado: NVIDIA GeForce RTX 4060 de 8 GB, PyTorch 2.11.0, CUDA 12.8, compute capability 8.9 e QLoRA 4-bit NF4 em BF16.

## Início rápido: instalação e execução

### 1. Obtenha e abra o projeto

Se recebeu o arquivo ZIP, extraia todo o conteúdo e abra a pasta extraída no VS Code.

Se recebeu acesso ao repositório privado, também pode baixar pelo PowerShell:

```powershell
git clone https://github.com/Torugo0/PedidoFlow.git
Set-Location .\PedidoFlow
```

No VS Code, abra **Terminal > Novo Terminal**. Confirme que o terminal é PowerShell e que o caminho mostrado termina na pasta que contém `setup.ps1`, `run.ps1` e `app.py`.

### 2. Confira Python e GPU

```powershell
python --version
nvidia-smi
```

O ambiente usado no desenvolvimento possui Python 3.10 e uma NVIDIA GeForce RTX 4060. O comando `nvidia-smi` deve reconhecer a placa e o driver.

### 3. Prepare o ambiente — somente na primeira execução

Execute o comando abaixo e aguarde até ele terminar e o prompt do PowerShell reaparecer:

```powershell
.\setup.ps1
```

O `setup.ps1` cria a pasta `.venv`, instala as dependências, instala o projeto e executa um teste real na GPU. O diagnóstico é salvo em `results/gpu-info.json` e deve informar `GPU CUDA funcionando`.

Se o PowerShell bloquear a execução do script, libere scripts somente para o terminal atual e tente novamente:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

### 4. Inicie a aplicação

Depois que o setup terminar, execute este segundo comando separadamente:

```powershell
.\run.ps1
```

> **Importante:** não escreva `.\setup.ps1 .\run.ps1` na mesma linha. Primeiro execute o setup, aguarde sua conclusão e somente depois execute o run.

O navegador deve abrir automaticamente em [http://127.0.0.1:7860](http://127.0.0.1:7860). Se ele não abrir, copie esse endereço para o navegador.

`127.0.0.1` é um endereço local: a aplicação fica disponível apenas no computador em que `run.ps1` está sendo executado. Mantenha o terminal aberto durante o uso. Para encerrar, volte ao terminal e pressione `Ctrl+C`.

Não é necessário ativar `.venv` manualmente; os scripts já usam o Python correto.

### 5. Próximas execuções

Depois da instalação inicial, basta abrir o PowerShell na pasta do projeto e executar:

```powershell
.\run.ps1
```

Execute `setup.ps1` novamente somente se a pasta `.venv` tiver sido removida ou se as dependências forem alteradas.

### Modelo usado na demonstração

A aplicação procura o adapter treinado e, quando ele está disponível, carrega o modelo-base `Qwen/Qwen3-1.7B`. No primeiro pedido, o download do modelo-base pelo Hugging Face pode levar alguns minutos.

- O adapter treinado está em `models/adapter_demo` e acompanha o projeto no GitHub e no ZIP.
- O modelo-base completo não é enviado; ele é baixado automaticamente do Hugging Face no primeiro uso.
- Sem o adapter, a interface, as datas, as confirmações e o banco continuam funcionando, mas a interpretação não é feita pela LLM treinada.

Para indicar um adapter manualmente:

```powershell
.\run.ps1 -AdapterPath ".\models\adapter_demo"
```

### Uso da interface

1. Escreva a solicitação e clique em **Entender solicitação**.
2. Confira o resumo e a data exata apresentada; não é necessário preencher campos nem editar JSON.
3. Confirme a data relativa, quando solicitado, e depois confirme a operação.
4. Confira o protocolo, os pedidos e o estoque atualizados.

Exemplos para testar:

```text
Cadastre duas caixas de café para o Mercado Central, na Rua das Flores, 120, com entrega na sexta.
Consulte o pedido 1.
Altere a entrega do pedido 1 para a próxima terça.
```

### Banco de dados

Não é necessário instalar nem iniciar um servidor de banco. Ao iniciar a aplicação, o SQLite cria automaticamente `data/pedidoflow.db`, com as tabelas `produtos`, `pedidos` e `pedido_itens` e um estoque inicial.

Os pedidos e o estoque permanecem salvos entre execuções. O banco e seus arquivos auxiliares `-wal` e `-shm` são locais, estão ignorados pelo Git e não são enviados ao GitHub.

### Solução de problemas

| Situação | Solução |
|---|---|
| PowerShell informa que a execução de scripts foi desabilitada | Execute `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e tente novamente. A liberação vale somente para o terminal atual. |
| Aparece `Ambiente .venv nao encontrado` | Execute `.\setup.ps1`, aguarde terminar e depois execute `.\run.ps1`. |
| Aparece `CUDA indisponível` | Execute `nvidia-smi`, atualize o driver NVIDIA e confirme que a GPU é compatível com a versão CUDA indicada em `requirements.txt`. |
| O navegador mostra `ERR_CONNECTION_REFUSED` | O servidor não está em execução. Rode `.\run.ps1` e mantenha o terminal aberto. |
| A porta `7860` já está ocupada | Encerre a outra instância do PedidoFlow com `Ctrl+C` e execute `.\run.ps1` novamente. |
| A interface informa modo de contingência | O adapter não foi localizado. Confirme a existência de `models/adapter_demo` ou informe o caminho com `-AdapterPath`. |
| O primeiro pedido demora | O modelo-base pode estar sendo baixado. Mantenha a conexão com a internet e aguarde o carregamento. |

## Modelo, treinamento e resultados

Foi escolhido o `Qwen/Qwen3-1.7B` por ser pequeno, multilíngue e compatível com QLoRA em uma GPU de 8 GB. O modelo não foi criado do zero: foi realizado um fine-tuning local que gerou o adapter LoRA disponível em `models/adapter_demo`.

### Dataset

O projeto disponibiliza 3.300 entradas sintéticas e únicas:

| Conjunto | Exemplos disponíveis |
|---|---:|
| Treino | 2.400 |
| Validação | 300 |
| Teste | 600 |

Para manter a POC simples e compatível com o tempo e o hardware disponíveis, o adapter entregue foi treinado com **400 exemplos de treino e 100 de validação**. Os conjuntos completos permanecem no repositório para consulta ou extensões futuras.

### Teste de parâmetros

Também foi executado na RTX 4060 um piloto A/B/C. Cada configuração usou 32 exemplos de treino, 16 de validação durante o treino e 10 exemplos na avaliação comparativa.

| Experimento | Rank | Alpha | Learning rate | Correspondência exata |
|---|---:|---:|---:|---:|
| A | 8 | 16 | 1e-4 | 0% |
| B | 8 | 16 | 2e-4 | 10% |
| C | 16 | 32 | 2e-4 | 40% |

O piloto mostra que configurações diferentes produziram resultados diferentes. A configuração C foi a melhor **somente nesse microteste de 10 casos**; como rank e alpha mudaram juntos, o experimento não isola o efeito de cada parâmetro nem permite generalizar a conclusão.

O adapter entregue continua sendo a configuração B: ele recebeu o treinamento maior, com 400 exemplos de treino e 100 de validação, e foi avaliado separadamente em 20 casos. Os adapters A/B/C do piloto eram execuções pequenas voltadas apenas à comparação de parâmetros.

### Avaliação do adapter entregue

O Qwen-base e o `adapter_demo`, treinado com a configuração B em uma amostra maior, foram avaliados nos mesmos 20 exemplos:

| Métrica | Modelo-base | Adapter B |
|---|---:|---:|
| JSON válido | 100% | 100% |
| Schema válido | 0% | 90% |
| Ação correta | 100% | 90% |
| Campos corretos | 11,22% | 98,31% |
| Correspondência exata | 0% | 85% |

O resultado mostra que o ajuste aprendeu o contrato JSON do PedidoFlow: a validade de schema passou de 0% para 90% e a correspondência exata passou de 0% para 85%. A avaliação também registra latência, pico de VRAM e resultados por ação.

Esta é uma **avaliação final da POC em escala reduzida**. Os tamanhos das amostras são informados para deixar o resultado transparente e auditável, sem apresentá-lo como uma avaliação estatística de produção.

Evidências disponíveis:

- `results/RESULTADOS.md`: metodologia, métricas e limitações;
- `results/metricas.json`: resultados estruturados;
- `results/comparacao_modelos.png`: modelo-base contra adapter;
- `results/comparacao_parametros.png`: piloto A/B/C;
- `results/gpu-info.json`: GPU, CUDA, PyTorch, VRAM e teste CUDA;
- `results/gpu-vscode-nvidia-smi.png`: GPU reconhecida no terminal do VS Code;
- `results/gpu-vscode-cuda-test.png`: execução real do diagnóstico CUDA.

O script `run_experiments.ps1` mantém disponível uma extensão opcional com o dataset completo, mas ela não é necessária para executar ou demonstrar a versão entregue.

## Testes automatizados

```powershell
.\.venv\Scripts\python.exe -m pytest
```

A última verificação aprovou **54 testes**, cobrindo datas, interpretação, campos ausentes, confirmação, operações no banco, dataset, métricas, interface e artefatos.

Esses testes verificam as regras e a integração do sistema e podem rodar na CPU. O fine-tuning, a avaliação da LLM e o teste de carregamento do adapter foram executados com CUDA na GPU, conforme `results/gpu-info.json` e `results/RESULTADOS.md`.

## Evidência da GPU

No terminal integrado do VS Code, execute:

```powershell
nvidia-smi
.\.venv\Scripts\python.exe training\check_gpu.py --output results\gpu-info.json
```

O diagnóstico realiza uma multiplicação de matrizes na GPU. As capturas abaixo comprovam que a NVIDIA GeForce RTX 4060 foi reconhecida no VS Code e que o PyTorch executou o teste com CUDA.

### GPU reconhecida pelo driver NVIDIA

![NVIDIA GeForce RTX 4060 reconhecida pelo nvidia-smi no terminal do VS Code](results/gpu-vscode-nvidia-smi.png)

### Teste real do PyTorch com CUDA

![Diagnóstico do PyTorch mostrando GPU CUDA funcionando](results/gpu-vscode-cuda-test.png)

## Estrutura

```text
app.py                 Interface Gradio
src/pedidoflow/        Domínio, datas, banco e interpretação
training/              Dataset, treino, avaliação e diagnóstico
training/configs/      Parâmetros A, B e C
data/                  Treino, validação e teste
models/adapter_demo/   Adapter LoRA treinado usado na demonstração
results/               Métricas, gráficos e evidências
tests/                 Testes automatizados
setup.ps1              Prepara o ambiente
run.ps1                Inicia a aplicação
run_experiments.ps1    Extensão opcional com experimentos completos
```

## GitHub e entrega

Repositório privado do projeto: [Torugo0/PedidoFlow](https://github.com/Torugo0/PedidoFlow)

Para baixar o projeto em outro computador com acesso autorizado:

```powershell
git clone https://github.com/Torugo0/PedidoFlow.git
```

O professor precisa ser adicionado como colaborador ou receber acesso antes de abrir o link. O repositório contém código, configurações, dataset, resultados e o adapter LoRA treinado. O modelo-base Qwen é baixado no primeiro uso. Não envie `.venv`, caches, banco SQLite, checkpoints ou credenciais.

Ao compactar a pasta manualmente, inclua `models/adapter_demo` e não inclua `.venv`, `.git`, caches, `data/pedidoflow.db` ou checkpoints intermediários.

## Pendências antes da entrega final

1. Resolver a exigência de 4 a 5 integrantes; atualmente há 3 integrantes identificados.
2. Dar acesso ao professor no repositório privado.
3. Criar o ZIP final, excluindo `.venv`, `.git`, caches, banco SQLite e checkpoints intermediários.
