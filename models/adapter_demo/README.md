---
base_model: Qwen/Qwen3-1.7B
library_name: peft
pipeline_tag: text-generation
tags:
  - lora
  - qlora
  - portuguese
  - tool-use
  - structured-output
---

# Adapter PedidoFlow

Adapter LoRA treinado localmente para transformar solicitações de pedidos em
português em chamadas de função JSON usadas pelo backend do PedidoFlow.

## Treinamento

- modelo-base: `Qwen/Qwen3-1.7B`;
- método: QLoRA 4-bit NF4 com BF16;
- configuração: rank 8, alpha 16, dropout 0,05 e learning rate 2e-4;
- amostra: 400 exemplos de treino e 100 de validação;
- hardware: NVIDIA GeForce RTX 4060 de 8 GB;
- ambiente: PyTorch 2.11.0+cu128 e CUDA 12.8.
- SHA-256 dos pesos: `1712ef1231670af22c84344f6ce0f8ca956279d06928c7caebb085310408704b`.

O adapter contém somente os ajustes aprendidos. O modelo-base não está nesta
pasta e é baixado do Hugging Face no primeiro uso.

## Avaliação da POC

Modelo-base e adapter foram avaliados nos mesmos 20 casos.

| Métrica | Modelo-base | Com adapter |
|---|---:|---:|
| JSON válido | 100% | 100% |
| Schema válido | 0% | 90% |
| Ação correta | 100% | 90% |
| Campos corretos | 11,22% | 98,31% |
| Correspondência exata | 0% | 85% |

Os detalhes, o piloto de hiperparâmetros e as limitações estão em
`../../results/RESULTADOS.md`.

## Uso

O `app.py` encontra esta pasta automaticamente. Execute `setup.ps1` uma vez e
depois `run.ps1`; no primeiro pedido, aguarde o download e o carregamento do
Qwen-base.

## Limitações

Este adapter foi produzido para uma POC acadêmica e para o domínio sintético do
PedidoFlow. Os resultados são amostrais e não devem ser generalizados para
produção ou para documentos reais sem uma avaliação adicional.
