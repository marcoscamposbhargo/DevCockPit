<#
.SYNOPSIS
    Gera o executável do DevCockpit em dist\DevCockpit.

.DESCRIPTION
    Empacota a aplicação com o PyInstaller no modo pasta, seguindo
    `devcockpit.spec`. O resultado é uma pasta autocontida: quem receber não
    precisa de Python, ambiente virtual nem do repositório.

    Banco, log e configuração NÃO vão no pacote — eles nascem ao lado do
    executável na primeira execução. Por isso a pasta pode ser copiada para
    outra máquina, e por isso este script apaga esses arquivos antes de
    empacotar: um `data\devcockpit.db` esquecido dentro de `dist` viajaria com
    os projetos cadastrados na sua máquina.

.PARAMETER Install
    Copia o resultado para C:\Users\<voce>\DevCockpit, preservando data\,
    logs\ e configs\ que ja existirem la. E onde o executavel deve morar de
    verdade: `dist` e area de build, apagada por -Clean, e levaria junto o
    banco com os projetos cadastrados.

.PARAMETER Run
    Abre o executável recém-gerado ao terminar.

.PARAMETER Clean
    Apaga `build\pyinstaller` e `dist\DevCockpit` antes de empacotar. Use quando
    trocar dependência ou mexer no `.spec` — o PyInstaller reaproveita análise
    anterior e um pacote meio velho é pior que um build demorado.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -Clean -Run
#>

[CmdletBinding()]
param(
    [switch] $Run,
    [switch] $Clean,
    [switch] $Install
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$saida = Join-Path $root 'dist\DevCockpit'
$trabalho = Join-Path $root 'build\pyinstaller'
$instalado = Join-Path $env:USERPROFILE 'DevCockpit'

if (-not (Test-Path $python)) {
    throw "Ambiente virtual ausente. Rode scripts\dev.ps1 uma vez para cria-lo."
}

# O PyInstaller é dependência só de empacotamento: não entra em `dependencies`
# do projeto, e uma máquina que nunca gerou executável não o tem.
& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Instalando PyInstaller...' -ForegroundColor Cyan
    & $python -m pip install "pyinstaller>=6.10" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o PyInstaller.' }
}

# Um executável travado na memória faz o build morrer no meio da cópia, com
# erro de acesso negado que não diz que a causa é o app aberto.
$rodando = @(Get-Process -Name 'DevCockpit' -ErrorAction SilentlyContinue)
if ($rodando.Count -gt 0) {
    Write-Host "Fechando $($rodando.Count) instancia(s) do DevCockpit..." -ForegroundColor Cyan
    $rodando | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

if ($Clean) {
    foreach ($alvo in @($saida, $trabalho)) {
        if (Test-Path $alvo) {
            Write-Host "Limpando $alvo" -ForegroundColor DarkGray
            Remove-Item $alvo -Recurse -Force
        }
    }
}

# O icone e gerado por codigo (scripts\make_icon.py) para nao existir um .ico
# binario que ninguem sabe refazer quando a cor do tema mudar.
$icone = Join-Path $root 'frontend\assets\devcockpit.ico'
if (-not (Test-Path $icone)) {
    Write-Host 'Gerando icone...' -ForegroundColor Cyan
    & $python -c "import PIL" 2>$null
    if ($LASTEXITCODE -ne 0) { & $python -m pip install pillow | Out-Null }
    & $python (Join-Path $root 'scripts\make_icon.py')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o icone.' }
}

Write-Host 'Empacotando...' -ForegroundColor Cyan
& $python -m PyInstaller (Join-Path $root 'devcockpit.spec') --noconfirm `
    --distpath (Join-Path $root 'dist') --workpath $trabalho
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (codigo $LASTEXITCODE)." }

# Resíduo de execução anterior dentro da pasta empacotada.
foreach ($residuo in @('data', 'logs', 'configs')) {
    $caminho = Join-Path $saida $residuo
    if (Test-Path $caminho) {
        Write-Host "Removendo residuo de execucao: $residuo\" -ForegroundColor DarkGray
        Remove-Item $caminho -Recurse -Force
    }
}

if ($Install) {
    Write-Host "Instalando em $instalado" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $instalado -Force | Out-Null

    # So o programa e substituido. data\, logs\ e configs\ ficam onde estao: e
    # onde vivem os projetos cadastrados, e uma atualizacao que os apaga e pior
    # que nao atualizar.
    # O DevCockpit em execucao segura o proprio .exe: sem fechar, a copia falha.
    Get-Process DevCockpit -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "Encerrando DevCockpit (PID $($_.Id)) para substituir o programa." -ForegroundColor DarkGray
        $_ | Stop-Process -Force
    }

    # Outro programa pode ter uma DLL do pacote mapeada -- o VS Code mantem
    # VCRUNTIME140.dll aberta quando o repositorio esta aberto nele. Apagar
    # falha, mas renomear funciona mesmo sob lock: o nome sai da frente, o
    # arquivo novo entra, e o antigo some no proximo build.
    $antigo = Join-Path $instalado '_internal'
    if (Test-Path $antigo) {
        Get-ChildItem $antigo -Filter '*.travado-*' -Recurse -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue

        foreach ($arquivo in Get-ChildItem $antigo -Recurse -File) {
            try {
                $fluxo = [System.IO.File]::Open($arquivo.FullName, 'Open', 'ReadWrite', 'None')
                $fluxo.Close()
                Remove-Item $arquivo.FullName -Force
            } catch {
                $carimbo = Get-Date -Format 'yyyyMMdd-HHmmss'
                Rename-Item $arquivo.FullName "$($arquivo.Name).travado-$carimbo" -ErrorAction Stop
                Write-Host "  $($arquivo.Name) esta em uso por outro programa; contornado." -ForegroundColor DarkYellow
            }
        }
    }

    Copy-Item (Join-Path $saida '_internal') $instalado -Recurse -Force
    Copy-Item (Join-Path $saida 'DevCockpit.exe') $instalado -Force

    Write-Host 'Programa atualizado; dados preservados.' -ForegroundColor Green
}

$tamanho = [math]::Round((Get-ChildItem $saida -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1MB, 1)

Write-Host ''
Write-Host "Pronto: $saida ($tamanho MB)" -ForegroundColor Green
Write-Host 'Copie a pasta inteira. Banco, log e configs nascem ao lado do .exe.' -ForegroundColor DarkGray

if ($Run) {
    $exe = if ($Install) { Join-Path $instalado 'DevCockpit.exe' } else { Join-Path $saida 'DevCockpit.exe' }
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
}
