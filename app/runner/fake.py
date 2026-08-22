"""FakeCommandRunner — peça central da estratégia de testes.

Permite asserção nos dois lados: o argv que o adapter **produziu** e o que o
service **entendeu** da saída. Nenhum teste unitário precisa tocar no sistema
operacional (NFR-031).
"""

from __future__ import annotations

from app.runner.command_spec import CommandResult, CommandSpec


class FakeCommandRunner:
    def __init__(self, responses: dict[str, CommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[CommandSpec] = []
        self.default = CommandResult(exit_code=0, stdout="", stderr="", duration_ms=1)

    def run(self, spec: CommandSpec) -> CommandResult:
        self.calls.append(spec)
        return self.responses.get(spec.label, self.default)

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
