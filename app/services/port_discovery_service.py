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
3. **Runtime de container, com a porta declarada por um único projeto.** O
   `cwd` do Docker aponta para a instalação dele, então as duas regras acima
   nunca casam com porta publicada por container. Sobra o número: se um único
   projeto declara aquela porta, foi o Compose dele que a publicou. Declarada
   por dois, ninguém é atribuído — isso é o conflito que a tela já aponta, e
   escolher um dos dois seria inventar.
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
from app.core.errors import ActionNotAllowed, ValidationError
from app.runner.background import is_alive, stop_background

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
    def strong_evidence(self) -> bool:
        """A atribuição é prova, e não palpite.

        `cwd` e `cmdline` provam: o processo roda dentro do projeto. `container`
        infere pelo número declarado, e inferência erra — o caso concreto foi a
        porta 8000 de um container da PLATAFORMA sendo atribuída ao SmartDash,
        que declarava 8000 e estava com tudo parado. A tela dizia "SmartDash
        Backend no ar" apontando para o servidor de outro projeto.

        Quem afirma "está no ar" precisa de prova. Quem só mostra "ocupada por
        alguém" pode se contentar com o palpite, porque não está afirmando dono.
        """
        return self.matched_by in ("cwd", "cmdline")

    #: Diretório de trabalho do processo, quando foi possível ler. É o que
    #: identifica o processo para um humano — "node.exe" não diz nada, "node.exe
    #: rodando em Projetos/AI Procedures" diz tudo.
    cwd: str | None = None
    #: Processo de desenvolvimento rodando dentro de um root permitido e que
    #: **nenhum projeto cadastrado reivindica**. É o servidor que sobreviveu à
    #: remoção do projeto, ou que foi subido antes de o painel existir.
    #:
    #: Só isto é oferecido para encerrar. A regra é a mesma defesa D4 que limita
    #: onde um projeto pode ser cadastrado: processo fora dos roots permitidos
    #: nunca é tocado, o que mantém `svchost`, Docker Desktop e o resto da
    #: máquina fora de alcance por construção.
    orphan: bool = False

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
    #: Portas que o projeto declara. Usadas só como última evidência, para
    #: porta publicada por container — onde o diretório de trabalho aponta para
    #: a instalação do Docker e não diz nada sobre o dono.
    declared_ports: tuple[int, ...] = ()


