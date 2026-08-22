"""Cruza a porta **declarada** com a porta que está de fato escutando.

O problema que isto resolve: até aqui o DevCockpit só sabia o que alguém digitou
no cadastro. Se o número estivesse errado — e ele fica errado, porque ninguém
volta no painel depois de mudar a porta no `.env` — o projeto aparecia parado
com o servidor no ar, e o painel inteiro perdia a credibilidade.

Regra de atribuição, em ordem. A primeira que casa vence:

1. **Diretório de trabalho.** O processo que abriu a porta roda dentro do
   diretório do projeto. É a evidência mais forte que existe e cobre o caso
   normal: `uvicorn`, `npm run dev`, `flask run`.
2. **Linha de comando.** O caminho do projeto aparece nos argumentos. Pega o
   caso do processo lançado de outro diretório com o caminho no argumento.
3. **Runtime de container.** Quem abriu foi o Docker. A porta é real, mas o
   dono não dá para deduzir daqui, então ela é marcada e não atribuída — o
   painel de Docker do projeto é quem responde essa pergunta.
4. **Sem dono.** Alguém está usando a porta e não é nenhum projeto cadastrado.
   Continua valendo a pena mostrar: é exatamente o que explica um `up` que
   falha com "address already in use".

Nada aqui escreve no banco. Descoberta é observação, e observação não corrige
declaração sozinha — quem decide trocar o número é quem conhece o projeto
(mesma razão de a tela de Ports nunca reescrever o `.env`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.adapters.system.ports import ListeningPort, PortScanner, normalized
from app.core.cache import TTLCache

logger = logging.getLogger(__name__)

CACHE_KEY = "ports.observed"


@dataclass(frozen=True)
class ObservedPort:
    """Uma porta em escuta, já atribuída (ou não) a um projeto."""

    port: int
    pid: int | None = None
    process_name: str | None = None
    #: Projeto a quem a porta foi atribuída, quando foi possível deduzir.
    project_id: str | None = None
    project_name: str | None = None
    #: Como a atribuição foi feita: "cwd", "cmdline", "container" ou "unknown".
    matched_by: str = "unknown"

    @property
    def claimed(self) -> bool:
        return self.project_id is not None


@dataclass
class PortObservation:
    """O resultado inteiro de uma varredura, pronto para a API."""

    ports: list[ObservedPort] = field(default_factory=list)
    #: Falhou a varredura (sem privilégio, plataforma sem suporte). A UI mostra
    #: "não foi possível observar" em vez de "nada escutando", que é mentira.
    available: bool = True

    def by_port(self) -> dict[int, ObservedPort]:
        return {item.port: item for item in self.ports}

    def for_project(self, project_id: str) -> list[ObservedPort]:
        return [item for item in self.ports if item.project_id == project_id]


@dataclass(frozen=True)
class ProjectRef:
    """O mínimo que a atribuição precisa saber de um projeto."""

    id: str
    name: str
    path: str


class PortDiscoveryService:
    def __init__(self, scanner: PortScanner, cache: TTLCache) -> None:
        self.scanner = scanner
        self.cache = cache

    # --- varredura ---

    def observe(self, projects: list[ProjectRef]) -> PortObservation:
        """Varre e atribui. Chamado pelo poller, nunca no caminho da requisição."""
        try:
            escutando = self.scanner.scan()
        except Exception:  # noqa: BLE001 - descoberta nunca derruba o poller
            logger.exception("varredura de portas falhou")
            observacao = PortObservation(available=False)
            self.cache.set(CACHE_KEY, observacao)
            return observacao

        observacao = PortObservation(
            ports=[self._assign(porta, projects) for porta in escutando]
        )
        self.cache.set(CACHE_KEY, observacao)
        return observacao

    def last_known(self) -> PortObservation:
        """O que a última varredura viu. Vazio antes do primeiro ciclo."""
        entrada = self.cache.get_with_age(CACHE_KEY)
        if entrada is None:
            return PortObservation()
        observacao, _idade = entrada
        return observacao

    # --- atribuição ---

    def _assign(self, porta: ListeningPort, projects: list[ProjectRef]) -> ObservedPort:
        dono = self._match_by_cwd(porta, projects)
        if dono is not None:
            return self._observed(porta, dono, "cwd")

        dono = self._match_by_cmdline(porta, projects)
        if dono is not None:
            return self._observed(porta, dono, "cmdline")

        if porta.via_container_runtime:
            return self._observed(porta, None, "container")

        return self._observed(porta, None, "unknown")

    @staticmethod
    def _match_by_cwd(porta: ListeningPort, projects: list[ProjectRef]) -> ProjectRef | None:
        atual = normalized(porta.cwd)
        if atual is None:
            return None

        # Do caminho mais longo para o mais curto: com um projeto dentro de
        # outro, o de dentro é a resposta certa. Ordenar ao contrário faria o
        # monorepo pai engolir todos os filhos.
        for project in sorted(projects, key=lambda p: len(p.path), reverse=True):
            raiz = normalized(project.path)
            if raiz is None:
                continue
            if len(atual) >= len(raiz) and atual[: len(raiz)] == raiz:
                return project
        return None

    @staticmethod
    def _match_by_cmdline(porta: ListeningPort, projects: list[ProjectRef]) -> ProjectRef | None:
        if not porta.cmdline:
            return None

        # Comparação por texto, tolerante à barra: o mesmo caminho aparece com
        # `\` no argumento e `/` no cadastro o tempo todo no Windows.
        alvo = porta.cmdline.replace("\\", "/").lower()
        for project in sorted(projects, key=lambda p: len(p.path), reverse=True):
            agulha = project.path.replace("\\", "/").lower()
            if agulha and agulha in alvo:
                return project
        return None

    @staticmethod
    def _observed(
        porta: ListeningPort, project: ProjectRef | None, matched_by: str
    ) -> ObservedPort:
        return ObservedPort(
            port=porta.port,
            pid=porta.pid,
            process_name=porta.process_name,
            project_id=project.id if project else None,
            project_name=project.name if project else None,
            matched_by=matched_by,
        )


def refs_from_projects(projects) -> list[ProjectRef]:  # type: ignore[no-untyped-def]
    return [ProjectRef(id=p.id, name=p.name, path=p.path) for p in projects]
