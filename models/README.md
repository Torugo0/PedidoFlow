# Modelos locais

O modelo-base `Qwen/Qwen3-1.7B` nao fica nesta pasta. Ele e baixado pelo
Hugging Face e armazenado no cache do computador.

`models/adapter_demo` contem o adapter LoRA entregue com a POC. Ele foi
treinado localmente com 400 exemplos de treino e 100 de validacao, usando a
configuracao B, e permite demonstrar a aplicacao sem refazer o treinamento.

Essa pasta acompanha o GitHub e o ZIP da entrega. Ela contem apenas os ajustes
LoRA, o tokenizer e as configuracoes; o Qwen completo continua sendo baixado
do Hugging Face no primeiro uso.

O piloto A/B/C reduzido e a comparacao com o modelo-base estao documentados em
`results/RESULTADOS.md`. O script de experimento completo permanece como uma
extensao opcional, mas seus checkpoints `models/run_a`, `models/run_b` e
`models/run_c` nao fazem parte da entrega.

A configuracao C venceu apenas o microteste do piloto, avaliado em 10 casos. O
adapter B foi mantido na entrega porque recebeu o treinamento maior de 400/100
exemplos e uma avaliacao separada em 20 casos.
