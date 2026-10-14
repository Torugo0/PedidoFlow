"""Executa inferencia em um split e calcula metricas exatas."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pedidoflow.generation import json_stopping_criteria  # noqa: E402
from pedidoflow.artifacts import sha256_directory, sha256_file  # noqa: E402
from pedidoflow.model_loader import load_local_model  # noqa: E402
from pedidoflow.prompts import SYSTEM_PROMPT  # noqa: E402

try:
    from training.metrics import compute_metrics, parse_prediction
except ModuleNotFoundError:
    from metrics import compute_metrics, parse_prediction

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def prompt_for(tokenizer: Any, user_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Avalia o Qwen base ou um adapter PedidoFlow.")
    parser.add_argument("--base-model", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--adapter-path", type=Path, help="Adapter LoRA; omita para avaliar o modelo base.")
    parser.add_argument(
        "--dataset-file",
        "--test-file",
        dest="dataset_file",
        type=Path,
        default=Path("data/test.jsonl"),
        help="JSONL de validacao ou teste; --test-file e mantido como alias.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/evaluation"))
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, help="Limita exemplos para teste rápido.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import torch
    if not torch.cuda.is_available():
        raise SystemExit(
            "CUDA não está disponível. A avaliação foi interrompida para cumprir o requisito de GPU."
        )

    tokenizer, model, compute_dtype = load_local_model(
        args.base_model, args.adapter_path
    )

    all_dataset_rows = load_jsonl(args.dataset_file)
    dataset_splits = {str(row.get("split", "unknown")) for row in all_dataset_rows}
    dataset_split = next(iter(dataset_splits)) if len(dataset_splits) == 1 else "mixed"
    test_rows = all_dataset_rows
    if args.limit:
        test_rows = test_rows[: args.limit]
    if not test_rows:
        raise SystemExit("O conjunto de teste está vazio.")

    predictions: list[dict[str, Any]] = []
    latencies: list[float] = []
    torch.cuda.reset_peak_memory_stats()

    for index, row in enumerate(test_rows, start=1):
        prompt = prompt_for(tokenizer, row["input"])
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda:0")
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                stopping_criteria=json_stopping_criteria(
                    tokenizer, inputs["input_ids"].shape[1]
                ),
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        torch.cuda.synchronize()
        latency = time.perf_counter() - started
        latencies.append(latency)
        completion_tokens = generated[0, inputs["input_ids"].shape[1] :]
        raw = tokenizer.decode(completion_tokens, skip_special_tokens=True).strip()
        parsed, _ = parse_prediction(raw)
        predictions.append(
            {
                "id": row.get("id", f"test-{index:05d}"),
                "family": row.get("family"),
                "input": row["input"],
                "expected": row["output"],
                "raw_prediction": raw,
                "prediction": parsed,
                "latency_seconds": round(latency, 6),
            }
        )
        if index % 25 == 0 or index == len(test_rows):
            print(f"Avaliados {index}/{len(test_rows)} exemplos")

    metrics = compute_metrics(predictions)
    metrics.update(
        {
            "base_model": args.base_model,
            "adapter_path": portable_path(args.adapter_path) if args.adapter_path else None,
            "adapter_sha256": (
                sha256_directory(args.adapter_path) if args.adapter_path else None
            ),
            "dataset_path": portable_path(args.dataset_file),
            "dataset_sha256": sha256_file(args.dataset_file),
            "dataset_split": dataset_split,
            "dataset_total_examples": len(all_dataset_rows),
            "evaluation_limit": args.limit,
            "partial_evaluation": len(test_rows) != len(all_dataset_rows),
            "gpu": torch.cuda.get_device_name(0),
            "inference_quantization": "4-bit NF4 double quantization",
            "inference_compute_dtype": str(compute_dtype).replace("torch.", ""),
            "mean_latency_seconds": round(sum(latencies) / len(latencies), 6),
            "peak_vram_gb": round(torch.cuda.max_memory_allocated() / (1024**3), 3),
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "predictions.jsonl", predictions)
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
