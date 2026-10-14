"""Métricas determinísticas para respostas estruturadas do PedidoFlow."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


VALID_ACTIONS = {
    "criar_pedido",
    "consultar_pedido",
    "cancelar_pedido",
    "alterar_entrega",
    "nao_suportada",
}

ALLOWED_ARGUMENTS = {
    "criar_pedido": {"cliente", "itens", "endereco_entrega", "prazo_texto"},
    "consultar_pedido": {"numero_pedido"},
    "cancelar_pedido": {"numero_pedido", "motivo"},
    "alterar_entrega": {"numero_pedido", "novo_endereco", "novo_prazo_texto"},
    "nao_suportada": set(),
}

ALLOWED_MISSING = {
    "criar_pedido": {"cliente", "itens", "endereco_entrega", "prazo_texto"},
    "consultar_pedido": {"numero_pedido"},
    "cancelar_pedido": {"numero_pedido", "motivo"},
    "alterar_entrega": {
        "numero_pedido",
        "novo_endereco",
        "novo_prazo_texto",
        "novo_endereco_ou_novo_prazo_texto",
        "novo_endereco ou novo_prazo_texto",
    },
    "nao_suportada": set(),
}


def _reject_json_constant(value: str):
    raise ValueError(f"Constante JSON nao permitida: {value}")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_items(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "produto",
            "quantidade",
            "unidade",
        }:
            return False
        if not _non_empty_string(item["produto"]):
            return False
        if not _positive_integer(item["quantidade"]):
            return False
        if not _non_empty_string(item["unidade"]):
            return False
    return True


def _arguments_are_valid(action: str, arguments: dict[str, Any]) -> bool:
    if action == "nao_suportada":
        return not arguments
    if "numero_pedido" in arguments and not _positive_integer(
        arguments["numero_pedido"]
    ):
        return False
    string_fields = {
        "cliente",
        "endereco_entrega",
        "prazo_texto",
        "motivo",
        "novo_endereco",
        "novo_prazo_texto",
    }
    if any(
        field in arguments and not _non_empty_string(arguments[field])
        for field in string_fields
    ):
        return False
    if "itens" in arguments and not _valid_items(arguments["itens"]):
        return False
    return True


def _fields_are_coherent(
    action: str, arguments: dict[str, Any], missing: list[str]
) -> bool:
    missing_set = set(missing)
    if set(arguments) & missing_set:
        return False
    if action == "nao_suportada":
        return not arguments and not missing
    required = {
        "criar_pedido": {"cliente", "itens", "endereco_entrega", "prazo_texto"},
        "consultar_pedido": {"numero_pedido"},
        "cancelar_pedido": {"numero_pedido", "motivo"},
        "alterar_entrega": {"numero_pedido"},
    }[action]
    for field in required:
        if (field in arguments) == (field in missing_set):
            return False
    if action == "alterar_entrega":
        has_change = "novo_endereco" in arguments or "novo_prazo_texto" in arguments
        reports_missing_change = bool(
            missing_set
            & {
                "novo_endereco_ou_novo_prazo_texto",
                "novo_endereco ou novo_prazo_texto",
            }
        )
        if has_change == reports_missing_change:
            return False
    return True


def parse_prediction(raw: Any) -> tuple[dict[str, Any] | None, bool]:
    """Retorna o objeto e se a resposta era JSON estrito (sem reparos)."""
    if isinstance(raw, dict):
        return raw, True
    if not isinstance(raw, str):
        return None, False
    try:
        parsed = json.loads(
            raw.strip(),
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, False
    return (parsed, True) if isinstance(parsed, dict) else (None, True)


def is_schema_valid(value: dict[str, Any] | None) -> bool:
    if value is None or set(value) != {"acao", "argumentos", "campos_faltantes"}:
        return False
    action = value.get("acao")
    arguments = value.get("argumentos")
    missing = value.get("campos_faltantes")
    if action not in VALID_ACTIONS or not isinstance(arguments, dict):
        return False
    if not isinstance(missing, list) or not all(_non_empty_string(item) for item in missing):
        return False
    if len(missing) != len(set(missing)):
        return False
    if not set(arguments).issubset(ALLOWED_ARGUMENTS[action]):
        return False
    if not set(missing).issubset(ALLOWED_MISSING[action]):
        return False
    if not _arguments_are_valid(action, arguments):
        return False
    return _fields_are_coherent(action, arguments, missing)


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Transforma estruturas aninhadas em campos comparáveis."""
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten(value[key], child))
        return flattened
    if isinstance(value, list):
        flattened = {}
        for index, item in enumerate(value):
            flattened.update(flatten(item, f"{prefix}[{index}]"))
        if not value:
            flattened[prefix] = []
        return flattened
    return {prefix: value}


