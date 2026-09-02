"""Log estruturado em JSON (NFR-050) com identificador de correlação (NFR-052)."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

#: Teto de cada arquivo de log e quantos arquivos antigos ficam guardados.
#: 10 MB x 5 limita o log a ~60 MB: sem isso o arquivo cresce sem fim (o de
#: desenvolvimento passou de 57 MB), e o polling escreve algumas linhas por
#: segundo.
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

#: Quem pediu a ação desta requisição: `None` (a pessoa, pelo botão) ou a tripla
#: `(agente, motivo, origem)` quando o servidor reconheceu uma proposta sua.
#:
#: Vive num `ContextVar` pelo mesmo motivo do `correlation_id`: quem grava a
#: auditoria é o serviço, lá no fundo, e passar autoria por parâmetro obrigaria
#: a atravessar rota, serviço, adapter e runner com um argumento que só a
#: última linha usa.
_autoria: ContextVar[tuple[str, str, str] | None] = ContextVar("autoria", default=None)

# Chaves cujo valor nunca é gravado (NFR-103 / defesa D8).
SENSITIVE_HINTS = ("token", "secret", "password", "passwd", "authorization", "api_key")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


def set_correlation_id(value: str | None) -> str:
    resolved = value or new_correlation_id()
    _correlation_id.set(resolved)
    return resolved


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_autoria(valor: tuple[str, str, str] | None) -> None:
    """Marca a requisição atual como vinda de uma proposta da IA."""
    _autoria.set(valor)


def get_autoria() -> tuple[str, str, str] | None:
    return _autoria.get()


def redact(value: str) -> str:
    """Mascara valor que pareça segredo, preservando a forma para depuração."""
    lowered = value.lower()
    if any(hint in lowered for hint in SENSITIVE_HINTS) and "=" in value:
        key, _, _ = value.partition("=")
        return f"{key}=***"
    return value


def redact_argv(argv: list[str]) -> list[str]:
    return [redact(item) for item in argv]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation = get_correlation_id()
        if correlation:
            payload["correlation_id"] = correlation
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    fmt: str = "json",
    *,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    formatter: logging.Formatter = (
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def log_with(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"extra_fields": fields})
