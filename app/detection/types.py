"""Tipos compartilhados pelos detectores.

Um detector responde a uma pergunta simples: "este diretório carrega a marca
X?". Ele não conhece banco, HTTP nem `subprocess` — só lê arquivo de manifesto
conhecido (defesa D9: superfície mínima de leitura).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Category:
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    DATABASE = "database"
    TOOLING = "tooling"


@dataclass(frozen=True)
class DetectedTech:
    name: str
    category: str
    evidence: str

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass(frozen=True)
class SuggestedService:
    key: str
    label: str
    port: int | None = None
    url: str | None = None
    health_kind: str = "TCP"
    #: De onde saiu o número: `"file"` quando foi lido de um arquivo do projeto
    #: (Compose, `vite.config`), `"convention"` quando é o padrão do framework.
    #:
    #: A diferença importa na hora de acusar divergência com o cadastro. "O
    #: Compose publica 5434 e você cadastrou 5433" é fato, e vale interromper
    #: alguém. "O padrão do uvicorn é 8000 e você cadastrou 3001" não é nada —
    #: quem cadastrou 3001 provavelmente passa `--port 3001`, e acusar isso
    #: transforma todo projeto com porta escolhida num alerta permanente.
    port_source: str = "convention"


@dataclass
class Detection:
    technologies: list[DetectedTech] = field(default_factory=list)
    services: list[SuggestedService] = field(default_factory=list)
    compose_file: str | None = None
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: Detection) -> None:
        known = {tech.name for tech in self.technologies}
        self.technologies.extend(t for t in other.technologies if t.name not in known)

        # Chave repetida: fica quem leu de arquivo. Antes era sempre o primeiro,
        # e isso bastava quando tudo vinha do mesmo diretório. Com monorepo, o
        # `backend/` é varrido antes do `infra/`: a porta **convencional** do
        # framework chegava primeiro e derrubava a que o Compose publica de
        # verdade. O projeto inteiro trata arquivo como mais forte que
        # convenção — o `merge` era o único lugar que não tratava.
        por_chave = {service.key: service for service in self.services}
        for candidato in other.services:
            atual = por_chave.get(candidato.key)
            if atual is None:
                self.services.append(candidato)
                por_chave[candidato.key] = candidato
            elif atual.port_source != "file" and candidato.port_source == "file":
                self.services[self.services.index(atual)] = candidato
                por_chave[candidato.key] = candidato

        self.compose_file = self.compose_file or other.compose_file
        self.warnings.extend(other.warnings)


class Detector(Protocol):
    name: str

    def detect(self, project_dir: Path) -> Detection | None: ...
