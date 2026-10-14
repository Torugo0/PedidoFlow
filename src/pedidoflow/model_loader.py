"""Carregamento unico do modelo implantado e avaliado, sempre em CUDA 4-bit."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_local_model(
    base_model: str,
    adapter_path: str | Path | None = None,
) -> tuple[Any, Any, Any]:
    """Retorna tokenizer, modelo e dtype com a mesma configuracao da avaliacao."""

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA não disponível")

    adapter = Path(adapter_path) if adapter_path is not None else None
    tokenizer_source = str(adapter) if adapter is not None else base_model
    try:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, use_fast=True)
    except (OSError, ValueError):
        tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=quantization,
        device_map={"": 0},
        dtype=compute_dtype,
        trust_remote_code=False,
    )
    if adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter))
    model.eval()
    return tokenizer, model, compute_dtype


__all__ = ["load_local_model"]
