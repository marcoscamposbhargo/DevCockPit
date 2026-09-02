"""Encerramento de árvore de processos.

Mora em `app/runner/` porque é aqui que `subprocess` pode ser importado
(ADR-003). O `JobManager` delega para cá em vez de matar processo por conta
própria.

Por que árvore e não só o filho: `docker compose up` cria uma constelação de
processos, e matar apenas o pai deixa órfão rodando — que continua segurando
porta e volume. No Windows não existe `killpg`, então o caminho é `taskkill /T`.

Nota específica desta máquina: nunca localizar processo por porta para matar.
Isso derruba o Docker Desktop junto. Só se mata PID conhecido, que este módulo
recebeu de quem o criou.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess  # noqa: S404 - ponto único de execução, ver ADR-003

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

# Criar o filho em grupo próprio é o que permite encerrar a árvore inteira.
# `CREATE_NO_WINDOW` impede que o filho aloque um console visível.
CREATION_FLAGS = (
    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    if _IS_WINDOWS
    else 0
)


def kill_tree(pid: int, *, timeout_s: float = 5.0) -> bool:
    """Encerra o processo e todos os seus descendentes.

    Devolve True quando o encerramento foi solicitado com sucesso. Não levanta
    exceção: um processo que já morreu não é erro.
    """
    if _IS_WINDOWS:
        return _kill_tree_windows(pid, timeout_s=timeout_s)
    return _kill_tree_posix(pid)


def _kill_tree_windows(pid: int, *, timeout_s: float) -> bool:
    try:
        completed = subprocess.run(  # noqa: S603 - argv fixo, pid é inteiro
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning(
            "falha ao encerrar árvore de processos",
            extra={"extra_fields": {"pid": pid, "error": str(exc)}},
        )
        return False

    # 128 = processo não encontrado; já morreu, o que é o resultado desejado.
    ok = completed.returncode in (0, 128)
    if not ok:
        logger.warning(
            "taskkill devolveu código inesperado",
            extra={
                "extra_fields": {
                    "pid": pid,
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr.strip()[:200],
                }
            },
        )
    return ok


def _kill_tree_posix(pid: int) -> bool:
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        return True
    except ProcessLookupError:
        return True  # já morreu
    except OSError as exc:
        logger.warning(
            "falha ao encerrar grupo de processos",
            extra={"extra_fields": {"pid": pid, "error": str(exc)}},
        )
        return False
