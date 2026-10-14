# Resultados preliminares executados

Estes numeros comprovam que o pipeline local de treino e avaliacao funciona na
RTX 4060. Eles **nao sao os resultados finais do CP**: o adapter B foi treinado
com apenas 400 exemplos e 100 de validacao, antes da regeneracao que tornou
todos os textos do dataset unicos.

Base e adapter foram avaliados nos mesmos 20 primeiros exemplos do
`data/test.jsonl` atual, em CUDA, com inferencia 4-bit NF4 e BF16.

| Modelo | JSON valido | Schema valido | Acao | Campos | Exact match | Latencia media | Pico VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-1.7B base | 100% | 0% | 100% | 11,22% | 0% | 6,16 s | 1,318 GB |
| Adapter B preliminar | 100% | 90% | 90% | 98,31% | 85% | 6,45 s | 1,351 GB |

O ganho de exact match mostra que o ajuste aprendeu o contrato de chamadas. A
queda de acuracia de acao em dois exemplos de alteracao deve ser investigada no
treino final; o conjunto de apenas 20 casos e pequeno demais para conclusoes de
qualidade.

## Piloto de parametros A/B/C

O piloto dos tres conjuntos de hiperparametros foi concluido na RTX 4060. Cada
run usou **32 exemplos de treino e 16 de validacao**; a avaliacao abaixo e
parcial e considera somente **10 exemplos de validacao** por run.

| Run | Schema valido | Acao | Campos | Exact match |
|---|---:|---:|---:|---:|
| A | 0% | 80% | 5,4054% | 0% |
| B | 10% | 90% | 14,2857% | 10% |
| C | 50% | 90% | 51,8519% | 40% |

O run C liderou **apenas este piloto reduzido**. Ele nao e o vencedor final: a
selecao oficial deve usar os tres treinos completos e todo o conjunto de
validacao, sem consultar o teste. Somente depois dessa selecao o modelo-base e
o vencedor podem ser avaliados no conjunto de teste.

Para obter resultados finais, execute `scripts/run_experiments.ps1`. O fluxo
treina A/B/C no dataset unico completo, escolhe hiperparametros pela validacao e
abre o teste somente para o modelo base e o vencedor.
