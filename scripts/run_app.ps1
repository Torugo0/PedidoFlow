param(
    [string]$AdapterPath
)

$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $project ".venv\Scripts\python.exe"
$previousAdapter = $env:PEDIDOFLOW_ADAPTER
$adapterWasChanged = $false

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente .venv nao encontrado. Siga a instalacao do README."
}

Push-Location $project
try {
    if ($AdapterPath) {
        $resolvedAdapter = (Resolve-Path -LiteralPath $AdapterPath).Path
        $env:PEDIDOFLOW_ADAPTER = $resolvedAdapter
        $adapterWasChanged = $true
        Write-Host "Usando adapter informado explicitamente: $resolvedAdapter"
    }
    & $python "app.py"
    if ($LASTEXITCODE -ne 0) {
        throw "A aplicacao terminou com erro (codigo $LASTEXITCODE)."
    }
}
finally {
    if ($adapterWasChanged) {
        if ($null -eq $previousAdapter) {
            Remove-Item Env:PEDIDOFLOW_ADAPTER -ErrorAction SilentlyContinue
        }
        else {
            $env:PEDIDOFLOW_ADAPTER = $previousAdapter
        }
    }
    Pop-Location
}
