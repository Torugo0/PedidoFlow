$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $project ".venv\Scripts\python.exe"

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar Python (codigo $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente .venv nao encontrado. Siga a instalacao do README."
}

Push-Location $project
try {
    Invoke-Python (Join-Path $PSScriptRoot "check_gpu.py") --output "reports\gpu-info.json"
    Invoke-Python "training\generate_dataset.py"

    foreach ($run in @("a", "b", "c")) {
        Invoke-Python "training\train.py" --config "configs\run_$run.json"
        Invoke-Python "training\evaluate.py" `
            --adapter-path "outputs\run_$run\final_adapter" `
            --dataset-file "data\validation.jsonl" `
            --output-dir "reports\validation\run_$run"
    }

    Invoke-Python "training\compare_results.py" --report-root "reports\validation"
    Invoke-Python "training\select_best.py" --report-root "reports\validation"

    $selection = Get-Content -LiteralPath "reports\model-selection.json" -Raw | ConvertFrom-Json
    Invoke-Python "training\evaluate.py" --output-dir "reports\final\base"
    Invoke-Python "training\evaluate.py" `
        --adapter-path $selection.adapter_path `
        --output-dir "reports\final\$($selection.run)"
    Invoke-Python "training\compare_results.py" --report-root "reports\final"

    Write-Host "Experimentos concluidos. Consulte a pasta reports."
}
finally {
    Pop-Location
}
