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
    Invoke-Python (Join-Path $PSScriptRoot "check_gpu.py")
    foreach ($run in @("a", "b", "c")) {
        Invoke-Python "training\train.py" `
            --config "configs\run_$run.json" `
            --output-dir "outputs\pilot_run_$run" `
            --max-train-samples 32 `
            --max-eval-samples 16
        Invoke-Python "training\evaluate.py" `
            --adapter-path "outputs\pilot_run_$run\final_adapter" `
            --dataset-file "data\validation.jsonl" `
            --output-dir "reports\pilot\run_$run" `
            --limit 10
    }
    Invoke-Python "training\compare_results.py" --report-root "reports\pilot"
    Write-Host "Piloto A/B/C concluido. Nao use estes numeros como resultado final."
}
finally {
    Pop-Location
}
