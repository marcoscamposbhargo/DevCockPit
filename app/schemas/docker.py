"""Schemas de Docker."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortOut(BaseModel):
    host_port: int
    container_port: int
    protocol: str = "tcp"


class ContainerOut(BaseModel):
    name: str
    service: str
    state: str
    image: str
    status: str
    health: str | None = None
    exit_code: int | None = None
    ports: list[PortOut] = Field(default_factory=list)


class DockerStatusOut(BaseModel):
    available: bool
    compose_file: str | None = None
    detail: str | None = None
    containers: list[ContainerOut] = Field(default_factory=list)
    running_count: int = 0
    declared_services: list[str] = Field(default_factory=list)


class DockerActionRequest(BaseModel):
    #: Apenas nomes que existam no Compose do projeto. Desconhecido é 422 e
    #: nenhum comando é executado (defesa D2).
    services: list[str] = Field(default_factory=list, max_length=50)


class DockerLogsOut(BaseModel):
    service: str | None = None
    tail: int
    lines: list[str] = Field(default_factory=list)
