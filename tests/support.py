"""Dublês compartilhados pelos testes.

O `FakeAsyncRunner` existe por um motivo aprendido do jeito difícil: um teste
de API que enfileirava `docker compose up` chegou a **subir containers de
verdade** na máquina, porque o `JobManager` usava o runner assíncrono real. O
`CommandRunner` síncrono estar dublado não basta — jobs usam o outro caminho.

Regra: todo app de teste substitui **os dois** runners.
"""

from __future__ import annotations

import asyncio

from app.runner.command_spec import CommandResult, CommandSpec


class FakeAsyncRunner:
    """Runner assíncrono controlável, sem tocar no sistema operacional."""

    def __init__(
        self,
        lines: list[str] | None = None,
        result: CommandResult | None = None,
        delay: float = 0.0,
        hang: bool = False,
        results_by_label: dict[str, CommandResult] | None = None,
    ) -> None:
        self.lines = lines or []
        self.result = result or CommandResult(0, "", "", 5)
        self.delay = delay
        self.hang = hang
        self.results_by_label = results_by_label or {}
        self.terminated = False
        self.calls: list[CommandSpec] = []

    async def run(
        self,
        spec: CommandSpec,
        on_line=None,  # type: ignore[no-untyped-def]
        cancel_event: asyncio.Event | None = None,
    ) -> CommandResult:
        self.calls.append(spec)

        for line in self.lines:
            if on_line is not None:
                on_line("stdout", line)
            if self.delay:
                await asyncio.sleep(self.delay)

        if self.hang:
            assert cancel_event is not None
            await cancel_event.wait()
            self.terminated = True
            return CommandResult(-1, "", "", 10)

        return self.results_by_label.get(spec.label, self.result)

    # --- helpers de asserção ---

    @property
    def labels(self) -> list[str]:
        return [call.label for call in self.calls]

    def argv_for(self, label: str) -> list[str]:
        for call in self.calls:
            if call.label == label:
                return call.argv
        raise AssertionError(f"Nenhuma execução com label {label!r}. Houve: {self.labels}")

    def assert_never_ran(self, label: str) -> None:
        if label in self.labels:
            raise AssertionError(f"A ação {label!r} não deveria ter sido executada.")
