$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$CommandArguments
    )
    & $Command @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha no comando (codigo $LASTEXITCODE): $Command $($CommandArguments -join ' ')"
    }
}

Push-Location $project
try {
    if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
        Invoke-Checked -Command "python" -CommandArguments @("-m", "venv", ".venv")
    }
    $python = Join-Path $project ".venv\Scripts\python.exe"
    Invoke-Checked -Command $python -CommandArguments @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked -Command $python -CommandArguments @("-m", "pip", "install", "-r", "requirements.txt")
    Invoke-Checked -Command $python -CommandArguments @("-m", "pip", "install", "--editable", ".")
    Invoke-Checked -Command $python -CommandArguments @("training\check_gpu.py", "--output", "results\gpu-info.json")
}
finally {
    Pop-Location
}
