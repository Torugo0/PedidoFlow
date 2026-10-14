"""Gera um dataset sintético e reproduzível para o PedidoFlow.

O split é feito por famílias de templates: uma forma de frase usada no treino
nunca aparece na validação ou no teste. Isso reduz vazamento e torna a
avaliação mais próxima de mensagens inéditas.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ACTIONS = (
    "criar_pedido",
    "consultar_pedido",
    "cancelar_pedido",
    "alterar_entrega",
    "nao_suportada",
)

ACTION_WEIGHTS = {
    "criar_pedido": 0.30,
    "consultar_pedido": 0.18,
    "cancelar_pedido": 0.18,
    "alterar_entrega": 0.22,
    "nao_suportada": 0.12,
}

CLIENTES = [
    "Mercado Central",
    "Padaria Primavera",
    "Cafeteria Horizonte",
    "Empório do Bairro",
    "Hotel Bela Vista",
    "Restaurante Sabor Caseiro",
    "Escola Caminhos",
    "Clínica Vida",
    "Condomínio das Flores",
    "Loja Ponto Certo",
]

PRODUTOS = [
    ("café", "caixa"),
    ("açúcar", "pacote"),
    ("arroz", "fardo"),
    ("leite", "caixa"),
    ("chá", "caixa"),
    ("farinha", "pacote"),
    ("óleo", "caixa"),
    ("água mineral", "fardo"),
    ("papel toalha", "pacote"),
    ("detergente", "caixa"),
]

NUMEROS_POR_EXTENSO = {
    1: "uma",
    2: "duas",
    3: "três",
    4: "quatro",
    5: "cinco",
    6: "seis",
    7: "sete",
    8: "oito",
    9: "nove",
    10: "dez",
    11: "onze",
    12: "doze",
}

ABREVIACOES_UNIDADE = {
    "caixa": "cx",
    "pacote": "pct",
    "fardo": "fardo",
    "unidade": "un",
}

ENDERECOS = [
    "Avenida Paulista, 1000, conjunto 12, São Paulo - SP",
    "Rua das Flores, 120, Curitiba - PR",
    "Avenida Brasil, 500, Rio de Janeiro - RJ",
    "Rua da Bahia, 730, sala 4, Belo Horizonte - MG",
    "Rua XV de Novembro, 88, Campinas - SP",
    "Avenida Ipiranga, 245, Porto Alegre - RS",
    "Rua do Comércio, 41, Salvador - BA",
    "Avenida Boa Viagem, 1500, Recife - PE",
    "Rua Goiás, 312, Goiânia - GO",
    "Avenida das Nações, 900, Brasília - DF",
]

PRAZOS = [
    "amanhã",
    "sexta",
    "sexta-feira",
    "na próxima terça-feira",
    "na próxima segunda-feira",
    "dia 22 de outubro",
    "daqui a três dias",
    "no próximo sábado",
    "quarta-feira",
]

MOTIVOS = [
    "foi cadastrado em duplicidade",
    "o cliente desistiu da compra",
    "os itens foram incluídos incorretamente",
    "o endereço informado estava errado",
    "não será mais necessário",
    "o prazo de entrega não atende",
]

UNSUPPORTED = {
    "train": [
        ("unsupported_train_weather", "Vai chover amanhã em São Paulo?"),
        ("unsupported_train_recipe", "Me ensine uma receita de bolo de chocolate."),
        ("unsupported_train_general", "Quem descobriu o Brasil?"),
        ("unsupported_train_joke", "Conte uma piada curta."),
    ],
    "validation": [
        ("unsupported_validation_translation", "Traduza bom dia para inglês."),
        ("unsupported_validation_music", "Recomende uma música para estudar."),
    ],
    "test": [
        ("unsupported_test_definition", "O que significa inteligência artificial?"),
        ("unsupported_test_travel", "Monte um roteiro de viagem para o litoral."),
        ("unsupported_test_code", "Escreva um programa que calcule juros."),
    ],
}

CONTEXT_PREFIXES = [
    "Olá,",
    "Bom dia,",
    "Boa tarde,",
    "Por favor,",
    "Quando puder,",
    "Preciso de ajuda:",
    "Tenho uma solicitação:",
    "No sistema,",
    "Para mim,",
    "Por gentileza,",
    "Pode me ajudar?",
    "Uma dúvida:",
    "Uma solicitação rápida:",
    "Queria pedir o seguinte:",
    "Você poderia verificar?",
    "Se for possível,",
    "Tenho este pedido:",
    "Preciso que veja isto:",
    "Gostaria de solicitar:",
    "Pode verificar para mim?",
]

CONTEXT_SUFFIXES = [
    "Pode verificar?",
    "Aguardo o retorno.",
    "Obrigado.",
    "Por gentileza.",
    "Isso é possível?",
    "Pode cuidar disso?",
    "Fico no aguardo.",
    "Consegue me ajudar?",
    "Pode conferir?",
    "Preciso de uma confirmação.",
    "Avise quando concluir.",
    "Agradeço desde já.",
    "Pode dar uma olhada?",
    "Consegue resolver?",
    "Tudo bem?",
    "Certo?",
    "Pode fazer isso?",
    "Me ajude, por favor.",
    "Pode analisar?",
    "Aguardo sua confirmação.",
]


def result(acao: str, argumentos: dict[str, Any], faltantes: list[str] | None = None) -> dict[str, Any]:
    return {
        "acao": acao,
        "argumentos": argumentos,
        "campos_faltantes": faltantes or [],
    }


def pluralize(unit: str, quantity: int) -> str:
    if quantity == 1:
        return unit
    forms = {"caixa": "caixas", "pacote": "pacotes", "fardo": "fardos", "unidade": "unidades"}
    return forms.get(unit, f"{unit}s")


def make_items(rng: random.Random, minimum: int = 1, maximum: int = 3) -> tuple[list[dict[str, Any]], str]:
    selected = rng.sample(PRODUTOS, k=rng.randint(minimum, maximum))
    items: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for product, unit in selected:
        quantity = rng.randint(1, 12)
        items.append({"produto": product, "quantidade": quantity, "unidade": unit})
        quantity_text = NUMEROS_POR_EXTENSO[quantity] if rng.random() < 0.25 else str(quantity)
        unit_text = (
            ABREVIACOES_UNIDADE[unit]
            if rng.random() < 0.15
            else pluralize(unit, quantity)
        )
        text_parts.append(f"{quantity_text} {unit_text} de {product}")
    if len(text_parts) == 1:
        item_text = text_parts[0]
    else:
        item_text = ", ".join(text_parts[:-1]) + " e " + text_parts[-1]
    return items, item_text


def create_complete(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    client = rng.choice(CLIENTES)
    address = rng.choice(ENDERECOS)
    deadline = rng.choice(PRAZOS)
    items, items_text = make_items(rng)
    text = template.format(cliente=client, itens=items_text, endereco=address, prazo=deadline)
    return text, result(
        "criar_pedido",
        {
            "cliente": client,
            "itens": items,
            "endereco_entrega": address,
            "prazo_texto": deadline,
        },
    )


def create_missing_address(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    client = rng.choice(CLIENTES)
    deadline = rng.choice(PRAZOS)
    items, items_text = make_items(rng)
    text = template.format(cliente=client, itens=items_text, prazo=deadline)
    return text, result(
        "criar_pedido",
        {"cliente": client, "itens": items, "prazo_texto": deadline},
        ["endereco_entrega"],
    )


def create_missing_deadline(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    client = rng.choice(CLIENTES)
    address = rng.choice(ENDERECOS)
    items, items_text = make_items(rng)
    text = template.format(cliente=client, itens=items_text, endereco=address)
    return text, result(
        "criar_pedido",
        {"cliente": client, "itens": items, "endereco_entrega": address},
        ["prazo_texto"],
    )


def create_missing_client(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    address = rng.choice(ENDERECOS)
    deadline = rng.choice(PRAZOS)
    items, items_text = make_items(rng)
    text = template.format(itens=items_text, endereco=address, prazo=deadline)
    return text, result(
        "criar_pedido",
        {"itens": items, "endereco_entrega": address, "prazo_texto": deadline},
        ["cliente"],
    )


def query_complete(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    return template.format(numero=order), result("consultar_pedido", {"numero_pedido": order})


def query_missing(_: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    return template, result("consultar_pedido", {}, ["numero_pedido"])


def cancel_complete(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    reason = rng.choice(MOTIVOS)
    return template.format(numero=order, motivo=reason), result(
        "cancelar_pedido", {"numero_pedido": order, "motivo": reason}
    )


def cancel_missing_reason(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    return template.format(numero=order), result(
        "cancelar_pedido", {"numero_pedido": order}, ["motivo"]
    )


def cancel_missing_order(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    reason = rng.choice(MOTIVOS)
    return template.format(motivo=reason), result(
        "cancelar_pedido", {"motivo": reason}, ["numero_pedido"]
    )


def change_both(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    address = rng.choice(ENDERECOS)
    deadline = rng.choice(PRAZOS)
    return template.format(numero=order, endereco=address, prazo=deadline), result(
        "alterar_entrega",
        {"numero_pedido": order, "novo_endereco": address, "novo_prazo_texto": deadline},
    )


def change_address(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    address = rng.choice(ENDERECOS)
    return template.format(numero=order, endereco=address), result(
        "alterar_entrega", {"numero_pedido": order, "novo_endereco": address}
    )


def change_deadline(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    order = rng.randint(1000, 9999)
    deadline = rng.choice(PRAZOS)
    return template.format(numero=order, prazo=deadline), result(
        "alterar_entrega", {"numero_pedido": order, "novo_prazo_texto": deadline}
    )


def change_missing_order(rng: random.Random, template: str) -> tuple[str, dict[str, Any]]:
    deadline = rng.choice(PRAZOS)
    return template.format(prazo=deadline), result(
        "alterar_entrega", {"novo_prazo_texto": deadline}, ["numero_pedido"]
    )


Template = tuple[str, Callable[[random.Random, str], tuple[str, dict[str, Any]]], str]


TEMPLATES: dict[str, dict[str, list[Template]]] = {
    "train": {
        "criar_pedido": [
            ("create_train_direct", create_complete, "Crie um pedido para {cliente} com {itens}, entrega em {endereco} até {prazo}."),
            ("create_train_polite", create_complete, "Por favor, cadastre {itens} para {cliente}. Enviar para {endereco} {prazo}."),
            ("create_train_colloquial", create_complete, "Manda {itens} pro {cliente}, no endereço {endereco}, para {prazo}."),
            ("create_train_no_address", create_missing_address, "Registre para {cliente} um pedido de {itens} com prazo {prazo}."),
            ("create_train_no_deadline", create_missing_deadline, "Quero {itens} para {cliente}, entregues em {endereco}."),
            ("create_train_no_client", create_missing_client, "Separe {itens} e entregue em {endereco} até {prazo}."),
        ],
        "consultar_pedido": [
            ("query_train_status", query_complete, "Qual é o status do pedido {numero}?"),
            ("query_train_where", query_complete, "Onde está o meu pedido número {numero}?"),
            ("query_train_details", query_complete, "Mostre os detalhes do pedido {numero}."),
            ("query_train_missing", query_missing, "Gostaria de consultar meu pedido."),
        ],
        "cancelar_pedido": [
            ("cancel_train_direct", cancel_complete, "Cancele o pedido {numero} porque {motivo}."),
            ("cancel_train_polite", cancel_complete, "Por favor, solicite o cancelamento do pedido {numero}; {motivo}."),
            ("cancel_train_no_reason", cancel_missing_reason, "Quero cancelar o pedido {numero}."),
            ("cancel_train_no_order", cancel_missing_order, "Cancele meu pedido, pois {motivo}."),
        ],
        "alterar_entrega": [
            ("change_train_both", change_both, "No pedido {numero}, mude o endereço para {endereco} e o prazo para {prazo}."),
            ("change_train_address", change_address, "Altere a entrega do pedido {numero} para {endereco}."),
            ("change_train_deadline", change_deadline, "Passe a entrega do pedido {numero} para {prazo}."),
            ("change_train_no_order", change_missing_order, "Quero mudar a entrega para {prazo}."),
        ],
    },
    "validation": {
        "criar_pedido": [
            ("create_validation_request", create_complete, "Faça o pedido de {itens} em nome de {cliente}; destino {endereco}; prazo {prazo}."),
            ("create_validation_no_address", create_missing_address, "O {cliente} precisa de {itens} para {prazo}."),
            ("create_validation_no_deadline", create_missing_deadline, "Inclua {itens} para o cliente {cliente}, em {endereco}."),
        ],
        "consultar_pedido": [
            ("query_validation_follow", query_complete, "Acompanhe para mim o pedido de número {numero}."),
            ("query_validation_missing", query_missing, "Preciso ver como está uma encomenda minha."),
        ],
        "cancelar_pedido": [
            ("cancel_validation_request", cancel_complete, "Abra o cancelamento de {numero}, já que {motivo}."),
            ("cancel_validation_no_reason", cancel_missing_reason, "Pode anular o pedido {numero}?"),
        ],
        "alterar_entrega": [
            ("change_validation_both", change_both, "Atualize o pedido {numero}: endereço {endereco} e data {prazo}."),
            ("change_validation_address", change_address, "O novo local de entrega de {numero} é {endereco}."),
            ("change_validation_deadline", change_deadline, "Reagende o pedido {numero} para {prazo}."),
        ],
    },
    "test": {
        "criar_pedido": [
            ("create_test_imperative", create_complete, "Lance {itens} para {cliente}, com entrega no endereço {endereco} em {prazo}."),
            ("create_test_natural", create_complete, "O {cliente} quer receber {itens} em {endereco} até {prazo}."),
            ("create_test_no_client", create_missing_client, "Providencie {itens}, destino {endereco}, para {prazo}."),
            ("create_test_no_deadline", create_missing_deadline, "Anote {itens} para {cliente} no endereço {endereco}."),
        ],
        "consultar_pedido": [
            ("query_test_progress", query_complete, "Consulte o andamento da encomenda {numero}."),
            ("query_test_missing", query_missing, "Você consegue localizar meu pedido?"),
        ],
        "cancelar_pedido": [
            ("cancel_test_stop", cancel_complete, "Interrompa o pedido {numero}: {motivo}."),
            ("cancel_test_no_order", cancel_missing_order, "Preciso cancelar uma compra porque {motivo}."),
            ("cancel_test_no_reason", cancel_missing_reason, "Desfaça a compra de número {numero}."),
        ],
        "alterar_entrega": [
            ("change_test_both", change_both, "Corrija a entrega de {numero} para {endereco} e deixe para {prazo}."),
            ("change_test_address", change_address, "Redirecione a encomenda {numero} ao endereço {endereco}."),
            ("change_test_deadline", change_deadline, "A nova data desejada para o pedido {numero} é {prazo}."),
            ("change_test_no_order", change_missing_order, "A entrega deve ficar para {prazo}, mas não lembro o número."),
        ],
    },
}


def action_plan(size: int, rng: random.Random) -> list[str]:
    counts = {action: int(size * weight) for action, weight in ACTION_WEIGHTS.items()}
    remainder = size - sum(counts.values())
    for action in ACTIONS[:remainder]:
        counts[action] += 1
    plan = [action for action in ACTIONS for _ in range(counts[action])]
    rng.shuffle(plan)
    return plan


def add_neutral_context(text: str, rng: random.Random) -> str:
    """Cria uma variacao natural sem acrescentar entidades ao pedido."""

    prefix = rng.choice(CONTEXT_PREFIXES)
    suffix = rng.choice(CONTEXT_SUFFIXES)
    return f"{prefix} {text} {suffix}"


def generate_split(split: str, size: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    seen_inputs: set[str] = set()
    for index, action in enumerate(action_plan(size, rng), start=1):
        for attempt in range(10_000):
            if action == "nao_suportada":
                family, text = rng.choice(UNSUPPORTED[split])
                output = result(action, {})
            else:
                family, builder, template = rng.choice(TEMPLATES[split][action])
                text, output = builder(rng, template)
            if attempt > 0:
                text = add_neutral_context(text, rng)
            if text not in seen_inputs:
                seen_inputs.add(text)
                break
        else:
            raise RuntimeError(
                f"Nao foi possivel gerar entrada unica para {split}/{action}."
            )
        rows.append(
            {
                "id": f"{split}-{index:05d}",
                "split": split,
                "family": family,
                "input": text,
                "output": output,
            }
        )
    return rows


def ensure_unique_inputs(splits: dict[str, list[dict[str, Any]]]) -> None:
    for name, rows in splits.items():
        inputs = [row["input"] for row in rows]
        if len(inputs) != len(set(inputs)):
            raise RuntimeError(f"O split {name} contem entradas duplicadas.")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def ensure_disjoint_families(splits: dict[str, list[dict[str, Any]]]) -> None:
    families = {name: {row["family"] for row in rows} for name, rows in splits.items()}
    names = list(families)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = families[left] & families[right]
            if overlap:
                raise RuntimeError(f"Famílias compartilhadas por {left} e {right}: {sorted(overlap)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera os dados sintéticos do PedidoFlow.")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--train-size", type=int, default=2400)
    parser.add_argument("--validation-size", type=int, default=300)
    parser.add_argument("--test-size", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sizes = {
        "train": args.train_size,
        "validation": args.validation_size,
        "test": args.test_size,
    }
    if any(size <= 0 for size in sizes.values()):
        raise SystemExit("Todos os tamanhos precisam ser maiores que zero.")

    splits = {
        name: generate_split(name, size, args.seed + offset)
        for offset, (name, size) in enumerate(sizes.items())
    }
    ensure_disjoint_families(splits)
    ensure_unique_inputs(splits)

    for name, rows in splits.items():
        write_jsonl(args.output_dir / f"{name}.jsonl", rows)
        counts = Counter(row["output"]["acao"] for row in rows)
        unique = len({row["input"] for row in rows})
        print(f"{name}: {len(rows)} exemplos ({unique} unicos) | {dict(counts)}")
    print(f"Dataset salvo em: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
