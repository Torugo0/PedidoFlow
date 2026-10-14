$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path
$python = Join-Path $project ".venv\Scripts\python.exe"

function Invoke-Python {
    param([Parameter(Mandatory = $true)][string[]]$PythonArguments)
    & $python @PythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar Python (codigo $LASTEXITCODE): $($PythonArguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente .venv nao encontrado. Siga a instalacao do README."
}

Push-Location $project
try {
    Invoke-Python -PythonArguments @("training\check_gpu.py", "--output", "results\gpu-info.json")
    Invoke-Python -PythonArguments @("training\generate_dataset.py")

    foreach ($run in @("a", "b", "c")) {
        Invoke-Python -PythonArguments @(
            "training\train.py",
            "--config", "training\configs\run_$run.json"
        )
        Invoke-Python -PythonArguments @(
            "training\evaluate.py",
            "--adapter-path", "models\run_$run\final_adapter",
            "--dataset-file", "data\validation.jsonl",
            "--output-dir", "results\validation\run_$run"
        )
    }

    Invoke-Python -PythonArguments @("training\compare_results.py", "--report-root", "results\validation")
    Invoke-Python -PythonArguments @("training\select_best.py", "--report-root", "results\validation")

    $selection = Get-Content -LiteralPath "results\model-selection.json" -Raw | ConvertFrom-Json
    Invoke-Python -PythonArguments @("training\evaluate.py", "--output-dir", "results\final\base")
    Invoke-Python -PythonArguments @(
        "training\evaluate.py",
        "--adapter-path", $selection.adapter_path,
        "--output-dir", "results\final\$($selection.run)"
    )
    Invoke-Python -PythonArguments @("training\compare_results.py", "--report-root", "results\final")

    Write-Host "Experimentos concluidos. Consulte a pasta results."
}
finally {
    Pop-Location
}
