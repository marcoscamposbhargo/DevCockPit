"""Validação de path — defesa D4 do modelo de segurança.

Ponto único. Todo path que chega do cliente passa por aqui antes de virar
argumento de comando, chave de banco ou alvo de ação de sistema operacional.

A comparação é feita por componente de diretório sobre paths já resolvidos.
`startswith` de string confundiria `C:/Users/User/Desktop-antigo` com
`C:/Users/User/Desktop`, que é exatamente o bug que essa camada existe para
não ter.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.errors import PathNotAllowed, PathNotFound

_CASE_INSENSITIVE = os.name == "nt"


def normalize_for_comparison(path: Path) -> tuple[str, ...]:
    """Reduz um path a componentes comparáveis na plataforma atual."""
    parts = path.parts
    if _CASE_INSENSITIVE:
        return tuple(part.lower() for part in parts)
    return parts


def is_within(candidate: Path, root: Path) -> bool:
    """Diz se `candidate` está contido em `root`, comparando por componente."""
    candidate_parts = normalize_for_comparison(candidate)
    root_parts = normalize_for_comparison(root)
    if len(candidate_parts) < len(root_parts):
        return False
    return candidate_parts[: len(root_parts)] == root_parts


def resolve_real(raw: str | Path) -> Path:
    """Canonicaliza um path, resolvendo symlinks e `..`.

    Não valida allowlist — quem faz isso é `validate_project_dir`.
    """
    return Path(raw).expanduser().resolve(strict=False)


def validate_project_dir(raw: str | Path, allowed_roots: list[Path]) -> Path:
    """Valida um diretório de projeto e devolve o path canonicalizado.

    Sequência (documentada em `docs/07-security-model.md`, defesa D4):

    1. rejeita path relativo
    2. resolve para caminho real, seguindo symlink
    3. exige que exista e seja diretório
    4. exige que esteja contido em pelo menos um root permitido

    O passo 4 acontece sobre o path **já resolvido**, o que é o que impede
    escape por symlink: um link dentro do root apontando para fora resolve para
    fora e é recusado.
    """
    original = Path(raw).expanduser()

    if not original.is_absolute():
        raise PathNotAllowed(f"O caminho precisa ser absoluto: {raw!r}")

    resolved = original.resolve(strict=False)

    if not resolved.exists():
        raise PathNotFound(f"Diretório não encontrado: {resolved}")

    if not resolved.is_dir():
        raise PathNotFound(f"O caminho não é um diretório: {resolved}")

    if not allowed_roots:
        raise PathNotAllowed(
            "Nenhum root permitido está configurado. "
            "Crie configs/roots.yml a partir de configs/roots.example.yml."
        )

    for root in allowed_roots:
        if is_within(resolved, root.resolve(strict=False)):
            return resolved

    raise PathNotAllowed(f"O diretório {resolved} não está em nenhum root permitido.")


def resolve_within_project(project_dir: Path, relative: str | Path) -> Path:
    """Resolve um path relativo dentro do projeto, garantindo que não escape.

    Usado para `compose_file` e afins, que são sempre relativos por decisão
    (ver `docs/05-data-model.md`).
    """
    candidate = Path(relative)
    if candidate.is_absolute():
        raise PathNotAllowed(f"O caminho precisa ser relativo ao projeto: {relative!r}")

    resolved = (project_dir / candidate).resolve(strict=False)
    if not is_within(resolved, project_dir.resolve(strict=False)):
        raise PathNotAllowed(f"O caminho {relative!r} escapa do diretório do projeto.")
    return resolved
