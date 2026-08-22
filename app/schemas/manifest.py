"""Schemas do manifesto `devcockpit.yml` (US-090, US-091).

O schema está descrito em `docs/08-project-configuration-spec.md`. As regras de
validação daqui são o que impede um arquivo dentro de um repositório clonado de
virar vetor: sem elas, um manifesto de terceiro apontaria o health check para
host arbitrário e transformaria o DevCockpit em cliente HTTP de qualquer coisa.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import HealthKind
from app.schemas.project import ServiceOut, validate_local_http_url

#: Versões de schema que este binário sabe ler. Versão fora daqui não é erro
#: fatal: o arquivo é ignorado com aviso (regra de validação da spec 08).
SUPPORTED_VERSIONS = frozenset({1})

MANIFEST_VERSION = 1

_SERVICE_KEY = re.compile(r"[a-z0-9_-]{1,32}")


class ManifestServiceEntry(BaseModel):
    """Um serviço declarado no manifesto.

    A chave do serviço é a chave do mapa YAML, não um campo — declará-la duas
    vezes criaria contradição possível.
    """

    model_config = ConfigDict(extra="ignore")

    label: str | None = Field(default=None, max_length=80)
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = None
    health: str | None = None
    health_kind: HealthKind | None = None
    open_in_browser: bool = True

    @field_validator("url", "health")
    @classmethod
    def must_be_local_http(cls, value: str | None) -> str | None:
        return validate_local_http_url(value)


class ManifestDocker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    #: Sempre relativo ao diretório do projeto. Quem garante que resolve dentro
    #: dele é `resolve_within_project`, na importação.
    compose_file: str | None = Field(default=None, max_length=200)
    project_name: str | None = Field(default=None, max_length=120)


class ManifestRepository(BaseModel):
    """Informativo. O estado do Git vem do disco, nunca do manifesto."""

    model_config = ConfigDict(extra="ignore")

    provider: str | None = Field(default=None, max_length=20)
    url: str | None = Field(default=None, max_length=400)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    stack: list[str] = Field(default_factory=list)
    docker: ManifestDocker | None = None
    services: dict[str, ManifestServiceEntry] = Field(default_factory=dict)
    repository: ManifestRepository | None = None

    @field_validator("services")
    @classmethod
    def keys_must_be_slugs(
        cls, value: dict[str, ManifestServiceEntry]
    ) -> dict[str, ManifestServiceEntry]:
        for key in value:
            if not _SERVICE_KEY.fullmatch(key):
                raise ValueError(
                    f"Chave de serviço inválida: {key!r}. Use [a-z0-9_-] com até 32 caracteres."
                )
        return value

    @field_validator("stack")
    @classmethod
    def stack_entries_are_short(cls, value: list[str]) -> list[str]:
        limpos = [item.strip() for item in value if item and item.strip()]
        for item in limpos:
            if len(item) > 60:
                raise ValueError(f"Item de stack longo demais: {item[:20]}…")
        return limpos


# --- respostas da API ---


class ManifestFieldDiff(BaseModel):
    field: str
    database: str | None
    manifest: str | None


class ManifestStatus(BaseModel):
    """O que a UI precisa para decidir entre avisar, oferecer importar ou nada."""

    exists: bool
    filename: str | None = None
    valid: bool = False
    version: int | None = None
    warnings: list[str] = Field(default_factory=list)
    diff: list[ManifestFieldDiff] = Field(default_factory=list)
    in_sync: bool = True


class ManifestImportResult(BaseModel):
    applied: list[str]
    warnings: list[str] = Field(default_factory=list)
    services: list[ServiceOut] = Field(default_factory=list)


class ManifestExportRequest(BaseModel):
    """Escrever em pasta de projeto exige confirmação explícita (FR-112)."""

    confirm: bool = False


class ManifestExportResult(BaseModel):
    path: str
    bytes_written: int
    overwritten: bool


class ManifestPreview(BaseModel):
    content: str
