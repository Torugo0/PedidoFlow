# Resultados finais da POC reduzida

O PedidoFlow foi desenvolvido como uma prova de conceito local e objetiva. O
modelo-base **Qwen3-1.7B** foi especializado com QLoRA usando **400 exemplos de
treino e 100 exemplos de validação**. O resultado desse treinamento está em
`models/adapter_demo` e é o adapter adotado pela aplicação.

Todos os treinamentos e avaliações descritos nesta página foram executados em
uma **NVIDIA GeForce RTX 4060**, usando CUDA 12.8 e PyTorch 2.11.0+cu128.

## Modelo-base comparado com o adapter treinado

O Qwen original e o Qwen com `adapter_demo` foram avaliados nas mesmas 20
entradas de `data/test.jsonl`, com inferência 4-bit NF4 e BF16.

| Modelo | JSON válido | Schema válido | Ação | Campos | Exact match | Latência média | Pico de VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-1.7B base | 100% | 0% | 100% | 11,22% | 0% | 6,16 s | 1,318 GB |
| Qwen3-1.7B + `adapter_demo` | 100% | 90% | 90% | 98,31% | 85% | 6,45 s | 1,351 GB |

O adapter elevou o *exact match* de 0% para 85% e a precisão dos campos de
11,22% para 98,31%. Isso mostra que o ajuste ensinou ao modelo o formato e os
argumentos esperados pelo PedidoFlow. Em dois dos 20 casos, porém, a ação
prevista não foi a correta.

## Teste de diferentes parâmetros

Também foi realizado um piloto A/B/C para verificar o efeito de configurações
LoRA diferentes. Cada configuração usou **32 exemplos de treino e 16 de
validação**, e foi medida em **10 exemplos de validação**.

| Configuração | Rank LoRA | Alpha | Learning rate | Schema válido | Ação | Campos | Exact match |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 8 | 16 | 0,0001 | 0% | 80% | 5,4054% | 0% |
| B | 8 | 16 | 0,0002 | 10% | 90% | 14,2857% | 10% |
| C | 16 | 32 | 0,0002 | 50% | 90% | 51,8519% | 40% |

Dentro desse piloto reduzido, a configuração C obteve o melhor resultado. Como
rank e alpha mudaram juntos entre B e C, a comparação demonstra apenas que as
configurações produziram resultados diferentes; ela não mede isoladamente o
efeito de cada parâmetro.

O adapter entregue é a configuração B treinada em escala maior, com 400
exemplos de treino e 100 de validação, e avaliada em 20 casos. A configuração C
venceu somente o microteste de 10 casos e não foi adotada como modelo final.

## Conclusão

Para o escopo da POC, as evidências mostram que:

- uma LLM foi treinada localmente em GPU por meio de QLoRA;
- o adapter treinado melhorou substancialmente o preenchimento dos campos e o
  atendimento ao schema;
- diferentes parâmetros foram testados e comparados;
- o modelo treinado está integrado à aplicação em `models/adapter_demo`.

## Limitações

Os resultados são finais **para esta POC reduzida**, mas não representam uma
avaliação de produção. O adapter foi treinado com 400/100 exemplos; a comparação
base × adapter usa 20 casos; e o piloto A/B/C usa 32/16 exemplos por configuração
e mede 10 casos. Amostras maiores e repetições com diferentes sementes seriam
necessárias para estimar a capacidade de generalização com maior confiança.
