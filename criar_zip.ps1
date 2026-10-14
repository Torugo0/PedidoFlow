param(
    [string]$Destino
)

$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path
$parent = Split-Path -Parent $project
if (-not $Destino) {
    $Destino = Join-Path $parent "PedidoFlow-entrega.zip"
}
$zip = [IO.Path]::GetFullPath($Destino)
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$staging = Join-Path $tempRoot ("PedidoFlow-package-" + [guid]::NewGuid().ToString("N"))

function Copy-RelativeFile {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $source = Join-Path $project $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Arquivo versionado nao encontrado: $RelativePath"
    }
    $target = Join-Path $staging $RelativePath
    $targetDirectory = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

function Copy-Adapter {
    param([Parameter(Mandatory = $true)][string]$AdapterPath)

    $source = [IO.Path]::GetFullPath((Join-Path $project $AdapterPath))
    if (-not $source.StartsWith($project + [IO.Path]::DirectorySeparatorChar)) {
        throw "Adapter fora do projeto: $source"
    }
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        return
    }
    $relative = [IO.Path]::GetRelativePath($project, $source)
    $target = Join-Path $staging $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
}

New-Item -ItemType Directory -Path $staging | Out-Null
try {
    $tracked = & git -C $project ls-files
    if ($LASTEXITCODE -ne 0 -or -not $tracked) {
        throw "Nao foi possivel obter a lista de arquivos versionados."
    }
    foreach ($file in $tracked) {
        Copy-RelativeFile $file
    }

    # O GitHub recebe codigo e evidencias leves. O ZIP tambem leva um adapter
    # executavel: primeiro o vencedor final, se existir; senao o demonstrativo.
    $adapter = "models/adapter_demo"
    $selectionFile = Join-Path $project "results\model-selection.json"
    if (Test-Path -LiteralPath $selectionFile) {
        $selection = Get-Content -LiteralPath $selectionFile -Raw | ConvertFrom-Json
        if ($selection.status -eq "final" -and $selection.adapter_path) {
            $adapter = [string]$selection.adapter_path
        }
    }
    Copy-Adapter $adapter

    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zip -Force
    $sizeMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 2)
    Write-Host "ZIP criado: $zip ($sizeMb MB)"
    Write-Host "Nao foram incluidos .venv, .git, caches, banco ou checkpoints intermediarios."
}
finally {
    if (Test-Path -LiteralPath $staging) {
        $resolved = (Resolve-Path -LiteralPath $staging).Path
        $prefix = Join-Path $tempRoot "PedidoFlow-package-"
        if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Diretorio temporario inesperado; limpeza cancelada: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
