"""Entidades da Fase 1: Project, ProjectTechnology, ProjectService, ActivityLog.

Ver `docs/05-data-model.md`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UtcDateTime, utcnow


class ProjectStatus(StrEnum):
    REGISTERED = "REGISTERED"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"


class TechnologySource(StrEnum):
    DETECTED = "DETECTED"
    MANUAL = "MANUAL"


class HealthKind(StrEnum):
    HTTP = "HTTP"
    TCP = "TCP"
    NONE = "NONE"


class ActivityStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"


class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProjectStatus.REGISTERED.value
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detection_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    technologies: Mapped[list[ProjectTechnology]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    services: Mapped[list[ProjectService]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_project_status", "status"),
        Index("ix_project_last_accessed", "last_accessed_at"),
    )


class ProjectTechnology(Base):
    __tablename__ = "project_technology"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default=TechnologySource.DETECTED.value
    )
    evidence: Mapped[str | None] = mapped_column(String(200), nullable=True)

    project: Mapped[Project] = relationship(back_populates="technologies")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_technology"),)


class ProjectService(Base):
    __tablename__ = "project_service"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    host: Mapped[str] = mapped_column(String(80), nullable=False, default="localhost")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    health_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    health_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default=HealthKind.TCP.value
    )
    open_in_browser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project: Mapped[Project] = relationship(back_populates="services")

    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_service"),
        Index("ix_project_service_port", "port"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argv: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_activity_project_created", "project_id", "created_at"),)


class GitRepository(Base):
    """Cache do estado do repositório. Não é fonte de verdade: o disco é."""

    __tablename__ = "git_repository"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    is_repo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_origin_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dirty_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ahead: Mapped[int | None] = mapped_column(Integer, nullable=True)
    behind: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_commit_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_commit_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)


class DockerConfig(Base):
    __tablename__ = "docker_config"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Relativo ao diretório do projeto (decisão em docs/05-data-model.md).
    compose_file: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    has_dockerfile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_services: Mapped[str | None] = mapped_column(Text, nullable=True)


class HealthSnapshot(Base):
    """Histórico de verificação. O estado corrente vive em cache, não aqui."""

    __tablename__ = "health_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    service_key: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_health_service_checked", "project_id", "service_key", "checked_at"),
    )


class DevServer(Base):
    """Servidor de desenvolvimento que o painel subiu, e ainda está de pé.

    Persistido porque o processo **sobrevive ao DevCockpit** de propósito:
    reiniciar o painel não pode derrubar o servidor de ninguém. Sem a linha
    aqui, reiniciar o painel tiraria o botão de parar junto e sobraria um
    processo que só o Gerenciador de Tarefas alcança.

    Uma linha por projeto: dois servidores do mesmo projeto disputariam a mesma
    porta, então a chave primária é o próprio `project_id`.
    """

    __tablename__ = "dev_server"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Guardado para conferir o PID na volta. O sistema recicla identificador
    #: de processo, e parar o PID errado é matar processo de terceiro.
    command: Mapped[str] = mapped_column(Text, nullable=False)
    cwd: Mapped[str] = mapped_column(Text, nullable=False)
    log_file: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
