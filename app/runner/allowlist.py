"""Allowlist de ações — defesa D2 do modelo de segurança (ADR-003).

O cliente envia um identificador de ação ("git.status"). A tradução para argv
está aqui, fixa no código. Nenhum valor vindo do cliente entra em posição de
flag; os únicos valores aceitos são tipados e validados pelos helpers abaixo.

Ação fora deste registro levanta `ActionNotAllowed`, que a camada HTTP traduz
em 403 e a auditoria grava como DENIED.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.core.errors import ActionNotAllowed, ValidationError

# --- validadores de valor ------------------------------------------------
# Todo valor do cliente que entra em argv passa por um destes.


def safe_int(value: object, *, minimum: int, maximum: int, name: str) -> str:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} precisa ser inteiro.") from exc
    if not minimum <= parsed <= maximum:
        raise ValidationError(f"{name} precisa estar entre {minimum} e {maximum}.")
    return str(parsed)


def safe_choice(value: object, *, allowed: Iterable[str], name: str) -> str:
    text = str(value)
    allowed_set = set(allowed)
    if text not in allowed_set:
        raise ValidationError(f"{name} inválido: {text!r}.")
    return text


def safe_token(value: object, *, name: str, max_length: int = 64) -> str:
    """Aceita apenas identificador simples e nunca algo que pareça flag."""
    text = str(value)
    if not text or len(text) > max_length:
        raise ValidationError(f"{name} tem tamanho inválido.")
    if text.startswith("-"):
        raise ValidationError(f"{name} não pode começar com '-'.")
    if not all(char.isalnum() or char in "._-" for char in text):
        raise ValidationError(f"{name} contém caractere não permitido.")
    return text


# --- registro de ações ---------------------------------------------------


@dataclass(frozen=True)
class ActionDefinition:
    """Uma ação executável e como ela vira argv."""

    label: str
    build: Callable[..., list[str]]
    timeout_key: str
    description: str


_REGISTRY: dict[str, ActionDefinition] = {}


def register(action: ActionDefinition) -> ActionDefinition:
    if action.label in _REGISTRY:
        raise RuntimeError(f"Ação duplicada no registro: {action.label}")
    _REGISTRY[action.label] = action
    return action


def get_action(label: str) -> ActionDefinition:
    action = _REGISTRY.get(label)
    if action is None:
        raise ActionNotAllowed(f"Ação não permitida: {label!r}")
    return action


def known_actions() -> list[str]:
    return sorted(_REGISTRY)


# --- ações da Fase 1 -----------------------------------------------------
# Fases seguintes adicionam git.*, docker.* e system.* aqui, e em nenhum outro
# lugar. Um teste garante que nenhuma ação destrutiva entre neste registro.

register(
    ActionDefinition(
        label="tool.version.git",
        build=lambda git_bin="git": [git_bin, "--version"],
        timeout_key="timeout_git",
        description="Verifica se o git está disponível no PATH.",
    )
)

register(
    ActionDefinition(
        label="tool.version.docker",
        build=lambda docker_bin="docker": [docker_bin, "--version"],
        timeout_key="timeout_docker_read",
        description="Verifica se o docker está disponível no PATH.",
    )
)

register(
    ActionDefinition(
        label="tool.version.code",
        build=lambda code_bin="code": [code_bin, "--version"],
        timeout_key="timeout_system_action",
        description="Verifica se o VS Code CLI está disponível no PATH.",
    )
)


# --- verificações de segurança do próprio registro -----------------------

FORBIDDEN_FRAGMENTS = (
    ("git", "reset"),
    ("git", "clean"),
    ("git", "checkout"),
    ("git", "commit"),
    ("git", "push"),
    ("docker", "system", "prune"),
    ("docker", "volume", "rm"),
)

FORBIDDEN_FLAGS = ("--force", "-f", "-v", "--volumes")


def assert_registry_is_safe() -> None:
    """Sanidade do registro. Chamado no startup e exercitado em teste.

    Percorre as ações com argumentos vazios sempre que possível e verifica que
    nenhuma produz comando destrutivo. Ação que exige parâmetro é ignorada
    aqui e coberta pelos testes específicos dela.
    """
    for label, action in _REGISTRY.items():
        try:
            argv = action.build()
        except TypeError:
            continue
        lowered = [part.lower() for part in argv]
        for fragment in FORBIDDEN_FRAGMENTS:
            if all(part in lowered for part in fragment):
                raise RuntimeError(f"Ação {label} produz comando proibido: {argv}")

        # `FORBIDDEN_FLAGS` estava declarado e nunca conferido: a barreira que
        # impede `down -v` de entrar no registro não existia de fato. As flags
        # são checadas por igualdade e não por substring — `-v` casaria com
        # `--verbose` e reprovaria ação legítima.
        for flag in FORBIDDEN_FLAGS:
            if flag in lowered:
                raise RuntimeError(f"Ação {label} usa flag proibida {flag!r}: {argv}")
