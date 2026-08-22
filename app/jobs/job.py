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
        """
        if self.output_truncated and self.lines and self.lines[0] == TRUNCATION_MARKER:
            self.lines.pop(0)
            self.output_bytes -= _size(TRUNCATION_MARKER)

        while len(self.lines) > 1 and self.output_bytes > limit:
            removed = self.lines.pop(0)
            self.output_bytes -= _size(removed)

        self.output_truncated = True
        self.lines.insert(0, TRUNCATION_MARKER)
        self.output_bytes += _size(TRUNCATION_MARKER)

    @property
    def output(self) -> str:
        return "\n".join(self.lines)

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
