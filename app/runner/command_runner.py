"""CommandRunner — único ponto de execução de comando externo (ADR-003).

`subprocess` só pode ser importado neste pacote. Existe teste que reprova a
suíte se isso for violado, e outro que reprova se a execução com shell for
habilitada em qualquer lugar do código-fonte.

O teste de higiene procura pela atribuição literal e não abre exceção nem para
comentário: por isso este texto não a escreve. Um teste com escape é um teste
que um dia deixa passar.
"""

from __future__ import annotations

import logging
import os
import subprocess  # noqa: S404 - ponto único de execução, ver ADR-003
import time
from typing import Protocol

from app.core.logging import redact_argv
from app.runner.command_spec import CommandResult, CommandSpec

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"


class CommandRunner(Protocol):
    """Interface. Serviços dependem disto, nunca da implementação concreta."""

    def run(self, spec: CommandSpec) -> CommandResult: ...


class SubprocessCommandRunner:
    """Execução real, sem shell, com timeout obrigatório."""

    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._audit = audit_sink

    def run(self, spec: CommandSpec) -> CommandResult:
        if spec.detached:
            return self._spawn(spec)
        return self._run_and_wait(spec)

    def _spawn(self, spec: CommandSpec) -> CommandResult:
        """Dispara e segue, para programa que abre janela.

        Duas coisas que a espera quebrava, ambas verificadas nesta máquina:

        1. `powershell.exe -NoExit` (a reserva de terminal quando não há
           `wt.exe`) nunca termina sozinho. Esperado, ele estourava o timeout de
           10 s e era morto — o terminal aparecia e sumia.
        2. Capturar `stdout`/`stderr` amarra o processo a um pipe em vez de a um
           console. O terminal subia sem janela nenhuma.

        Por isso aqui não há `capture_output`, não há `timeout` e não há espera.
        O sucesso é ter conseguido criar o processo.
        """
        started = time.perf_counter()
        env = {**os.environ, **spec.env_extra} if spec.env_extra else None

        creation_flags = 0
        start_new_session = False
        if _IS_WINDOWS:
            # Console próprio: fechar o DevCockpit não pode fechar o terminal
            # que o usuário abriu. `CREATE_NEW_CONSOLE` e `DETACHED_PROCESS`
            # são mutuamente exclusivos no Windows — juntos, `CreateProcess`
            # recusa com parâmetro inválido.
            creation_flags = subprocess.CREATE_NEW_CONSOLE
        else:
            start_new_session = True

        try:
            subprocess.Popen(  # noqa: S603 - argv montado pelo OSAdapter, sem valor do cliente
                spec.argv,
                cwd=str(spec.cwd),
                shell=False,
                env=env,
                creationflags=creation_flags,
                start_new_session=start_new_session,
            )
        except (FileNotFoundError, OSError) as exc:
            result = CommandResult(
                exit_code=127,
                stdout="",
                stderr=f"Não foi possível iniciar {spec.program}: {exc}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            self._record(spec, result, status="FAILED")
            return result

        result = CommandResult(
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        self._record(spec, result, status="SUCCESS")
        return result

    def _run_and_wait(self, spec: CommandSpec) -> CommandResult:
        started = time.perf_counter()
        env = {**os.environ, **spec.env_extra} if spec.env_extra else None

        creation_flags = 0
        start_new_session = False
        if _IS_WINDOWS:
            # Cria um grupo de processos para que o timeout possa encerrar a
            # árvore inteira, não só o filho direto.
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        try:
            completed = subprocess.run(  # noqa: S603 - argv validado pela allowlist
                spec.argv,
                cwd=str(spec.cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=spec.timeout_s,
                shell=False,
                env=env,
                creationflags=creation_flags,
                start_new_session=start_new_session,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            result = CommandResult(
                exit_code=-1,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                duration_ms=duration_ms,
                timed_out=True,
            )
            self._record(spec, result, status="TIMEOUT")
            return result
        except FileNotFoundError:
            duration_ms = int((time.perf_counter() - started) * 1000)
            result = CommandResult(
                exit_code=127,
                stdout="",
                stderr=f"Programa não encontrado: {spec.program}",
                duration_ms=duration_ms,
            )
            self._record(spec, result, status="FAILED")
            return result

        duration_ms = int((time.perf_counter() - started) * 1000)
        result = CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=duration_ms,
        )
        self._record(spec, result, status="SUCCESS" if result.ok else "FAILED")
        return result

    def _record(self, spec: CommandSpec, result: CommandResult, status: str) -> None:
        argv = redact_argv(spec.argv)
        logger.info(
            "command executed",
            extra={
                "extra_fields": {
                    "action": spec.label,
                    "argv": argv,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "status": status,
                }
            },
        )
        if self._audit is not None:
            self._audit.record_command(spec=spec, result=result, status=status)


class AuditSink(Protocol):
    def record_command(self, spec: CommandSpec, result: CommandResult, status: str) -> None: ...


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
