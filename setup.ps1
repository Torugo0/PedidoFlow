$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha no comando (codigo $LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

Push-Location $project
try {
    if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
        Invoke-Checked "python" -m venv .venv
    }
    $python = Join-Path $project ".venv\Scripts\python.exe"
    Invoke-Checked $python -m pip install --upgrade pip
    Invoke-Checked $python -m pip install -r requirements.txt
    Invoke-Checked $python -m pip install -e .
    Invoke-Checked $python training\check_gpu.py --output results\gpu-info.json
}
finally {
    Pop-Location
}
