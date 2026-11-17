"""Structured JSON logging with PII/secret redaction (docs/SECURITY.md §9)."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_KEYS = re.compile(r"\b(nvapi-[A-Za-z0-9_-]+|sb_secret_[A-Za-z0-9_-]+|sk-[A-Za-z0-9]{16,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b")
_QUERY_SECRET = re.compile(r"(?i)\b(api_key|apikey|key|token|access_token|refresh_token|client_secret|password|code|secret)=([^&\s\"']+)")
_SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "api_key", "secret", "authorization", "body"}


def redact_text(text: str) -> str:
    text = _QUERY_SECRET.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _KEYS.sub("[REDACTED_KEY]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    return text


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(key, v) for v in value]
    return value


def redaction_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: _redact_value(k, v) for k, v in event_dict.items()}


class RedactingFilter(logging.Filter):
    """Applies the same redaction to standard-library log records (uvicorn, httpx, sqlalchemy…)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


class _StdoutHandler(logging.StreamHandler):
    """Resolves sys.stdout at write time (survives stream swaps, e.g. test capture)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def configure_logging(level: str = "INFO") -> None:
    handler = _StdoutHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if type(h) not in (logging.StreamHandler, _StdoutHandler)]
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore"):  # request lines can carry query-string credentials
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,  # render tracebacks first, then redact them too
            redaction_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
