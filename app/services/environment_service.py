"""Subir e baixar o ambiente de um projeto, na ordem certa.

O modelo de uso que isto atende: **o Docker sobe o ambiente, o servidor de
desenvolvimento sobe em cima dele.** Banco, Redis e afins vivem em container; a
aplicação roda nativa, com hot reload, falando com esses containers. Um clique
tem que dar conta dos dois, na ordem, porque a ordem inversa quebra: aplicação
que sobe antes do banco morre no primeiro `connect` ou entra em laço de
retentativa que ninguém quer ler.

## Quem é aplicação e quem é ambiente

O bloco `run:` do manifesto é o que decide. Havendo `run:`, a aplicação é o
comando dele e **o Compose inteiro é ambiente**. Não havendo, a aplicação é o
próprio Compose — é o caso de um projeto cuja stack inteira roda em container.

Essa distinção é o que dá sentido ao "Desligar". Ver `down`.

## A espera

Depois do `compose up -d`, esperar é obrigatório e esperar um tempo fixo é
chute. Um Postgres com um banco vazio abre em dois segundos; com trinta giga de
dados, em vinte. O que se espera aqui são as **portas dos serviços declarados
que não são a aplicação** — as dependências — com teto.

Serviço declarado sem porta não entra na espera: não há o que perguntar.

## Subir é idempotente

`compose up -d` com tudo já de pé retorna rápido e não mexe em nada. Por isso a
etapa do Docker roda sempre, sem perguntar se é necessária — o que corresponde
a "pega os ambientes já construídos e continua o processo".
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.adapters.docker.adapter import DockerAdapter
from app.core.errors import DomainError
from app.detection.detectors.docker_stack import find_compose_file
from app.jobs.job import Job
from app.models.project import Project
from app.runner.async_runner import AsyncCommandRunner
from app.services.activity_service import ActivityService
from app.services.dev_server_service import DevServerService
from app.services.health_service import HealthService, ServiceTarget

logger = logging.getLogger(__name__)

#: Teto da espera pelas dependências. Passado disso a aplicação sobe assim
#: mesmo, com aviso: travar o clique indefinidamente é pior que subir e deixar
#: a aplicação reclamar, que é o que ela faria no terminal de qualquer forma.
DEPENDENCY_TIMEOUT_S = 30.0
DEPENDENCY_POLL_S = 1.0

#: Limite de bytes da saída acumulada no job desta orquestração.
OUTPUT_LIMIT = 512 * 1024


class NothingToStart(DomainError):
    code = "NOTHING_TO_START"
    status_code = 409
    default_message = (
        "Este projeto não tem Compose nem comando de execução. "
        "Declare o bloco `run:` no devcockpit.yml."
    )


@dataclass
class EnvironmentPlan:
    """O que "Ligar" faria neste projeto, antes de fazer."""

    compose_file: str | None = None
    app_command: str = ""
    app_source: str = ""
    #: Chaves dos serviços declarados que a subida espera antes do app.
    dependencies: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.dependencies is None:
            self.dependencies = []

    @property
    def has_app(self) -> bool:
        return bool(self.app_command)

    @property
    def has_docker(self) -> bool:
        return self.compose_file is not None


class EnvironmentService:
    def __init__(
        self,
        session_factory: sessionmaker,
        adapter: DockerAdapter,
        health: HealthService,
        logs_dir,  # type: ignore[no-untyped-def]
        runner: AsyncCommandRunner | None = None,
        compose_timeout_s: float = 300.0,
        discovery=None,  # type: ignore[no-untyped-def]
    ) -> None:
        # Sessão própria por operação: o job roda depois que a requisição
        # acabou, e a sessão daquela requisição já está fechada.
        self.session_factory = session_factory
        self.adapter = adapter
        self.health = health
        self.logs_dir = logs_dir
        self.runner = runner or AsyncCommandRunner()
        self.compose_timeout_s = compose_timeout_s
        #: Só para explicar falha de porta ocupada. Opcional: sem ela a
        #: mensagem continua correta, só menos útil.
        self.discovery = discovery

    # --- leitura ---

    def plan(self, project: Project, servers: DevServerService) -> EnvironmentPlan:
        plano_app = servers.plan(project)
        chave_app = self._app_service_key(project, servers)

        dependencias = [
            service.key
            for service in project.services
            if service.port and service.key != chave_app
        ]

        return EnvironmentPlan(
            compose_file=self._compose_file(project),
            app_command=plano_app.display if plano_app else "",
            app_source=plano_app.source if plano_app else "",
            dependencies=dependencias,
        )

    @staticmethod
    def _compose_file(project: Project) -> str | None:
        """O arquivo Compose do projeto, ou `None` se não houver.

        Lê o disco direto em vez de passar pelo `DockerService`: aqui não se
        quer cache nenhum. O cache de lá guarda o **status** de uma consulta
        anterior, e no momento de subir o ambiente o que interessa é o que está
        no disco agora.
        """
        project_dir = Path(project.path)
        if not project_dir.is_dir():
            return None
        encontrado = find_compose_file(project_dir)
        return encontrado.name if encontrado is not None else None

    @staticmethod
    def _app_service_key(project: Project, servers: DevServerService) -> str | None:
        """Qual serviço declarado a aplicação fornece.

        O manifesto pode dizer em `run.service`. Sem isso, vale o mesmo serviço
        de onde a porta do comando saiu — assim a espera nunca inclui a porta do
        próprio app, que por definição ainda não subiu.
        """
        plano = servers.plan(project)
        if plano is None:
            return None
        if plano.service:
            return plano.service
        for service in project.services:
            if service.port:
                return service.key
        return None

    # --- subida ---

    async def up(self, job: Job, project_id: str) -> str:
        """Sobe o ambiente e depois a aplicação. Roda dentro de um job."""
        session = self.session_factory()
        try:
            servers = DevServerService(session=session, logs_dir=self.logs_dir)
            project = session.get(Project, project_id)
            if project is None:
                raise NothingToStart(f"Projeto {project_id!r} não encontrado.")

            plano = self.plan(project, servers)
            if not plano.has_docker and not plano.has_app:
                raise NothingToStart(
                    f"{project.name} não tem Compose nem comando de execução. "
                    "Declare o bloco `run:` no devcockpit.yml do projeto."
                )

            if plano.has_docker:
                await self._compose_up(job, project, plano)

            if plano.has_app:
                # Já estar no ar é o estado desejado, não erro. Subir é
                # idempotente por decisão: o `compose up -d` acima já era, e
                # tratar "a aplicação já está rodando" como falha marcaria o
                # job inteiro de vermelho por causa de um resultado que é
                # exatamente o que se pediu.
                if servers.status(project).running:
                    job.append(
                        "A aplicação já estava no ar; nada a subir.", limit=OUTPUT_LIMIT
                    )
                    return f"Ambiente de {project.name} no ar; a aplicação já rodava."

                if plano.dependencies:
                    await self._wait_dependencies(job, project, plano)
                await asyncio.to_thread(self._start_app, session, project_id)
                session.commit()
                job.append(f"Aplicação no ar: {plano.app_command}", limit=OUTPUT_LIMIT)
                return f"Ambiente e aplicação de {project.name} no ar."

            return f"Ambiente de {project.name} no ar."
        finally:
            session.close()

    async def _compose_up(self, job: Job, project: Project, plano: EnvironmentPlan) -> None:
        job.append(f"Subindo os containers ({plano.compose_file})…", limit=OUTPUT_LIMIT)

        spec = self.adapter.action_spec(
            Path(project.path),
            plano.compose_file,
            "up",
            [],
            timeout_s=self.compose_timeout_s,
        )
        resultado = await self.runner.run(
            spec,
            on_line=lambda _canal, linha: job.append(linha, limit=OUTPUT_LIMIT),
            cancel_event=job.cancel_event,
        )
        if not resultado.ok:
            raise DomainError(self._explain_failure(resultado, job))
        job.append("Containers no ar.", limit=OUTPUT_LIMIT)

    def _explain_failure(self, resultado, job: Job) -> str:  # type: ignore[no-untyped-def]
        """Traduz a falha do Compose no que dá para fazer a respeito.

        "port is already allocated" é a falha mais comum e a mais inútil como
        vem: o Docker diz que a porta está ocupada e não diz por quem. Quem lê
        precisa abrir um terminal e caçar — que é exatamente o trabalho que a
        descoberta de porta já fez no último ciclo do poller.
        """
        saida = f"{resultado.stdout}\n{resultado.stderr}"
        porta = _porta_ocupada(saida)

        if porta is None:
            return (
                f"O Compose falhou ao subir ({resultado.exit_code}). "
                "A saída acima tem o motivo."
            )

        culpado = self._quem_ocupa(porta)
        job.append(f"A porta {porta} já está ocupada por {culpado}.", limit=OUTPUT_LIMIT)
        return (
            f"A porta {porta} já está ocupada por {culpado}. "
            "Pare quem está com ela, ou troque a porta deste projeto."
        )

    def _quem_ocupa(self, porta: int) -> str:
        """Descrição de quem está com a porta, do mais informativo ao menos."""
        if self.discovery is None:
            return "outro processo"

        observada = self.discovery.last_known().by_port().get(porta)
        if observada is None:
            return "outro processo (não identificado na última varredura)"

        if observada.project_name:
            return f"{observada.project_name} ({observada.process_name or 'processo'})"
        if observada.matched_by == "container":
            return f"um container ({observada.process_name or 'Docker'})"
        return observada.process_name or "outro processo"

    async def _wait_dependencies(self, job: Job, project: Project, plano: EnvironmentPlan) -> None:
        """Espera as portas das dependências responderem, com teto.

        Esperar um tempo fixo seria chute: um Postgres com banco vazio abre em
        dois segundos, com trinta giga de dados em vinte. Aqui a espera acaba
        quando o serviço responde, e não quando um número arbitrário passa.
        """
        alvos = [
            ServiceTarget(
                project_id=project.id,
                key=service.key,
                label=service.label,
                host=service.host or "localhost",
                port=service.port,
                url=service.url,
                health_url=service.health_url,
                health_kind=service.health_kind,
            )
            for service in project.services
            if service.key in set(plano.dependencies) and service.port
        ]
        if not alvos:
            return

        nomes = ", ".join(alvo.label for alvo in alvos)
        job.append(f"Esperando as dependências responderem: {nomes}…", limit=OUTPUT_LIMIT)

        limite = asyncio.get_running_loop().time() + DEPENDENCY_TIMEOUT_S
        pendentes = {alvo.key: alvo for alvo in alvos}

        while pendentes:
            resultados = await self.health.check_many(list(pendentes.values()))
            for resultado in resultados:
                if resultado.state.value == "ONLINE":
                    alvo = pendentes.pop(resultado.key, None)
                    if alvo is not None:
                        job.append(f"  {alvo.label} respondeu.", limit=OUTPUT_LIMIT)

            if not pendentes:
                job.append("Dependências prontas.", limit=OUTPUT_LIMIT)
                return

            if asyncio.get_running_loop().time() >= limite:
                faltando = ", ".join(alvo.label for alvo in pendentes.values())
                # Subir assim mesmo, com aviso: travar o clique para sempre é
                # pior que deixar a aplicação reclamar, que é o que ela faria
                # no terminal de qualquer jeito.
                job.append(
                    f"Sem resposta de {faltando} em {DEPENDENCY_TIMEOUT_S:.0f}s. "
                    "Subindo a aplicação assim mesmo.",
                    limit=OUTPUT_LIMIT,
                )
                return

            await asyncio.sleep(DEPENDENCY_POLL_S)

    def _start_app(self, session, project_id: str) -> None:  # type: ignore[no-untyped-def]
        servers = DevServerService(
            session=session,
            logs_dir=self.logs_dir,
            activity=ActivityService(session),
        )
        project = session.get(Project, project_id)
        servers.start(project)

    # --- descida ---

    def down(self, project: Project, servers: DevServerService, *, include_docker: bool) -> str:
        """Para a **camada de aplicação**. O ambiente só cai se for pedido.

        A assimetria é deliberada e vem do uso real: o Docker segura banco e
        fila, que são caros de subir e não mudam entre uma execução e outra da
        aplicação. Derrubá-los a cada parada do backend transformaria um ciclo
        de dois segundos num de trinta.

        Quando o projeto **não tem** aplicação separada, a aplicação é o próprio
        Compose e é ele que para — senão "Desligar" não faria nada, que é a pior
        resposta possível a um clique.
        """
        plano_app = servers.plan(project)

        if plano_app is None and not include_docker:
            # Sem aplicação separada, o Compose é a aplicação.
            return "docker"

        servers.stop(project)
        return "docker" if include_docker else "app"


#: As duas formas com que o Docker relata porta ocupada, conforme a versão e a
#: camada que falhou:
#:
#:   Bind for 0.0.0.0:5432 failed: port is already allocated
#:   listen tcp 0.0.0.0:3000: bind: address already in use
#:
#: Em ambas o número vem depois do último `:` do endereço, mas numa ele antecede
#: a frase e na outra a sucede — daí dois padrões em vez de um espertinho.
_FORMAS_PORTA_OCUPADA = (
    re.compile(r"bind for\s+\S*?:(\d{1,5})\s+failed:\s*port is already allocated", re.I),
    re.compile(r"\S*?:(\d{1,5}):\s*bind:\s*address already in use", re.I),
)


def _porta_ocupada(saida: str) -> int | None:
    """Extrai a porta de uma falha de "porta já ocupada", se for esse o caso.

    Devolve `None` para qualquer outra falha: quem chama cai na mensagem
    genérica, que continua correta. Adivinhar porta de uma saída que não fala
    de porta seria inventar um culpado.
    """
    for padrao in _FORMAS_PORTA_OCUPADA:
        achado = padrao.search(saida)
        if achado is None:
            continue
        numero = int(achado.group(1))
        if 1 <= numero <= 65535:
            return numero
    return None
