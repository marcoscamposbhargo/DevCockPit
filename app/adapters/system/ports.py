"""Quem está escutando nas portas locais, agora.

Este módulo só **observa**. Ele não decide de quem é a porta, não compara com
nada declarado e não mata processo nenhum — a nota em `app/runner/process.py`
vale em dobro aqui: localizar processo por porta para encerrá-lo derruba o
Docker Desktop junto. Isto aqui lê e devolve.

Por que `psutil` e não `netstat`/`Get-NetTCPConnection`: a pergunta que importa
não é "que portas estão abertas" e sim "de quem é o processo que abriu". Só o
diretório de trabalho do processo permite dizer que a porta 8765 é *deste*
projeto e não de outro. Medido nesta máquina: `psutil` responde a varredura
inteira em ~5 ms; o caminho por PowerShell (`Get-NetTCPConnection` +
`Get-Process`) levava ~1,4 s, o que já não caberia num ciclo de poller sem
aparecer.

Processo de outro usuário — serviço do Windows, em geral — recusa a leitura.
Isso não é erro: a porta continua sendo reportada, só que sem dono conhecido.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

#: Endereços que contam como "escutando aqui". `0.0.0.0` e `::` entram porque
#: quem escuta em todas as interfaces também escuta no loopback — e é assim que
#: a maioria dos servidores de desenvolvimento sobe.
LOCAL_BIND_ADDRESSES = frozenset({"0.0.0.0", "127.0.0.1", "::", "::1", ""})

#: Processos que publicam porta em nome de outra coisa. O diretório de trabalho
#: deles aponta para a instalação do próprio Docker, nunca para o projeto, então
#: casar por `cwd` jamais funcionaria — e sem esta marcação a porta apareceria
#: como "dono desconhecido", que é pior que a verdade.
CONTAINER_RUNTIMES = frozenset(
    {
        "com.docker.backend.exe",
        "com.docker.backend",
        "docker-proxy",
        "docker-proxy.exe",
        "dockerd",
        "dockerd.exe",
        "wslrelay.exe",
    }
)


@dataclass(frozen=True)
class ListeningPort:
    """Uma porta local com o que se conseguiu descobrir sobre quem a abriu."""

    port: int
    pid: int | None = None
    process_name: str | None = None
    #: Diretório de trabalho do processo. `None` quando a leitura foi recusada.
    cwd: str | None = None
    cmdline: str = ""
    addresses: frozenset[str] = field(default_factory=frozenset)

    @property
    def via_container_runtime(self) -> bool:
        """Porta publicada por um runtime de container, não pelo projeto."""
        return (self.process_name or "").lower() in {
            name.lower() for name in CONTAINER_RUNTIMES
        }


class PortScanner:
    """Enumera as portas em escuta. Substituível nos testes por uma lista fixa."""

    def scan(self) -> list[ListeningPort]:
        raise NotImplementedError


class PsutilPortScanner(PortScanner):
    def scan(self) -> list[ListeningPort]:
        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, OSError) as exc:
            # Sem privilégio para enumerar: a descoberta some, o resto da
            # aplicação continua. Um painel que quebra porque não conseguiu
            # olhar as portas é pior que um painel sem essa coluna.
            logger.warning(
                "não foi possível enumerar as portas em escuta",
                extra={"extra_fields": {"error": str(exc)}},
            )
            return []

        #: Uma porta costuma aparecer duas vezes, IPv4 e IPv6. É a mesma porta.
        por_porta: dict[int, dict] = {}

        for conn in connections:
            if conn.status != psutil.CONN_LISTEN or conn.laddr is None:
                continue

            address = getattr(conn.laddr, "ip", "")
            if address not in LOCAL_BIND_ADDRESSES:
                continue

            port = getattr(conn.laddr, "port", 0)
            if not 1 <= port <= 65535:
                continue

            entrada = por_porta.setdefault(port, {"pid": conn.pid, "addresses": set()})
            entrada["addresses"].add(address)
            # A primeira entrada com PID conhecido vence: a duplicata IPv6 às
            # vezes vem sem PID.
            if entrada["pid"] is None:
                entrada["pid"] = conn.pid

        return [
            self._describe(port, entrada["pid"], frozenset(entrada["addresses"]))
            for port, entrada in sorted(por_porta.items())
        ]

    @staticmethod
    def _describe(port: int, pid: int | None, addresses: frozenset[str]) -> ListeningPort:
        if not pid:
            return ListeningPort(port=port, addresses=addresses)

        name: str | None = None
        cwd: str | None = None
        cmdline = ""

        try:
            process = psutil.Process(pid)
            name = process.name()
            # Cada leitura tem o seu próprio try: num processo de sistema o
            # nome vem e o `cwd` é recusado, e perder o nome por causa disso
            # apagaria a única pista útil que restava.
            try:
                cwd = process.cwd()
            except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                cwd = None
            try:
                cmdline = " ".join(process.cmdline())
            except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                cmdline = ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass

        return ListeningPort(
            port=port,
            pid=pid,
            process_name=name,
            cwd=cwd,
            cmdline=cmdline,
            addresses=addresses,
        )


class FakePortScanner(PortScanner):
    """Lista fixa. Teste de descoberta não pode depender do que a máquina roda."""

    def __init__(self, ports: list[ListeningPort] | None = None) -> None:
        self.ports = ports or []

    def scan(self) -> list[ListeningPort]:
        return list(self.ports)


def build_port_scanner() -> PortScanner:
    return PsutilPortScanner()


def normalized(path: str | None) -> tuple[str, ...] | None:
    """Componentes comparáveis de um path, ou `None` se não houver path.

    Espelha `app.core.paths.normalize_for_comparison`, mas aceita `None` e
    string vazia — que é o caso comum aqui, onde o `cwd` pode ter sido negado.
    """
    if not path:
        return None
    parts = Path(path).parts
    if os.name == "nt":
        return tuple(part.lower() for part in parts)
    return parts
