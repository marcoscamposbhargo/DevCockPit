"""Log estruturado em JSON (NFR-050) com identificador de correlação (NFR-052)."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

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


def configure_logging(level: str = "INFO", log_file: Path | None = None, fmt: str = "json") -> None:
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
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def log_with(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"extra_fields": fields})