class PortDiscoveryService:
    def __init__(
        self,
        scanner: PortScanner,
        cache: TTLCache,
        allowed_roots: list | None = None,
    ) -> None:
        self.scanner = scanner
        self.cache = cache
        #: Limita o que pode ser marcado como órfão — e, por consequência, o que
        #: a tela oferece encerrar. Sem roots, nada é órfão: é o padrão seguro.
        self.allowed_roots = allowed_roots or []

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

        dono_por_porta = self._sole_declarers(projects)
        observacao = PortObservation(
            ports=[self._assign(porta, projects, dono_por_porta) for porta in escutando]
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

    # --- encerrar órfão ---

    def stop_orphan(self, pid: int) -> ObservedPort:
        """Encerra um processo de desenvolvimento largado. Devolve a porta dele.

        **O PID vem do cliente**, e é o único lugar do painel onde um valor do
        cliente participa de uma operação destrutiva. Por isso ele não é
        obedecido: serve para *procurar* na última observação, e quem decide é
        o que o servidor mesmo classificou.

        Duas guardas, as duas aqui e não na tela:

        1. o PID precisa estar na última varredura **marcado como órfão** — o
           que significa processo dentro de um root permitido e sem projeto que
           o reivindique (defesa D4, reusada);
        2. o processo precisa continuar vivo, ou já se chegou onde se queria.

        PID inventado, ou apontando para `svchost`, para o Docker Desktop ou
        para qualquer coisa fora dos roots, não passa da primeira.

        A nota de `app/runner/process.py` é a razão deste cuidado: nunca se
        localiza processo por porta para matar. Aqui se encerra um PID que o
        próprio painel observou e classificou.
        """
        observada = next(
            (porta for porta in self.last_known().ports if porta.pid == pid),
            None,
        )

        if observada is None:
            raise ValidationError(
                f"O processo {pid} não está na última varredura de portas. "
                "Recarregue a tela e tente de novo."
            )

        if not observada.orphan:
            raise ActionNotAllowed(
                f"O processo {pid} não é um servidor de desenvolvimento largado. "
                "O painel só encerra processos que rodam dentro de um root "
                "permitido e que nenhum projeto cadastrado reivindica."
            )

        # Morreu entre a varredura e o clique: é o resultado desejado.
        if not is_alive(pid):
            return observada

        if not stop_background(pid):
            raise ValidationError(
                f"O processo {pid} não respondeu ao pedido de encerramento. "
                "Pode ser preciso encerrá-lo pelo Gerenciador de Tarefas."
            )

        return observada

    # --- atribuição ---

    def _assign(
        self,
        porta: ListeningPort,
        projects: list[ProjectRef],
        dono_por_porta: dict[int, ProjectRef],
    ) -> ObservedPort:
        dono = self._match_by_cwd(porta, projects)
        if dono is not None:
            return self._observed(porta, dono, "cwd")

        dono = self._match_by_cmdline(porta, projects)
        if dono is not None:
            return self._observed(porta, dono, "cmdline")

        if porta.via_container_runtime:  # noqa: SIM102 - a ordem das regras é o contrato
            # O `cwd` do Docker aponta para a instalação dele, então as duas
            # regras acima nunca casam com uma porta publicada por container.
            # Sobra o número: se **um único** projeto declara aquela porta, foi
            # o Compose dele que a publicou.
            #
            # Sem isto, o banco em container de um projeto aparecia como "sem
            # dono" e o serviço declarado virava divergência — um alarme falso
            # justamente na configuração que o painel recomenda.
            declarado_por = dono_por_porta.get(porta.port)
            return self._observed(porta, declarado_por, "container")

        return self._observed(porta, None, "unknown", orphan=self._is_orphan(porta))

    def _is_orphan(self, porta: ListeningPort) -> bool:
        """Processo de desenvolvimento largado, dentro de um root permitido.

        Duas condições, e as duas são necessárias:

        1. **Dentro de um root permitido.** É a mesma defesa D4 que limita onde
           um projeto pode ser cadastrado, reusada para limitar o que pode ser
           encerrado. `svchost`, Docker Desktop e o navegador ficam fora de
           alcance por construção, e não por uma lista de exceções que alguém
           precisaria manter.
        2. **Nenhum projeto o reivindica.** Chegar até aqui já significa que as
           regras de atribuição falharam — o processo roda numa pasta que não é
           de projeto cadastrado nenhum.

        O caso que isto pega: subir o servidor de um projeto, remover o projeto
        do painel, e o processo continuar de pé segurando a porta sem nenhum
        caminho de volta pela interface.
        """
        if not self.allowed_roots or porta.cwd is None:
            return False

        atual = normalized(porta.cwd)
        if atual is None:
            return False

        for raiz in self.allowed_roots:
            comparavel = normalized(str(raiz))
            if comparavel is None:
                continue
            if len(atual) >= len(comparavel) and atual[: len(comparavel)] == comparavel:
                return True
        return False

    @staticmethod
    def _sole_declarers(projects: list[ProjectRef]) -> dict[int, ProjectRef]:
        """Porta -> projeto, só quando **um** projeto declara aquela porta.

        Porta disputada por dois projetos não identifica ninguém: é o conflito
        que a tela de Ports já aponta, e escolher um dos dois aqui seria
        inventar. Evidência ambígua não vira atribuição.
        """
        vistos: dict[int, ProjectRef | None] = {}
        for project in projects:
            for porta in project.declared_ports:
                vistos[porta] = None if porta in vistos else project
        return {porta: dono for porta, dono in vistos.items() if dono is not None}

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
        porta: ListeningPort,
        project: ProjectRef | None,
        matched_by: str,
        *,
        orphan: bool = False,
    ) -> ObservedPort:
        return ObservedPort(
            port=porta.port,
            pid=porta.pid,
            process_name=porta.process_name,
            project_id=project.id if project else None,
            project_name=project.name if project else None,
            matched_by=matched_by,
            cwd=porta.cwd,
            orphan=orphan,
        )


def refs_from_projects(projects) -> list[ProjectRef]:  # type: ignore[no-untyped-def]
    return [
        ProjectRef(
            id=p.id,
            name=p.name,
            path=p.path,
            declared_ports=tuple(s.port for s in p.services if s.port),
        )
        for p in projects
    ]
