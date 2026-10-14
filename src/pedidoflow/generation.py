"""Utilitarios de geracao restrita para respostas JSON locais."""

from __future__ import annotations

import json
from typing import Any


def strict_json_loads(text: str) -> Any:
    def reject_constant(value: str):
        raise ValueError(f"Constante JSON nao permitida: {value}")

    return json.loads(text, parse_constant=reject_constant)


def is_complete_json_object(text: str) -> bool:
    """Retorna True somente quando todo o texto ja e um objeto JSON valido."""

    try:
        parsed = strict_json_loads(text.strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    return isinstance(parsed, dict)


def json_stopping_criteria(tokenizer: Any, prompt_length: int):
    """Para uma geracao batch=1 assim que a resposta for um JSON completo."""

    import torch
    from transformers import StoppingCriteria, StoppingCriteriaList

    class _StopOnCompleteJson(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):  # noqa: ANN001, ARG002
            if input_ids.shape[0] != 1:
                return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)
            completion = tokenizer.decode(
                input_ids[0, prompt_length:], skip_special_tokens=True
            )
            complete = is_complete_json_object(completion)
            return torch.tensor([complete], dtype=torch.bool, device=input_ids.device)

    return StoppingCriteriaList([_StopOnCompleteJson()])


__all__ = ["is_complete_json_object", "json_stopping_criteria", "strict_json_loads"]
