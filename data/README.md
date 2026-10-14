# Dados

Os arquivos `train.jsonl`, `validation.jsonl` e `test.jsonl` sao sinteticos e
reproduziveis com `training/generate_dataset.py`.

Cada linha contem:

- identificador;
- split;
- familia do template;
- texto de entrada;
- objeto JSON esperado.

O banco `pedidoflow.db` e criado automaticamente para a demonstracao e fica
fora do Git.

Cada split possui entradas de texto unicas. Na geracao padrao sao 2.400/2.400
no treino, 300/300 na validacao e 600/600 no teste. As familias de templates
tambem sao disjuntas entre os tres conjuntos.