def _as_expected(row: dict[str, Any]) -> dict[str, Any]:
    expected = row.get("expected", row.get("output"))
    if not isinstance(expected, dict):
        raise ValueError("Cada linha precisa conter 'expected' ou 'output' como objeto.")
    return expected


def _as_prediction(row: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    if "prediction" in row and row["prediction"] is not None:
        return parse_prediction(row["prediction"])
    return parse_prediction(row.get("raw_prediction", row.get("predicted")))


def compute_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    if not records:
        raise ValueError("Não há previsões para avaliar.")

    valid_json = 0
    valid_schema = 0
    action_correct = 0
    argument_exact = 0
    missing_exact = 0
    exact = 0
    field_correct = 0
    field_total = 0
    per_action: dict[str, Counter[str]] = defaultdict(Counter)

    for row in records:
        expected = _as_expected(row)
        predicted, json_ok = _as_prediction(row)
        action = str(expected.get("acao"))
        stats = per_action[action]
        stats["total"] += 1

        if json_ok and predicted is not None:
            valid_json += 1
            stats["valid_json"] += 1
        if is_schema_valid(predicted):
            valid_schema += 1
            stats["valid_schema"] += 1

        if predicted is not None and predicted.get("acao") == expected.get("acao"):
            action_correct += 1
            stats["action_correct"] += 1

        expected_args = expected.get("argumentos", {})
        predicted_args = predicted.get("argumentos", {}) if predicted else {}
        if predicted is not None and predicted_args == expected_args:
            argument_exact += 1
            stats["arguments_exact"] += 1

        expected_missing = expected.get("campos_faltantes", [])
        predicted_missing = predicted.get("campos_faltantes", []) if predicted else []
        if predicted is not None and predicted_missing == expected_missing:
            missing_exact += 1
            stats["missing_exact"] += 1

        if predicted == expected:
            exact += 1
            stats["exact"] += 1

        expected_fields = flatten(expected_args, "argumentos")
        predicted_fields = flatten(predicted_args, "argumentos")
        keys = set(expected_fields) | set(predicted_fields)
        if not keys:
            field_total += 1
            if predicted is not None and expected_args == predicted_args:
                field_correct += 1
        else:
            field_total += len(keys)
            field_correct += sum(
                key in expected_fields
                and key in predicted_fields
                and expected_fields[key] == predicted_fields[key]
                for key in keys
            )

    total = len(records)

    def rate(value: int, denominator: int = total) -> float:
        return round(value / denominator, 6) if denominator else 0.0

    action_breakdown = {}
    for action in sorted(per_action):
        stats = per_action[action]
        action_total = stats["total"]
        action_breakdown[action] = {
            "total": action_total,
            "action_accuracy": rate(stats["action_correct"], action_total),
            "arguments_exact_match_rate": rate(stats["arguments_exact"], action_total),
            "exact_match_rate": rate(stats["exact"], action_total),
        }

    return {
        "total_examples": total,
        "valid_json_rate": rate(valid_json),
        "schema_valid_rate": rate(valid_schema),
        "action_accuracy": rate(action_correct),
        "argument_field_accuracy": rate(field_correct, field_total),
        "arguments_exact_match_rate": rate(argument_exact),
        "missing_fields_exact_match_rate": rate(missing_exact),
        "exact_match_rate": rate(exact),
        "by_action": action_breakdown,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula métricas de um JSONL de previsões.")
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    metrics = compute_metrics(load_jsonl(args.predictions))
    rendered = json.dumps(metrics, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
