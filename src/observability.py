"""Structured JSON logging with request-scoped correlation IDs."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "correlation_id": getattr(record, "correlation_id", "-"),
                "trace_id": getattr(record, "trace_id", "-"),
                **{
                    key: getattr(record, key)
                    for key in (
                        "error_type",
                        "run_id",
                        "point_count",
                        "anomaly_count",
                        "unsupported_claim_count",
                    )
                    if hasattr(record, key)
                },
            },
            ensure_ascii=True,
        )


class FinOpsJsonStreamHandler(logging.StreamHandler):
    pass


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        record.trace_id = _trace_id.get()
        return True


def configure_json_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    if not any(
        isinstance(handler, FinOpsJsonStreamHandler) for handler in root_logger.handlers
    ):
        handler = FinOpsJsonStreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler.addFilter(CorrelationIdFilter())
        root_logger.addHandler(handler)
    root_logger.setLevel(level)


@contextmanager
def correlation_context(correlation_id: str, trace_id: str = "-") -> Iterator[None]:
    correlation_token = _correlation_id.set(correlation_id)
    trace_token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(trace_token)
        _correlation_id.reset(correlation_token)
