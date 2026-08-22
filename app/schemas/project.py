"""Schemas de entrada e saída da API (Pydantic v2).

Validação declarativa é parte da defesa D2: o que não passa por aqui não chega
perto de virar argumento de comando.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import HealthKind, ProjectStatus, TechnologySource

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def validate_local_http_url(value: str | None) -> str | None:
    """Restringe URLs a HTTP local (ver `docs/08-project-configuration-spec.md`).

    Sem isso, um manifesto transformaria o DevCockpit em cliente HTTP para
    host arbitrário — e o poller de health passaria a bater nesse host a cada
    ciclo. Vive fora da classe porque o manifesto reusa a mesma regra: duas
    cópias da regra seriam duas chances de divergir.

    A extração do host é feita por `urlparse`, nunca por fatiamento de string.
    A forma `http://localhost:3000@evil.com/` tem `localhost:3000` como
    *userinfo* e `evil.com` como host: qualquer parser caseiro que corte no
    primeiro `:` lê o pedaço errado e libera destino externo.
    """
    if value is None:
        return None
    text = value.strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("A URL precisa usar http ou https.")
    host = (parsed.hostname or "").strip("[]")
    if host not in {h.strip("[]") for h in _LOCAL_HOSTS}:
        raise ValueError("A URL precisa apontar para localhost.")
    return text


class TechnologyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    category: str
    source: TechnologySource
    evidence: str | None = None


class ServiceIn(BaseModel):
    key: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=80)
    host: str = "localhost"
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = None
    health_url: str | None = None
    health_kind: HealthKind = HealthKind.TCP
    open_in_browser: bool = True

    @field_validator("url", "health_url")
    @classmethod
    def must_be_local_http(cls, value: str | None) -> str | None:
        return validate_local_http_url(value)


class ServiceOut(ServiceIn):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    run_detection: bool = True
    #: `devcockpit.yml` presente na raiz é importado no cadastro (FR-110). Não
    #: há o que sobrescrever num projeto recém-criado, então o padrão é ligado.
    import_manifest: bool = True


class ProjectUpdate(BaseModel):
    """`path` não está aqui de propósito (decisão D-06)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_pinned: bool | None = None
    detection_locked: bool | None = None


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    path: str
    status: ProjectStatus
    is_pinned: bool
    technologies: list[str] = Field(default_factory=list)
    #: Quantos serviços o projeto declara. O **estado** de cada um não vem
    #: daqui: listar projetos não pode disparar verificação de rede (NFR-010).
    #: A tela cruza este total com o que o dashboard já traz do cache.
    services_total: int = 0
    last_accessed_at: datetime | None = None
    #: O painel sabe subir a aplicação deste projeto (Compose ou comando de
    #: execução). Separa "posso ligar" de "não sei como", que na tela são um
    #: botão e uma explicação — nunca o mesmo botão apagado sem motivo.
    can_start: bool = False
    #: A **aplicação** está no ar. Não é o mesmo que "algum serviço responde":
    #: num projeto cujo banco vive em container, o banco continua respondendo
    #: com a aplicação parada, e contar os dois juntos fazia o botão anunciar
    #: "Ligado" logo depois de desligar.
    #:
    #: `None` quando o projeto não tem aplicação separada — a stack inteira
    #: roda em container e o Compose **é** a aplicação. Aí quem responde pelo
    #: estado é a verificação de saúde, e `false` seria mentira: diria "parado"
    #: com tudo no ar.
    app_running: bool | None = None


class ProjectDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    path: str
    status: ProjectStatus
    is_pinned: bool
    detection_locked: bool
    technologies: list[TechnologyOut] = Field(default_factory=list)
    services: list[ServiceOut] = Field(default_factory=list)
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectSummary]
    total: int


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str | None
    action: str
    status: str
    duration_ms: int | None
    exit_code: int | None
    message: str | None
    correlation_id: str | None
    created_at: datetime


class ActivityList(BaseModel):
    items: list[ActivityOut]
    total: int


class ToolAvailability(BaseModel):
    git: bool
    docker: bool
    code: bool


class HealthOut(BaseModel):
    status: str
    version: str
    tools: ToolAvailability
    allowed_roots: list[str]


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
