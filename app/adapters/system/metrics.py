"""Leitura do estado da máquina: processador, memória, disco e temperatura.

Duas fontes com custos muito diferentes, e é isso que organiza o módulo:

- **`psutil`** responde processador, memória e disco em poucos milissegundos.
  Pode ser lido a cada par de segundos sem ninguém notar.
- **A temperatura** só existe no Windows através do WMI, e ler WMI exige subir
  um `powershell.exe`. Medido nesta máquina: 341 ms por leitura. Isso não cabe
  num relógio de dois segundos, então tem cadência própria e cache.

Sobre o que a temperatura significa: `Win32_PerfFormattedData_Counters_Thermal
ZoneInformation` devolve a zona térmica ACPI, que é a placa e não o núcleo do
processador. Ela costuma marcar bem menos que a temperatura de núcleo que um
HWMonitor mostra, e apresentá-la como "CPU" seria mentira. O rótulo diz zona
térmica, e é isso que ela é.

`MSAcpi_ThermalZoneTemperature`, que seria a leitura mais direta, responde
"Acesso negado" sem privilégio administrativo — e o painel não pede privilégio
para nada (defesa D3).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.runner.command_spec import CommandSpec

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

#: Kelvin em décimos -> Celsius. O contador do Windows devolve décimos de
#: Kelvin, não Kelvin: 3010 são 301,0 K, que são 27,9 °C.
_ZERO_ABSOLUTO_DECIMOS = 2731.5

_TEMPERATURA_PS = (
    "Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_Thermal"
    "ZoneInformation -ErrorAction SilentlyContinue | "
    "Select-Object -First 1 -ExpandProperty HighPrecisionTemperature"
)


@dataclass(frozen=True)
class MachineMetrics:
    """Estado da máquina num instante."""

    cpu_percent: float
    cpu_count: int
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_free_gb: float
    #: `None` quando a plataforma não expõe, ou a leitura falhou. A tela precisa
    #: distinguir "não sei" de "está frio".
    temperature_c: float | None = None


@dataclass(frozen=True)
class ProcessMetrics:
    """Consumo de um processo que o painel subiu."""

    pid: int
    cpu_percent: float
    memory_mb: float
    #: Quantos processos a árvore tem. Um `npm run dev` vira meia dúzia, e
    #: somar todos é a única leitura honesta do que aquele servidor custa.
    process_count: int = 1


def read_machine(temperature_c: float | None = None) -> MachineMetrics:
    """Processador, memória e disco agora. Custa poucos milissegundos.

    `cpu_percent` sem intervalo devolve a média desde a última chamada, e não
    bloqueia. A primeira leitura de todas sai 0,0 — quem chama trata isso como
    "ainda não sei", não como "ocioso".
    """
    memoria = psutil.virtual_memory()
    disco = psutil.disk_usage(str(Path.home().anchor or "/"))

    return MachineMetrics(
        cpu_percent=psutil.cpu_percent(interval=None),
        cpu_count=psutil.cpu_count(logical=True) or 0,
        memory_percent=memoria.percent,
        memory_used_gb=round(memoria.used / 1024**3, 1),
        memory_total_gb=round(memoria.total / 1024**3, 1),
        disk_percent=disco.percent,
        disk_free_gb=round(disco.free / 1024**3, 1),
        temperature_c=temperature_c,
    )


def read_process_tree(pid: int) -> ProcessMetrics | None:
    """Consumo do processo e de toda a descendência dele.

    A árvore inteira, e não só o pai: `npm run dev` é um `cmd.exe` que gasta
    zero e um `node` que gasta tudo. Medir só o pai mostraria 0% num servidor
    que está fritando o processador.
    """
    try:
        raiz = psutil.Process(pid)
        arvore = [raiz, *raiz.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    cpu = 0.0
    memoria = 0.0
    vivos = 0

    for processo in arvore:
        try:
            cpu += processo.cpu_percent(interval=None)
            memoria += processo.memory_info().rss
            vivos += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not vivos:
        return None

    return ProcessMetrics(
        pid=pid,
        # Num processador de doze núcleos, `cpu_percent` de uma árvore pode
        # passar de 100 — é a soma por núcleo. Dividir pelo número de núcleos
        # dá a fração da máquina, que é o que a barra na tela representa.
        cpu_percent=round(cpu / max(psutil.cpu_count(logical=True) or 1, 1), 1),
        memory_mb=round(memoria / 1024**2, 1),
        process_count=vivos,
    )


def temperature_spec(cwd: Path, timeout_s: float = 10.0) -> CommandSpec | None:
    """Comando que lê a zona térmica. `None` fora do Windows.

    Argv fixo no código, sem nada vindo do cliente — o mesmo contrato de
    qualquer outra execução do painel (ADR-003).
    """
    if not _IS_WINDOWS:
        return None

    return CommandSpec(
        argv=[
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _TEMPERATURA_PS,
        ],
        cwd=cwd,
        timeout_s=timeout_s,
        label="system.temperature",
    )


def parse_temperature(saida: str) -> float | None:
    """Décimos de Kelvin -> Celsius, ou `None` se a saída não trouxer número.

    Máquina sem zona térmica exposta devolve vazio, e isso não é erro: é a
    resposta honesta de "esta máquina não conta". Vale para muito desktop e
    para máquina virtual.
    """
    achado = re.search(r"\d+", saida or "")
    if achado is None:
        return None

    celsius = (int(achado.group()) - _ZERO_ABSOLUTO_DECIMOS) / 10

    # Fora desta faixa não é temperatura de máquina ligada: é contador zerado,
    # unidade diferente, ou lixo. Melhor não mostrar nada que mostrar -273.
    if not -20 <= celsius <= 130:
        return None

    return round(celsius, 1)
