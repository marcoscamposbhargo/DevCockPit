"""Hierarquia de erros de domínio e o mapeamento para HTTP.

A camada HTTP não inventa status: cada erro de domínio já carrega o seu.
Ver a tabela em `docs/06-api-specification.md`.
"""

from __future__ import annotations


class DomainError(Exception):
    """Erro previsto, com código estável e status HTTP associado."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    default_message: str = "Erro interno."

    def __init__(self, message: str | None = None, **context: object) -> None:
        self.message = message or self.default_message
        self.context = context
        super().__init__(self.message)


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    status_code = 422
    default_message = "Dados inválidos."


class ProjectNotFound(DomainError):
    code = "PROJECT_NOT_FOUND"
    status_code = 404
    default_message = "Projeto não encontrado."


class ProjectAlreadyExists(DomainError):
    code = "PROJECT_ALREADY_EXISTS"
    status_code = 409
    default_message = "Já existe um projeto cadastrado para esse diretório."


class PathNotFound(DomainError):
    code = "PATH_NOT_FOUND"
    status_code = 400
    default_message = "Diretório não encontrado."


class PathNotAllowed(DomainError):
    code = "PATH_NOT_ALLOWED"
    status_code = 403
    default_message = (
        "O diretório não está em um root permitido. "
        "Ajuste configs/roots.yml se quiser incluí-lo."
    )


class ProjectDirMissing(DomainError):
    code = "PROJECT_DIR_MISSING"
    status_code = 409
    default_message = "O diretório do projeto não existe mais."


class NotAGitRepo(DomainError):
    code = "NOT_A_GIT_REPO"
    status_code = 409
    default_message = "O diretório não é um repositório Git."


class DockerUnavailable(DomainError):
    code = "DOCKER_UNAVAILABLE"
    status_code = 503
    default_message = "O Docker não está respondendo."


class NoComposeFile(DomainError):
    code = "NO_COMPOSE_FILE"
    status_code = 409
    default_message = "O projeto não tem arquivo Compose."


class OperationInProgress(DomainError):
    code = "OPERATION_IN_PROGRESS"
    status_code = 409
    default_message = "Já existe uma operação em andamento para este projeto."


class ToolNotFound(DomainError):
    code = "TOOL_NOT_FOUND"
    status_code = 503
    default_message = "Ferramenta externa não encontrada no PATH."


class ActionNotAllowed(DomainError):
    """Ação fora da allowlist. Gera registro DENIED na auditoria."""

    code = "ACTION_NOT_ALLOWED"
    status_code = 403
    default_message = "Ação não permitida."


class CommandTimeout(DomainError):
    code = "COMMAND_TIMEOUT"
    status_code = 504
    default_message = "O comando excedeu o tempo limite."
