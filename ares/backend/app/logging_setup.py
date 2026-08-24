"""Structured logging for ARES with mandatory secret redaction.

Log lines are single-line JSON so they can be shipped/parsed later. A
redaction filter guarantees that MT5 passwords and AI API keys never reach
any log sink, even if a subsystem logs an object containing them.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_SECRET_PATTERNS = [
    re.compile(r"(password['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.IGNORECASE),
    re.compile(r"(authorization['\"]?\s*[:=]\s*['\"]?)(bearer\s+\S+)", re.IGNORECASE),
]

_runtime_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret value so it is masked wherever it appears."""
    if value and len(value) >= 4:
        _runtime_secrets.add(value)


def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1***REDACTED***", text)
    for secret in _runtime_secrets:
        if secret in text:
            text = text.replace(secret, "***REDACTED***")
    return text


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format first (so %d/%f args keep their types), then redact.
        record.msg = _redact(record.getMessage())
        record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = _redact(self.formatException(record.exc_info))
        extra = getattr(record, "event", None)
        if extra:
            payload["event"] = extra
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    # Quiet down noisy access logs; ARES logs its own events.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ares.{name}")
