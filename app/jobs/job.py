"""Estado de um job (ADR-006)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.models.base import utcnow

TRUNCATION_MARKER = "… saída truncada: linhas iniciais descartadas …"


def _size(line: str) -> int:
    """Bytes que a linha ocupa, contando a quebra."""
    return len(line.encode("utf-8", errors="replace")) + 1


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"

    @property
    def is_final(self) -> bool:
        return self in {
            JobStatus.SUCCESS,
            JobStatus.FAILED,
            JobStatus.TIMEOUT,
            JobStatus.CANCELLED,
        }


@dataclass
class Job:
    id: str
    action: str
    key: str
    project_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    message: str | None = None

    #: Saída acumulada em linhas, com limite de bytes (ver `output_limit`).
    lines: list[str] = field(default_factory=list)
    output_bytes: int = 0
    output_truncated: bool = False
    #: Quantas linhas já foram descartadas pela frente. É o deslocamento entre
    #: o índice absoluto que o cliente acompanha e a posição atual em `lines`.
    #: Sem ele, tudo que sai depois do primeiro truncamento some no caminho.
    dropped: int = 0

    _cancel: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    #: Incrementa a cada linha nova; usado pelo SSE e pelo polling para saber
    #: o que já foi entregue, sem reenviar tudo.
    revision: int = 0

    def append(self, line: str, *, limit: int) -> None:
        self.lines.append(line)
        self.output_bytes += _size(line)
        self.revision += 1

        if self.output_bytes > limit:
            self._trim(limit)

    def _trim(self, limit: int) -> None:
        """Descarta o começo até caber.

        O interessante em log de comando longo quase sempre está no fim: o
        erro que fez o `compose up` falhar aparece nas últimas linhas, não nas
        primeiras. Por isso corta-se pela frente.

        Precisa rodar em **toda** ultrapassagem, não só na primeira: um job que
        produz saída sem parar tem que continuar cabendo no limite.

        O marcador de truncamento **não entra** em `lines`. Ele é apresentação,
        e uma linha sintética na lista desalinharia o índice absoluto que o SSE
        e o polling usam para saber o que já entregaram — o efeito era a saída
        parar de aparecer no console a partir do primeiro corte. Quem exibe lê
        `output_truncated`.
        """
        while len(self.lines) > 1 and self.output_bytes > limit:
            removed = self.lines.pop(0)
            self.output_bytes -= _size(removed)
            self.dropped += 1

        self.output_truncated = True

    def lines_since(self, absolute_index: int) -> list[str]:
        """Linhas a partir de um índice **absoluto**, contado desde a primeira.

        O cliente guarda um cursor que nunca retrocede; `lines` retrocede a
        cada truncamento. Esta é a única tradução entre os dois.
        """
        return self.lines[max(0, absolute_index - self.dropped) :]

    @property
    def output(self) -> str:
        corpo = "\n".join(self.lines)
        return f"{TRUNCATION_MARKER}\n{corpo}" if self.output_truncated else corpo

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None:
            return None
        end = self.finished_at or utcnow()
        return int((end - self.started_at).total_seconds() * 1000)

    def request_cancel(self) -> None:
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def cancel_event(self) -> asyncio.Event:
        return self._cancel
