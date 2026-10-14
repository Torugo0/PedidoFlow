"""Consolida metricas dos experimentos em CSV, Markdown e grafico."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = (
    "dataset_split",
    "total_examples",
    "partial_evaluation",
    "valid_json_rate",
    "schema_valid_rate",
    "action_accuracy",
    "argument_field_accuracy",
    "arguments_exact_match_rate",
    "missing_fields_exact_match_rate",
    "exact_match_rate",
    "mean_latency_seconds",
    "peak_vram_gb",
)


def load_runs(
    root: Path, include_smoke: bool, name_contains: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/metrics.json")):
        if not include_smoke and "smoke" in path.parent.name.casefold():
            continue
        if name_contains and name_contains.casefold() not in path.parent.name.casefold():
            continue
        metrics = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "run": path.parent.name,
                **{field: metrics.get(field) for field in FIELDS},
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("run", *FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    selected = (
        "run",
        "dataset_split",
        "total_examples",
        "partial_evaluation",
        "schema_valid_rate",
        "action_accuracy",
        "argument_field_accuracy",
        "exact_match_rate",
        "mean_latency_seconds",
        "peak_vram_gb",
    )
    lines = [
        "# Comparacao de resultados",
        "",
        "| " + " | ".join(selected) + " |",
        "|" + "|".join("---" for _ in selected) + "|",
    ]
    for row in rows:
        values = []
        for field in selected:
            value = row.get(field)
            values.append("—" if value is None else str(value))
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "Gerado automaticamente por `training/compare_results.py`.",
            "Diretorios com `smoke` sao excluidos por padrao.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    metrics = (
        "schema_valid_rate",
        "action_accuracy",
        "argument_field_accuracy",
        "exact_match_rate",
    )
    labels = ("Schema", "Acao", "Campos", "Exact match")
    positions = np.arange(len(metrics))
    width = 0.8 / len(rows)
    figure, axis = plt.subplots(figsize=(10, 5.5))
    for index, row in enumerate(rows):
        values = [float(row.get(metric) or 0) for metric in metrics]
        axis.bar(
            positions + (index - (len(rows) - 1) / 2) * width,
            values,
            width,
            label=row["run"],
        )
    axis.set_ylim(0, 1)
    axis.set_ylabel("Taxa")
    axis.set_title("PedidoFlow: comparacao dos experimentos")
    axis.set_xticks(positions, labels)
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara os relatorios do PedidoFlow.")
    parser.add_argument("--report-root", type=Path, default=Path("results"))
    parser.add_argument("--include-smoke", action="store_true")
    parser.add_argument("--name-contains")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    rows = load_runs(args.report_root, args.include_smoke, args.name_contains)
    if not rows:
        raise SystemExit("Nenhum metrics.json elegivel foi encontrado.")
    output_dir = args.output_dir or args.report_root
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "comparison.csv", rows)
    write_markdown(output_dir / "comparison.md", rows)
    write_chart(output_dir / "comparison.png", rows)
    print(f"Comparacao gerada para {len(rows)} execucao(oes).")


if __name__ == "__main__":
    main()
