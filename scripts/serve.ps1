<#
.SYNOPSIS
    Sobe o DevCockpit em segundo plano, solto da sessão que o iniciou.

.DESCRIPTION
    `dev.ps1` prende o servidor ao terminal que o chamou: fechar o terminal,
    interromper um agente ou encerrar a sessão derruba o uvicorn junto — o log
    mostra "Application shutdown complete" e parece que a aplicação quebrou,
    quando na verdade ela só recebeu o sinal de término de quem a hospedava.

    Este script existe para o caso oposto: o servidor fica de pé até alguém
    mandar parar. É o modo usado no dia a dia; `dev.ps1` continua sendo o modo
    de acompanhar o log ao vivo no próprio terminal.

.PARAMETER Restart
    Para o que estiver rodando e sobe de novo. É como recarregar código novo.

.PARAMETER Stop
    Só para. Não sobe nada.

.PARAMETER Status
    Só informa. Não sobe nem para nada.

.PARAMETER Reload
    Liga o `--reload` do uvicorn. Desligado por padrão: o observador de arquivos
    já deixou de aplicar mudança de schema mais de uma vez, e um servidor que
    diz ter recarregado sem ter recarregado custa mais caro do que reiniciar na
    mão.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
    powershell -ExecutionPolicy Bypass -File scripts\serve.ps1 -Restart
    powershell -ExecutionPolicy Bypass -File scripts\serve.ps1 -Status
#>

[CmdletBinding()]
param(
    [switch] $Restart,
    [switch] $Stop,
    [switch] $Status,
    [switch] $Reload,
    [int]    $Port = 8765
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$logDir = Join-Path $root 'logs'
$pidFile = Join-Path $logDir 'server.pid'
$outLog = Join-Path $logDir 'server.out'
$errLog = Join-Path $logDir 'server.err'

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Get-ServerProcesses {
    # A porta é a verdade, não o arquivo de PID: um servidor subido à mão por
    # fora deste script também precisa ser encontrado, senão o "já está no ar"
    # mente e duas instâncias brigam pela mesma porta.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*uvicorn*app.main:app*--port $Port*" }
}

function Test-ServerResponding {
    try {
        $resposta = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" `
            -Headers @{ Host = "127.0.0.1:$Port" } -TimeoutSec 3 -UseBasicParsing
        return $resposta.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Show-Status {
    $processos = @(Get-ServerProcesses)
    $respondendo = Test-ServerResponding

    if ($processos.Count -eq 0 -and -not $respondendo) {
        Write-Host "PARADO — nada escutando em 127.0.0.1:$Port" -ForegroundColor DarkGray
        return $false
    }

    $pids = ($processos | Select-Object -ExpandProperty ProcessId) -join ', '
    if ($respondendo) {
        Write-Host "NO AR — http://127.0.0.1:$Port (pid $pids)" -ForegroundColor Green
    } else {
        # Processo vivo que não responde é pior que processo morto: a porta está
        # ocupada e a aplicação não atende.
        Write-Host "TRAVADO — processo vivo (pid $pids) mas /api/health nao responde" -ForegroundColor Yellow
        Write-Host "          use -Restart" -ForegroundColor Yellow
    }
    return $true
}

function Stop-Server {
    $processos = @(Get-ServerProcesses)
    if ($processos.Count -eq 0) {
        Write-Host 'Nada para parar.' -ForegroundColor DarkGray
        return
    }

    foreach ($processo in $processos) {
        Write-Host "Parando pid $($processo.ProcessId)..." -ForegroundColor Cyan
        Stop-Process -Id $processo.ProcessId -Force -ErrorAction SilentlyContinue
    }

    # O worker morre junto com o pai, mas não instantaneamente.
    $limite = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $limite -and @(Get-ServerProcesses).Count -gt 0) {
        Start-Sleep -Milliseconds 250
    }

    if (@(Get-ServerProcesses).Count -gt 0) {
        Write-Host 'AVISO: algum processo resistiu ao termino.' -ForegroundColor Yellow
    } else {
        Write-Host 'Parado.' -ForegroundColor Green
    }
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
}

function Start-Server {
    if (-not (Test-Path $python)) {
        throw "Ambiente virtual ausente. Rode scripts\dev.ps1 uma vez para cria-lo."
    }

    Write-Host 'Aplicando migracoes...' -ForegroundColor Cyan
    # O alembic escreve as linhas `INFO` dele em stderr mesmo quando dá tudo
    # certo. Com `$ErrorActionPreference = 'Stop'`, o PowerShell 5.1 empacota
    # cada uma dessas linhas num ErrorRecord e o script morre aqui — antes de
    # chegar no uvicorn. O sintoma era "o servidor não sobe" sem erro nenhum
    # que apontasse para migração.
    #
    # Quem decide se a migração falhou é o código de saída, não o fato de ter
    # havido escrita em stderr.
    $saidaAlembic = & {
        $ErrorActionPreference = 'Continue'
        & $python -m alembic upgrade head 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
        $saidaAlembic | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "Falha ao aplicar as migracoes (codigo $LASTEXITCODE)."
    }

    $argumentos = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    if ($Reload) { $argumentos += '--reload' }

    # Sem `-NoNewWindow`: o processo precisa sobreviver ao terminal que o criou.
    $processo = Start-Process -FilePath $python -ArgumentList $argumentos `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    Set-Content -Path $pidFile -Value $processo.Id -Encoding utf8

    $limite = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $limite) {
        if (Test-ServerResponding) {
            Write-Host "NO AR — http://127.0.0.1:$Port (pid $($processo.Id))" -ForegroundColor Green
            Write-Host "Log: logs\server.err   Parar: scripts\serve.ps1 -Stop" -ForegroundColor DarkGray
            return
        }
        if ($processo.HasExited) { break }
        Start-Sleep -Milliseconds 300
    }

    Write-Host 'FALHOU: o servidor nao respondeu. Ultimas linhas do log:' -ForegroundColor Red
    if (Test-Path $errLog) { Get-Content $errLog -Tail 20 }
    exit 1
}

# --- despacho ---

if ($Status) { Show-Status | Out-Null; return }
if ($Stop) { Stop-Server; return }
if ($Restart) { Stop-Server; Start-Server; return }

if (@(Get-ServerProcesses).Count -gt 0) {
    # Subir por cima de um servidor que já está no ar só produz erro de porta
    # ocupada e um log confuso.
    Write-Host 'Ja esta rodando. Use -Restart para recarregar o codigo.' -ForegroundColor Yellow
    Show-Status | Out-Null
    return
}

Start-Server
