"""Seleciona o adapter vencedor usando somente metricas de validacao."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pedidoflow.artifacts import sha256_directory, sha256_file  # noqa: E402


def _metricas(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Registra o melhor adapter entre os experimentos finais A/B/C."
    )
    parser.add_argument("--report-root", type=Path, default=Path("reports"))
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    parser.add_argument("--runs", nargs="+", default=["run_a", "run_b", "run_c"])
    parser.add_argument(
        "--selection-file",
        type=Path,
        default=Path("reports/model-selection.json"),
    )
    parser.add_argument("--expected-train-examples", type=int, default=2400)
    parser.add_argument("--expected-validation-examples", type=int, default=300)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Permite selecionar execucoes incompletas e marca o resultado como preliminar.",
    )
    args = parser.parse_args()

    candidatos: list[dict[str, Any]] = []
    encontrados: set[str] = set()
    for run in args.runs:
        metrics_path = args.report_root / run / "metrics.json"
        adapter_path = args.output_root / run / "final_adapter"
        config_path = PROJECT_ROOT / "configs" / f"{run}.json"
        if not metrics_path.exists() or not adapter_path.exists():
            continue
        metricas = _metricas(metrics_path)
        summary_path = args.output_root / run / "training_summary.json"
        if not summary_path.exists():
            continue
        summary = _metricas(summary_path)
        completo = (
            metricas.get("dataset_split") == "validation"
            and metricas.get("total_examples") == args.expected_validation_examples
            and not metricas.get("partial_evaluation", True)
            and summary.get("train_examples") == args.expected_train_examples
            and summary.get("validation_examples")
            == args.expected_validation_examples
            and bool(metricas.get("dataset_sha256"))
            and metricas.get("dataset_sha256")
            == summary.get("validation_dataset_sha256")
            and bool(metricas.get("adapter_sha256"))
            and metricas.get("adapter_sha256") == summary.get("adapter_sha256")
            and metricas.get("adapter_sha256") == sha256_directory(adapter_path)
            and metricas.get("base_model") == summary.get("base_model")
            and config_path.exists()
            and summary.get("config_sha256") == sha256_file(config_path)
        )
        if not completo and not args.allow_partial:
            continue
        encontrados.add(run)
        candidatos.append(
            {
                "run": run,
                "adapter_path": adapter_path.as_posix(),
                "metrics_path": metrics_path.as_posix(),
                "training_summary_path": summary_path.as_posix(),
                "complete_experiment": completo,
                "adapter_sha256": metricas.get("adapter_sha256"),
                "validation_dataset_sha256": metricas.get("dataset_sha256"),
                "train_dataset_sha256": summary.get("train_dataset_sha256"),
                "base_model": summary.get("base_model"),
                "config_sha256": summary.get("config_sha256"),
                "exact_match_rate": float(metricas.get("exact_match_rate") or 0),
                "schema_valid_rate": float(metricas.get("schema_valid_rate") or 0),
                "argument_field_accuracy": float(
                    metricas.get("argument_field_accuracy") or 0
                ),
                "mean_latency_seconds": float(
                    metricas.get("mean_latency_seconds") or float("inf")
                ),
            }
        )

    if not candidatos:
        raise SystemExit(
            "Nenhum run completo de treino/validacao foi encontrado. "
            "Nao use --allow-partial para resultados finais."
        )
    ausentes = sorted(set(args.runs) - encontrados)
    if ausentes and not args.allow_partial:
        raise SystemExit(
            "A selecao final exige todos os runs solicitados completos. "
            f"Ausentes ou incompletos: {', '.join(ausentes)}."
        )
    controlled_experiment = len(
        {
            (
                item["base_model"],
                item["train_dataset_sha256"],
                item["validation_dataset_sha256"],
            )
            for item in candidatos
        }
    ) == 1
    if not controlled_experiment and not args.allow_partial:
        raise SystemExit(
            "Os runs nao compartilham o mesmo modelo base e hashes de treino/validacao."
        )

    vencedor = max(
        candidatos,
        key=lambda item: (
            item["exact_match_rate"],
            item["schema_valid_rate"],
            item["argument_field_accuracy"],
            -item["mean_latency_seconds"],
        ),
    )
    selecao = {
        "status": (
            "final"
            if (
                not ausentes
                and controlled_experiment
                and all(item["complete_experiment"] for item in candidatos)
            )
            else "preliminary"
        ),
        "selection_split": "validation",
        "missing_runs": ausentes,
        "controlled_experiment": controlled_experiment,
        "criterio": (
            "Maior exact_match_rate; desempate por schema_valid_rate, "
            "argument_field_accuracy e menor latencia."
        ),
        **vencedor,
        "candidatos": candidatos,
    }
    destino = args.selection_file
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(selecao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(selecao, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
