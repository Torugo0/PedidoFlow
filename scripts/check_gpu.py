"""Valida que PyTorch está realmente usando a GPU antes dos experimentos."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida a GPU CUDA com uma operacao real.")
    parser.add_argument("--output", type=Path, help="Salva o mesmo resultado em JSON.")
    args = parser.parse_args()
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("PyTorch não está instalado. Instale as dependências do projeto.") from exc

    if not torch.cuda.is_available():
        raise SystemExit(
            "ERRO: CUDA indisponível no PyTorch. Confira driver NVIDIA e a versão CUDA do PyTorch."
        )

    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    torch.cuda.reset_peak_memory_stats(device)

    # Uma multiplicação pequena confirma execução de um kernel, não apenas detecção do driver.
    left = torch.randn((2048, 2048), device=device)
    right = torch.randn((2048, 2048), device=device)
    torch.cuda.synchronize(device)
    started = time.perf_counter()
    product = left @ right
    torch.cuda.synchronize(device)
    elapsed_ms = (time.perf_counter() - started) * 1000
    checksum = float(product[0, 0].item())

    try:
        driver_nvidia = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            text=True,
            timeout=10,
        ).splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        driver_nvidia = "nao identificado"

    info = {
        "status": "GPU CUDA funcionando",
        "sistema": platform.platform(),
        "python": sys.version.split()[0],
        "pytorch": torch.__version__,
        "cuda_pytorch": torch.version.cuda,
        "driver_nvidia": driver_nvidia,
        "gpu": properties.name,
        "compute_capability": f"{properties.major}.{properties.minor}",
        "vram_total_gb": round(properties.total_memory / (1024**3), 2),
        "teste_matriz_ms": round(elapsed_ms, 2),
        "pico_vram_teste_mb": round(torch.cuda.max_memory_allocated(device) / (1024**2), 2),
        "checksum": round(checksum, 4),
    }
    rendered = json.dumps(info, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
