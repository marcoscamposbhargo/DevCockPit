"""Execução assíncrona com saída incremental (ADR-006).

Diferença essencial em relação ao `SubprocessCommandRunner`: aqui a saída é
entregue **linha a linha, enquanto o comando roda**. É o que permite o console
de job mostrar o progresso de um `compose up` de dois minutos em vez de uma
tela parada.

Nada de `communicate()` dentro do event loop: isso bloquearia a aplicação
inteira até o comando acabar.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable

from app.core.logging import redact_argv
from app.runner.command_spec import CommandResult, CommandSpec
from app.runner.process import CREATION_FLAGS, kill_tree

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

# Linha maior que isso é truncada: log de container pode vir sem quebra.
MAX_LINE_BYTES = 64 * 1024


class AsyncCommandRunner:
    """Executa um `CommandSpec` de forma assíncrona, emitindo linhas."""

    async def run(
        self,
        spec: CommandSpec,
        on_line: Callable[[str, str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> CommandResult:
        started = time.perf_counter()
        env = {**os.environ, **spec.env_extra} if spec.env_extra else None

        try:
            process = await asyncio.create_subprocess_exec(
                *spec.argv,
                cwd=str(spec.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=CREATION_FLAGS,
                start_new_session=not _IS_WINDOWS,
            )
        except FileNotFoundError:
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr=f"Programa não encontrado: {spec.program}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        collected: dict[str, list[str]] = {"stdout": [], "stderr": []}

        async def pump(stream: asyncio.StreamReader | None, channel: str) -> None:
            if stream is None:
                return
            while True:
                try:
                    raw = await stream.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    # Linha absurdamente longa: consome um pedaço e segue.
                    raw = await stream.read(MAX_LINE_BYTES)
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                collected[channel].append(line)
                if on_line is not None:
                    on_line(channel, line)

        pumps = asyncio.gather(
            pump(process.stdout, "stdout"),
            pump(process.stderr, "stderr"),
        )

        timed_out = False
        cancelled = False

        async def wait_for_cancel() -> None:
            if cancel_event is not None:
                await cancel_event.wait()

        cancel_task = asyncio.create_task(wait_for_cancel())
        wait_task = asyncio.create_task(process.wait())

        try:
            done, _ = await asyncio.wait(
                {wait_task, cancel_task},
                timeout=spec.timeout_s,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                timed_out = True
            elif cancel_task in done and wait_task not in done:
                cancelled = True

            if timed_out or cancelled:
                await self._terminate(process)
                # Espera curta para o pipe fechar e a saída parcial chegar.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wait_task, timeout=5)
        finally:
            cancel_task.cancel()
            try:
                await asyncio.wait_for(pumps, timeout=5)
            except TimeoutError:
                pumps.cancel()

        exit_code = process.returncode if process.returncode is not None else -1
        duration_ms = int((time.perf_counter() - started) * 1000)

        logger.info(
            "async command finished",
            extra={
                "extra_fields": {
                    "action": spec.label,
                    "argv": redact_argv(spec.argv),
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "timed_out": timed_out,
                    "cancelled": cancelled,
                }
            },
        )

        return CommandResult(
            exit_code=exit_code,
            stdout="\n".join(collected["stdout"]),
            stderr="\n".join(collected["stderr"]),
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        """Encerra a árvore. Um processo que ignora o sinal morre de todo jeito."""
        if process.returncode is not None:
            return

        pid = process.pid
        killed = await asyncio.to_thread(kill_tree, pid)

        if not killed:
            # Último recurso: mata só o processo direto.
            with contextlib.suppress(ProcessLookupError):
                process.kill()
