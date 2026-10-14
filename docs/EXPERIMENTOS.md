# Plano de experimentos

## Hipotese

O fine-tuning supervisionado deve melhorar a conformidade com o schema e a
extracao dos argumentos em relacao ao Qwen3-1.7B original.

## Variaveis controladas

- modelo base;
- dataset e splits;
- seed 42;
- quantizacao NF4 4-bit;
- batch por GPU;
- gradient accumulation;
- comprimento maximo 512;
- numero de epocas;
- prompt do sistema;
- conjunto de teste.

## Experimentos

| Run | LoRA rank | Alpha | Learning rate | Epocas |
|---|---:|---:|---:|---:|
| A | 8 | 16 | 1e-4 | 2 |
| B | 8 | 16 | 2e-4 | 2 |
| C | 16 | 32 | 2e-4 | 2 |

A comparacao A x B mede o efeito da taxa de aprendizado. B x C mede o efeito
do rank do adapter.

## Dois tipos de execucao

### Smoke test

Usa poucos exemplos para provar que download, quantizacao, treino, salvamento e
avaliacao funcionam na GPU. Seus numeros nao devem ser apresentados como
qualidade final do modelo.

### Experimento final

Usa os 2.400 exemplos de treino e os 300 de validacao para comparar A/B/C. O
conjunto de 600 exemplos de teste permanece fechado durante essa escolha. So o
adapter vencedor e o modelo base sao avaliados no teste; esses sao os resultados
finais que devem ir para a apresentacao.

## Metricas

- `valid_json_rate`: a resposta inteira e um objeto JSON parseavel.
- `schema_valid_rate`: possui somente acoes e argumentos permitidos.
- `action_accuracy`: escolheu a funcao correta.
- `argument_field_accuracy`: proporcao de campos atomicos corretos.
- `arguments_exact_match_rate`: todos os argumentos estao exatos.
- `missing_fields_exact_match_rate`: campos ausentes foram identificados.
- `exact_match_rate`: objeto completo identico ao esperado.
- latencia e pico de VRAM.

JSON invalido nao e reparado durante a avaliacao; conta como erro.

## Reproducao

```powershell
.\scripts\run_experiments.ps1
```

As metricas A/B/C de selecao ficam em `reports/validation/`. Ao final,
`training/select_best.py` registra o vencedor em
`reports/model-selection.json`; esse e o adapter que o frontend carrega. A
selecao prioriza exact match e usa schema, acuracia de campos e latencia como
desempates. Depois, a avaliacao final do base e do vencedor fica em
`reports/final/`. Cada pasta recebe `metrics.json` e `predictions.jsonl`.

Essa separacao evita escolher hiperparametros olhando o teste e preserva a
validade da comparacao final.

Os resumos registram SHA-256 dos datasets, configs e adapters. A selecao final
so aceita metricas cujo hash corresponda ao adapter e ao split usados no treino;
se um run for sobrescrito, ele precisa ser avaliado e selecionado novamente.
