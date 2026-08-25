# Sobe o DevCockpit em desenvolvimento (NFR-070: um comando).
#
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Port 8766

[CmdletBinding()]
param(
    [int] $Port = 8765
)

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

# Porta ocupada e rotina, nao excecao: o Docker Desktop tomou a 8765 desta
# maquina numa manha em que o painel estava parado, e o uvicorn morria com
# WinError 10048 sem que o script dissesse por que. Ceder custa menos que
# disputar.
$porta = $null
foreach ($candidata in $Port..($Port + 19)) {
    $escuta = $null
    try {
        $escuta = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidata)
        $escuta.Start()
        $porta = $candidata
        break
    } catch {
        continue
    } finally {
        if ($null -ne $escuta) { $escuta.Stop() }
    }
}
if ($null -eq $porta) { throw "Nenhuma porta livre entre $Port e $($Port + 19)." }
if ($porta -ne $Port) { Write-Host "Porta $Port ocupada; usando $porta" -ForegroundColor Yellow }

# Tambem para as Settings, e nao so para o uvicorn: a porta entra na lista de
# origens aceitas em requisicao que altera estado (defesa D5). Sem isso, subir
# fora da 8765 devolve 403 em todo botao do painel, com a tela carregando
# normalmente.
$env:DEVCOCKPIT_PORT = "$porta"

Write-Host "Subindo em http://127.0.0.1:$porta" -ForegroundColor Green
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $porta
