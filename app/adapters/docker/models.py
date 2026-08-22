"""Objetos de domínio do Docker."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PublishedPort:
    host_port: int
    container_port: int
    protocol: str = "tcp"

    def __str__(self) -> str:
        return f"{self.host_port}->{self.container_port}/{self.protocol}"


@dataclass(frozen=True)
class Container:
    name: str
    service: str
    state: str
    image: str
    status: str
    health: str | None = None
    exit_code: int | None = None
    ports: list[PublishedPort] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.state.lower() == "running"


@dataclass
class ComposeStatus:
    """Estado do Compose de um projeto.

    `available: False` não é erro: é resposta honesta quando o daemon não
    responde. O dashboard precisa continuar carregando (NFR-060).
    """

    available: bool
    compose_file: str | None = None
    containers: list[Container] = field(default_factory=list)
    detail: str | None = None

    @property
    def running_count(self) -> int:
        return sum(1 for container in self.containers if container.is_running)
