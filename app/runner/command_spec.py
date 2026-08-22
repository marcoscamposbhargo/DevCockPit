"""Especificação de comando — a única forma de pedir execução.

`argv` é sempre lista. `timeout_s` é obrigatório. Não existe construtor que
aceite string de shell, porque não existe execução com shell (ADR-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path
    timeout_s: float
    label: str
    env_extra: dict[str, str] = field(default_factory=dict)

    #: Programa que **abre uma janela e fica de pé** — terminal, editor,
    #: explorador de arquivos. Esperar por ele é sempre errado: ou ele devolve
    #: na hora (e a espera não custa nada) ou ele só termina quando o usuário
    #: fecha a janela, e aí o timeout mata o que acabou de ser aberto. Com este
    #: sinal o runner dispara e segue, sem pipe e sem espera.
    detached: bool = False

    def __post_init__(self) -> None:
        if not self.argv:
            raise ValueError("argv não pode ser vazio.")
        if not all(isinstance(item, str) for item in self.argv):
            raise ValueError("argv precisa conter apenas strings.")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s é obrigatório e precisa ser positivo.")
        if not self.label:
            raise ValueError("label é obrigatório para a auditoria.")

    @property
    def program(self) -> str:
        return self.argv[0]


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out
