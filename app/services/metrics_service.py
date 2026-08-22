"""Métricas da máquina e dos servidores que o painel subiu.

Existe para responder duas perguntas que hoje custam abrir o Gerenciador de
Tarefas: **"a máquina está aguentando?"** e **"qual projeto está comendo ela?"**.

A segunda é a que só este painel sabe responder. O Gerenciador de Tarefas mostra
dezoito processos `node.exe` e nenhum nome de projeto; aqui cada árvore de
processo tem dono, porque foi o painel que a subiu.

Duas cadências, porque os custos são diferentes por ordens de grandeza:

- processador, memória e disco custam milissegundos e podem ser lidos sempre;
- a temperatura exige subir um `powershell.exe` (341 ms medidos nesta máquina),
  então tem cache próprio e um intervalo bem mais folgado.

Misturar as duas cadências faria a leitura barata pagar o preço da cara.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.adapters.system.metrics import (
    MachineMetrics,
    parse_temperature,
    read_machine,
    read_process_tree,
    temperature_spec,
)
from app.runner.command_runner import CommandRunner

logger = logging.getLogger(__name__)

#: A temperatura de uma máquina não muda de forma interessante em dois
#: segundos, e a leitura custa caro. Trinta segundos é mais que suficiente para
#: perceber uma subida sustentada, que é o que importa.
TEMPERATURE_TTL_S = 30.0


@dataclass
class ServerMetrics:
    """Consumo de um servidor de desenvolvimento, com o projeto dele."""

    project_id: str
    project_name: str
    pid: int
    cpu_percent: float
    memory_mb: float
    process_count: int


@dataclass
class MetricsSnapshot:
    machine: MachineMetrics
    servers: list[ServerMetrics] = field(default_factory=list)


class MetricsService:
    def __init__(self, runner: CommandRunner, project_root: Path) -> None:
        self.runner = runner
        # O comando precisa de um diretório de trabalho e não usa nada dele; a
        # raiz do projeto é a escolha previsível.
        self.project_root = project_root
        self._temperatura: float | None = None
        self._lida_em: float = 0.0

    def snapshot(self, servidores) -> MetricsSnapshot:  # type: ignore[no-untyped-def]
        """Uma leitura completa. `servidores` são os registros de `dev_server`."""
        return MetricsSnapshot(
            machine=read_machine(temperature_c=self._temperature()),
            servers=[
                ServerMetrics(
                    project_id=registro.project_id,
                    project_name=nome,
                    pid=registro.pid,
                    cpu_percent=medida.cpu_percent,
                    memory_mb=medida.memory_mb,
                    process_count=medida.process_count,
                )
                for registro, nome in servidores
                if (medida := read_process_tree(registro.pid)) is not None
            ],
        )

    def _temperature(self) -> float | None:
        """Temperatura com cache. Fora do Windows, sempre `None`."""
        agora = time.monotonic()
        if self._lida_em and agora - self._lida_em < TEMPERATURE_TTL_S:
            return self._temperatura

        self._lida_em = agora
        spec = temperature_spec(self.project_root)
        if spec is None:
            self._temperatura = None
            return None

        try:
            resultado = self.runner.run(spec)
        except Exception:  # noqa: BLE001 - métrica nunca derruba a tela
            logger.exception("falha ao ler a temperatura")
            self._temperatura = None
            return None

        # Saída vazia é resposta legítima: muita máquina e toda máquina virtual
        # não expõem zona térmica. `None` vira "—" na tela, não zero.
        self._temperatura = parse_temperature(resultado.stdout) if resultado.ok else None
        return self._temperatura
