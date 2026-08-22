# Sobe o DevCockpit em desenvolvimento (NFR-070: um comando).
#
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host 'Criando ambiente virtual...' -ForegroundColor Cyan
    python -m venv .venv
    & $python -m pip install --upgrade pip
    & $python -m pip install -e '.[dev]'
}

if (-not (Test-Path '.env')) {
    Write-Host 'Criando .env a partir de .env.example...' -ForegroundColor Cyan
    Copy-Item '.env.example' '.env'
}

if (-not (Test-Path 'configs\roots.yml')) {
    Write-Host 'AVISO: configs\roots.yml nao existe.' -ForegroundColor Yellow
    Write-Host 'Copie configs\roots.example.yml e ajuste os diretorios permitidos.' -ForegroundColor Yellow
    Write-Host 'Sem isso, nenhum projeto pode ser cadastrado (defesa D4).' -ForegroundColor Yellow
}

Write-Host 'Aplicando migracoes...' -ForegroundColor Cyan
& $python -m alembic upgrade head

Write-Host 'Subindo em http://127.0.0.1:8765' -ForegroundColor Green
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
