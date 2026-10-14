"""Fine-tuning supervisionado do Qwen3-1.7B com QLoRA 4-bit."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pedidoflow.prompts import SYSTEM_PROMPT  # noqa: E402
from pedidoflow.artifacts import sha256_directory, sha256_file  # noqa: E402


def require_cuda(torch_module: Any) -> None:
    if not torch_module.cuda.is_available():
        raise SystemExit(
            "CUDA não está disponível. O treinamento foi interrompido para impedir uso acidental da CPU."
        )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows:
        raise ValueError(f"Dataset vazio: {path}")
    return rows


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def apply_chat_template(
    tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool
) -> str:
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
        )


def build_prompt_completion(tokenizer: Any, row: dict[str, Any]) -> tuple[str, str]:
    prompt_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": row["input"]},
    ]
    target = json.dumps(row["output"], ensure_ascii=False, separators=(",", ":"))
    complete_messages = prompt_messages + [{"role": "assistant", "content": target}]
    prompt = apply_chat_template(tokenizer, prompt_messages, add_generation_prompt=True)
    complete = apply_chat_template(tokenizer, complete_messages, add_generation_prompt=False)
    if not complete.startswith(prompt):
        raise RuntimeError("O chat template não produziu um prefixo estável para prompt/completion.")
    return prompt, complete[len(prompt) :]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Treina o classificador/extrator do PedidoFlow.")
    parser.add_argument("--config", type=Path, required=True, help="Arquivo JSON do experimento.")
    parser.add_argument("--output-dir", type=Path, help="Sobrescreve output_dir da configuração.")
    parser.add_argument(
        "--max-train-samples", type=int, help="Limite opcional para smoke test."
    )
    parser.add_argument(
        "--max-eval-samples", type=int, help="Limite opcional para smoke test."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_json(args.config)

    # Imports tardios permitem usar --help sem que todo o ambiente de ML esteja instalado.
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    from trl import SFTConfig, SFTTrainer

    require_cuda(torch)
    seed = int(config.get("seed", 42))
    random.seed(seed)
    set_seed(seed)

    base_model = config.get("base_model", "Qwen/Qwen3-1.7B")
    output_dir = args.output_dir or Path(config.get("output_dir", "outputs/experiment"))
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=quantization_config,
        device_map={"": 0},
        dtype=compute_dtype,
        trust_remote_code=False,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=bool(config.get("gradient_checkpointing", True))
    )

    paths = config.get("data", {})
    train_rows = load_jsonl(Path(paths.get("train", "data/train.jsonl")))
    validation_rows = load_jsonl(Path(paths.get("validation", "data/validation.jsonl")))
    if args.max_train_samples:
        train_rows = train_rows[: args.max_train_samples]
    if args.max_eval_samples:
        validation_rows = validation_rows[: args.max_eval_samples]
    # O JSON de argumentos tem formatos diferentes por ação. Formatá-lo antes de
    # criar o Dataset evita que o Apache Arrow acrescente chaves nulas à estrutura.
    train_pairs = [build_prompt_completion(tokenizer, row) for row in train_rows]
    validation_pairs = [build_prompt_completion(tokenizer, row) for row in validation_rows]
    train_dataset = Dataset.from_dict(
        {
            "prompt": [pair[0] for pair in train_pairs],
            "completion": [pair[1] for pair in train_pairs],
        }
    )
    validation_dataset = Dataset.from_dict(
        {
            "prompt": [pair[0] for pair in validation_pairs],
            "completion": [pair[1] for pair in validation_pairs],
        }
    )

    lora = config.get("lora", {})
    lora_config = LoraConfig(
        r=int(lora.get("r", 8)),
        lora_alpha=int(lora.get("alpha", 16)),
        lora_dropout=float(lora.get("dropout", 0.05)),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=lora.get("target_modules", "all-linear"),
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training = config.get("training", {})
    atualizacoes_por_epoca = math.ceil(
        len(train_rows)
        / int(training.get("batch_size", 1))
        / int(training.get("gradient_accumulation_steps", 8))
    )
    total_atualizacoes = max(
        1,
        math.ceil(atualizacoes_por_epoca * float(training.get("epochs", 2))),
    )
    warmup_steps = max(
        0, int(total_atualizacoes * float(training.get("warmup_ratio", 0.03)))
    )
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=float(training.get("epochs", 2)),
        learning_rate=float(training.get("learning_rate", 1e-4)),
        per_device_train_batch_size=int(training.get("batch_size", 1)),
        per_device_eval_batch_size=int(training.get("eval_batch_size", 1)),
        gradient_accumulation_steps=int(training.get("gradient_accumulation_steps", 8)),
        max_length=int(training.get("max_length", 512)),
        warmup_steps=warmup_steps,
        weight_decay=float(training.get("weight_decay", 0.01)),
        lr_scheduler_type=training.get("lr_scheduler_type", "cosine"),
        optim=training.get("optim", "paged_adamw_8bit"),
        logging_steps=int(training.get("logging_steps", 10)),
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=int(training.get("save_total_limit", 2)),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        gradient_checkpointing=bool(config.get("gradient_checkpointing", True)),
        completion_only_loss=True,
        report_to="none",
        seed=seed,
        data_seed=seed,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        processing_class=tokenizer,
    )

    torch.cuda.reset_peak_memory_stats()
    train_result = trainer.train(resume_from_checkpoint=training.get("resume_from_checkpoint"))
    final_dir = output_dir / "final_adapter"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    summary = {
        "experiment": config.get("name", args.config.stem),
        "base_model": base_model,
        "adapter_path": portable_path(final_dir),
        "config_path": portable_path(args.config),
        "config_sha256": sha256_file(args.config),
        "train_dataset_sha256": sha256_file(
            Path(paths.get("train", "data/train.jsonl"))
        ),
        "validation_dataset_sha256": sha256_file(
            Path(paths.get("validation", "data/validation.jsonl"))
        ),
        "adapter_sha256": sha256_directory(final_dir),
        "gpu": torch.cuda.get_device_name(0),
        "cuda_runtime": torch.version.cuda,
        "compute_dtype": str(compute_dtype).replace("torch.", ""),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / (1024**3), 3),
        "train_examples": len(train_rows),
        "validation_examples": len(validation_rows),
        "train_metrics": train_result.metrics,
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    evidence_dir = PROJECT_ROOT / "reports" / "training"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{output_dir.name}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # Evita fragmentação excessiva em GPUs com pouca VRAM. O usuário ainda pode sobrescrever.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    main()
