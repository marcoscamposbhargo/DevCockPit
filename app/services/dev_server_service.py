"""Subir e parar o servidor de desenvolvimento de um projeto pelo painel.

O que isto resolve: até aqui, "ligar" só existia para projeto com Compose.
Projeto de `npm run dev` ou `uvicorn` — que é a maioria — exigia abrir um
terminal, lembrar o comando e digitá-lo, toda vez. O painel sabia dizer que o
projeto estava parado e não sabia fazer nada a respeito.

Três decisões que sustentam o resto:

**O processo sobrevive ao painel.** Reiniciar o DevCockpit não pode derrubar o
servidor de ninguém, então o processo nasce em grupo próprio e o PID vai para o
banco. Sobreviver só não vira órfão porque, na volta, o painel reencontra o
processo pelo PID gravado — e a descoberta de porta confirma pela porta em
escuta.

**PID sozinho não basta para parar.** O sistema recicla identificador de
processo. Antes de encerrar, o comando gravado é conferido contra o que o
processo de fato está executando; divergiu, a linha é descartada em vez de
matar processo de terceiro.

**Saída vai para arquivo.** Um servidor ligado o dia inteiro estoura qualquer
buffer em memória, e o log precisa continuar legível depois de reiniciar o
painel — que é justamente quando alguém vai querer ler por que caiu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, ProjectDirMissing, ValidationError
from app.core.paths import resolve_within_project
from app.models.base import utcnow
from app.models.project import ActivityStatus, DevServer, Project
from app.runner.background import is_alive, start_background, stop_background, tail_log
from app.services.activity_service import ActivityService
from app.services.run_plan import RunPlan, resolve_run_plan

logger = logging.getLogger(__name__)


class NoRunCommand(DomainError):
    code = "NO_RUN_COMMAND"
    status_code = 409
    default_message = (
        "Não foi possível descobrir como subir este projeto. "
        "Declare o bloco `run:` no devcockpit.yml."
    )


class ServerAlreadyRunning(DomainError):
    code = "SERVER_ALREADY_RUNNING"
    status_code = 409
    default_message = "Este projeto já tem um servidor de desenvolvimento no ar."


@dataclass(frozen=True)
class DevServerState:
    running: bool
    pid: int | None = None
    command: str = ""
    source: str = ""
    evidence: str = ""
    started_at: datetime | None = None
    log_file: str | None = None
    #: Existe um plano de execução, mesmo que nada esteja rodando. É o que
    #: decide se a UI oferece o botão ou explica por que não pode.
    can_start: bool = False


class DevServerService:
    def __init__(
        self,
        session: Session,
        logs_dir: Path,
        activity: ActivityService | None = None,
    ) -> None:
        self.session = session
        self.logs_dir = logs_dir
        self.activity = activity or ActivityService(session)

    # --- consulta ---

    def _project_dir(self, project: Project) -> Path:
        project_dir = Path(project.path)
        if not project_dir.is_dir():
            raise ProjectDirMissing(f"O diretório {project.path} não existe mais.")
        return project_dir

    def _record(self, project: Project) -> DevServer | None:
        return self.session.execute(
            select(DevServer).where(DevServer.project_id == project.id)
        ).scalar_one_or_none()

    def _declared_port(self, project: Project) -> int | None:
        """A porta que o projeto declara, para passar ao comando quando cabe.

        Um `uvicorn` sem `--port` sobe em 8000 e o painel verifica outra coisa.
        Passar o número que já está no cadastro é o que faz o botão e a coluna
        de estado concordarem no primeiro clique.
        """
        for service in project.services:
            if service.port:
                return service.port
        return None

    def plan(self, project: Project) -> RunPlan | None:
        """O que rodaria se alguém clicasse em ligar. `None` quando não dá para saber."""
        try:
            project_dir = self._project_dir(project)
        except ProjectDirMissing:
            return None
        try:
            return resolve_run_plan(project_dir, port=self._declared_port(project))
        except ValidationError:
            # Manifesto com comando recusado: a tela não oferece o botão, e o
            # motivo aparece quando a pessoa tenta ligar.
            return None

    def status(self, project: Project) -> DevServerState:
        registro = self._reconcile(project)
        plano = self.plan(project)

        if registro is None:
            return DevServerState(
                running=False,
                command=plano.display if plano else "",
                source=plano.source if plano else "",
                evidence=plano.evidence if plano else "",
                can_start=plano is not None,
            )

        return DevServerState(
            running=True,
            pid=registro.pid,
            command=registro.command,
            source=registro.source,
            evidence=plano.evidence if plano else "",
            started_at=registro.started_at,
            log_file=registro.log_file,
            can_start=plano is not None,
        )

    def _reconcile(self, project: Project) -> DevServer | None:
        """Descarta o registro quando o processo já não existe.

        Roda em toda consulta porque o processo morre por fora o tempo todo —
        Ctrl+C no console dele, erro de compilação, reinício da máquina. Um
        registro que sobrevive ao processo faz o painel oferecer "Parar" para
        algo que já não está lá.
        """
        registro = self._record(project)
        if registro is None:
            return None

        if not is_alive(registro.pid):
            self.session.delete(registro)
            self.session.flush()
            return None

        return registro

    # --- ações ---

    def start(self, project: Project) -> DevServerState:
        if self._reconcile(project) is not None:
            raise ServerAlreadyRunning(
                f"{project.name} já tem um servidor no ar. Pare antes de subir de novo."
            )

        project_dir = self._project_dir(project)
        plano = resolve_run_plan(project_dir, port=self._declared_port(project))
        if plano is None:
            raise NoRunCommand(
                f"Não foi possível descobrir como subir {project.name}. "
                "Declare o bloco `run:` no devcockpit.yml do projeto — "
                'por exemplo: run:\\n  cmd: ["npm", "run", "dev"]'
            )

        # `cwd` do plano é relativo e já passou por validação na leitura; aqui
        # ele é resolvido de novo porque este é o ponto onde vira diretório de
        # execução de verdade, e é aqui que a garantia precisa valer.
        cwd = resolve_within_project(project_dir, plano.cwd) if plano.cwd else project_dir

        log_file = self.logs_dir / "servers" / f"{project.id}.log"

        try:
            iniciado = start_background(argv=plano.argv, cwd=cwd, log_file=log_file)
        except (OSError, ValueError) as exc:
            self.activity.record(
                action="server.start",
                status=ActivityStatus.FAILED,
                project_id=project.id,
                argv=plano.argv,
                message=str(exc)[:300],
            )
            raise ValidationError(
                f"Não foi possível iniciar {plano.argv[0]!r}: {exc}. "
                "Confira se o programa está no PATH."
            ) from exc

        self.session.add(
            DevServer(
                project_id=project.id,
                pid=iniciado.pid,
                command=plano.display,
                cwd=str(cwd),
                log_file=iniciado.log_file,
                source=plano.source,
                started_at=utcnow(),
            )
        )
        self.session.flush()

        self.activity.record(
            action="server.start",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            argv=plano.argv,
            message=f"pid {iniciado.pid} · {plano.display}",
        )

        return self.status(project)

    def stop(self, project: Project) -> DevServerState:
        registro = self._reconcile(project)
        if registro is None:
            # Parar o que já não está rodando é o resultado desejado, não erro.
            return self.status(project)

        pid = registro.pid
        encerrado = stop_background(pid)

        # A linha sai mesmo se o encerramento falhou: mantê-la faria o painel
        # oferecer "Parar" para sempre num processo que não obedece. O aviso do
        # que aconteceu vai para a auditoria.
        self.session.delete(registro)
        self.session.flush()

        self.activity.record(
            action="server.stop",
            status=ActivityStatus.SUCCESS if encerrado else ActivityStatus.FAILED,
            project_id=project.id,
            message=f"pid {pid}" if encerrado else f"pid {pid} não encerrou",
        )

        if not encerrado:
            raise ValidationError(
                f"O processo {pid} não respondeu ao pedido de encerramento. "
                "Pode ser preciso encerrá-lo pelo Gerenciador de Tarefas."
            )

        return self.status(project)

    def logs(self, project: Project, lines: int = 200) -> list[str]:
        registro = self._record(project)
        arquivo = (
            Path(registro.log_file)
            if registro is not None
            else self.logs_dir / "servers" / f"{project.id}.log"
        )
        # Lê o arquivo mesmo com o servidor parado: depois de uma queda, o log é
        # a única coisa que explica o que houve.
        return tail_log(arquivo, lines=lines)
