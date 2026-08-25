"""Ações de sistema operacional (FR-070 a FR-074).

Funde o `SystemService` e o `ProcessService` do prompt original: eram a mesma
coisa com nomes diferentes (divergência registrada em `docs/12-decisions.md`).
"""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from app.adapters.system.adapter import BaseOSAdapter
from app.core.errors import ProjectDirMissing, ValidationError
from app.models.project import ActivityStatus, Project
from app.runner.command_runner import CommandRunner
from app.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


class SystemActionService:
    def __init__(
        self,
        adapter: BaseOSAdapter,
        runner: CommandRunner,
        activity: ActivityService,
    ) -> None:
        self.adapter = adapter
        self.runner = runner
        self.activity = activity

    def _project_dir(self, project: Project) -> Path:
        project_dir = Path(project.path)
        if not project_dir.is_dir():
            raise ProjectDirMissing(f"O diretório {project.path} não existe mais.")
        return project_dir

    # --- abrir ferramentas ---

    def open_in_editor(self, project: Project) -> None:
        project_dir = self._project_dir(project)
        self._execute(project, self.adapter.open_in_editor(project_dir))
        # A janela só vem para frente com ajuda (D-46): `code` devolve 0 mesmo
        # quando reaproveita uma janela que ficou atrás do browser.
        self.adapter.focus_editor_window(project_dir)

    def open_editor_blank(self) -> None:
        """Abre o VS Code sem projeto, para o começo do dia.

        Não recebe caminho nenhum — nem do cliente, nem daqui. A rota só diz
        "abra o editor", e o argv sai inteiro do adapter (ADR-003). É por isso
        que este atalho não precisa passar pela validação de root: não há path
        para validar.
        """
        self._execute(None, self.adapter.open_editor_blank())

    def open_folder(self, project: Project) -> None:
        # O `explorer` do Windows devolve 1 mesmo quando abre a pasta, então
        # aqui o código de saída não é sinal de falha.
        self._execute(
            project, self.adapter.open_folder(self._project_dir(project)), ignore_exit_code=True
        )

    def open_terminal(self, project: Project) -> None:
        self._execute(project, self.adapter.open_terminal(self._project_dir(project)))

    def open_service_url(self, project: Project, service_key: str) -> str:
        """Abre a URL de um serviço **cadastrado**.

        Recebe a chave, nunca a URL (decisão D-13). Aceitar URL do cliente
        reabriria o vetor que o modelo de segurança fecha: a página poderia
        fazer o backend abrir qualquer endereço no browser do usuário.
        """
        service = next((s for s in project.services if s.key == service_key), None)
        if service is None:
            disponiveis = ", ".join(sorted(s.key for s in project.services)) or "nenhum"
            raise ValidationError(
                f"Serviço {service_key!r} não existe neste projeto. Disponíveis: {disponiveis}."
            )

        url = service.url or (f"http://{service.host}:{service.port}" if service.port else None)
        if not url:
            raise ValidationError(f"O serviço {service_key!r} não tem URL nem porta definida.")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or (parsed.hostname or "") not in {
            host.strip("[]") for host in LOCAL_HOSTS
        }:
            raise ValidationError("A URL do serviço precisa apontar para localhost.")

        # `webbrowser` usa a API do sistema e não passa por shell — diferente de
        # `start`, que é comando interno do shell do Windows (ADR-007).
        webbrowser.open(url)

        self.activity.record(
            action="system.browser",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            message=f"Abriu {url}",
        )
        return url

    # --- execução ---

    def _execute(self, project: Project | None, spec, ignore_exit_code: bool = False) -> None:  # type: ignore[no-untyped-def]
        result = self.runner.run(spec)

        sucesso = result.ok or (ignore_exit_code and not result.timed_out)
        self.activity.record(
            action=spec.label,
            status=ActivityStatus.SUCCESS if sucesso else ActivityStatus.FAILED,
            # `None` na ação global (abrir o editor vazio): a auditoria
            # registra o que houve sem inventar um projeto que não existe.
            project_id=project.id if project is not None else None,
            duration_ms=result.duration_ms,
            exit_code=result.exit_code,
            argv=spec.argv,
            message=None if sucesso else (result.stderr.strip()[:300] or "Falha ao abrir."),
        )

        if not sucesso:
            from app.core.errors import ToolNotFound

            raise ToolNotFound(result.stderr.strip()[:300] or "Não foi possível abrir.")
