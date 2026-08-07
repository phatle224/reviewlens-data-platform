"""JSON logging with correlation context and fail-closed redaction."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TextIO, cast
from uuid import uuid4

import structlog
from structlog.contextvars import bound_contextvars, clear_contextvars, get_contextvars
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

REDACTED = "[REDACTED]"
REDACTED_BINARY = "[REDACTED_BINARY]"
INVALID_EVENT = "invalid_log_event"
MAX_STRING_LENGTH = 1024
MAX_COLLECTION_ITEMS = 50
MAX_NESTING_DEPTH = 6

_STABLE_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>'\"]+", re.IGNORECASE)
_PAYMENT_LIKE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PHONE = re.compile(r"(?<![\w])(?:\+?\d[\d(). -]{7,}\d)(?![\w])")

_CORRELATION_FIELDS = (
    "trace_id",
    "source_release_id",
    "ingestion_batch_id",
    "dataset_run_id",
    "process_run_id",
    "release_id",
)
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "password",
        "passphrase",
        "api_key",
        "access_key",
        "access_key_id",
        "private_key",
        "private_key_path",
        "secret",
        "secret_key",
        "secret_access_key",
        "token",
        "auth_token",
        "refresh_token",
        "session_cookie",
    }
)
_RESTRICTED_TEXT_KEYS = frozenset(
    {
        "content",
        "document_text",
        "chunk_text",
        "error_message",
        "message",
        "prompt",
        "prompt_text",
        "provider_body",
        "query",
        "question",
        "raw_payload",
        "raw_review",
        "request_body",
        "response_body",
        "review_comment",
        "review_text",
        "review_title",
    }
)


def new_trace_id() -> str:
    """Return an opaque trace ID that is safe to place in logs and audit rows."""

    return uuid4().hex


def _validate_id(field_name: str, value: str) -> None:
    if not _CORRELATION_ID.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable opaque identifier")


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Context propagated across one logical source, process, or serving flow."""

    trace_id: str
    source_release_id: str | None = None
    ingestion_batch_id: str | None = None
    dataset_run_id: str | None = None
    process_run_id: str | None = None
    release_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in _CORRELATION_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                _validate_id(field_name, value)

    def as_dict(self) -> dict[str, str]:
        return {
            field_name: value
            for field_name in _CORRELATION_FIELDS
            if (value := getattr(self, field_name)) is not None
        }


@contextmanager
def bind_log_context(context: CorrelationContext) -> Generator[None]:
    """Bind and restore correlation fields using context-local storage."""

    with bound_contextvars(**context.as_dict()):
        yield


def clear_log_context() -> None:
    """Clear context at an Airflow task, request, or CLI operation boundary."""

    clear_contextvars()


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _matches_protected_key(normalized: str, protected: frozenset[str]) -> bool:
    return normalized in protected or any(normalized.endswith(f"_{key}") for key in protected)


class Redactor:
    """Recursively sanitize log values without calling unknown-object reprs."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._secrets = tuple(
            sorted({value for value in secret_values if len(value) >= 8}, key=len, reverse=True)
        )

    def redact_event(self, event_dict: EventDict) -> EventDict:
        redacted = self._redact_mapping(event_dict, depth=0)
        event_dict.clear()
        event_dict.update(redacted)
        return event_dict

    def _redact_mapping(self, value: Mapping[Any, Any], *, depth: int) -> dict[str, object]:
        if depth >= MAX_NESTING_DEPTH:
            return {"redaction": "[MAX_DEPTH]"}
        redacted: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_COLLECTION_ITEMS:
                redacted["truncated_items"] = len(value) - MAX_COLLECTION_ITEMS
                break
            key_is_safe = (
                isinstance(key, str)
                and _FIELD_NAME.fullmatch(key) is not None
                and self._redact_string(key) == key
            )
            key_text = key if key_is_safe else f"invalid_field_{index}"
            normalized = _normalized_key(key_text)
            if _matches_protected_key(normalized, _SENSITIVE_KEYS) or _matches_protected_key(
                normalized, _RESTRICTED_TEXT_KEYS
            ):
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = self._redact_value(item, depth=depth + 1)
        return redacted

    def _redact_value(self, value: object, *, depth: int) -> object:
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, str):
            return self._redact_string(value)
        if isinstance(value, bytes | bytearray | memoryview):
            return REDACTED_BINARY
        if isinstance(value, BaseException):
            return f"[EXCEPTION:{type(value).__name__}]"
        if isinstance(value, Mapping):
            return self._redact_mapping(value, depth=depth)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            if depth >= MAX_NESTING_DEPTH:
                return "[MAX_DEPTH]"
            items = [
                self._redact_value(item, depth=depth + 1) for item in value[:MAX_COLLECTION_ITEMS]
            ]
            if len(value) > MAX_COLLECTION_ITEMS:
                items.append(f"[TRUNCATED:{len(value) - MAX_COLLECTION_ITEMS}]")
            return items
        return f"[OBJECT:{type(value).__name__}]"

    def _redact_string(self, value: str) -> str:
        redacted = value
        for secret in self._secrets:
            redacted = redacted.replace(secret, REDACTED)
        redacted = _EMAIL.sub(REDACTED, redacted)
        redacted = _URL.sub(REDACTED, redacted)
        redacted = _PAYMENT_LIKE.sub(REDACTED, redacted)
        redacted = _PHONE.sub(REDACTED, redacted)
        if len(redacted) > MAX_STRING_LENGTH:
            return f"{redacted[:MAX_STRING_LENGTH]}[TRUNCATED]"
        return redacted


class _EventAndContextProcessor:
    def __init__(self, trace_id_factory: Callable[[], str]) -> None:
        self._trace_id_factory = trace_id_factory

    def __call__(
        self,
        _logger: WrappedLogger,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event = event_dict.get("event")
        event_dict["event"] = (
            event if isinstance(event, str) and _STABLE_NAME.fullmatch(event) else INVALID_EVENT
        )

        for field_name in _CORRELATION_FIELDS:
            event_dict.pop(field_name, None)
        context = get_contextvars()
        for field_name in _CORRELATION_FIELDS:
            value = context.get(field_name)
            if isinstance(value, str) and _CORRELATION_ID.fullmatch(value):
                event_dict[field_name] = value

        if "trace_id" not in event_dict:
            trace_id = self._trace_id_factory()
            _validate_id("trace_id", trace_id)
            event_dict["trace_id"] = trace_id
        return event_dict


def _sanitize_exception(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict

    exception_type: type[BaseException] | None = None
    if isinstance(exc_info, BaseException):
        exception_type = type(exc_info)
    elif isinstance(exc_info, tuple) and exc_info:
        candidate = exc_info[0]
        if isinstance(candidate, type) and issubclass(candidate, BaseException):
            exception_type = candidate
    else:
        exception_type = sys.exc_info()[0]
    event_dict["exception_type"] = exception_type.__name__ if exception_type else "Exception"
    return event_dict


class _RedactionProcessor:
    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def __call__(
        self,
        _logger: WrappedLogger,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        return self._redactor.redact_event(event_dict)


def configure_logging(
    *,
    stream: TextIO | None = None,
    minimum_level: int = logging.INFO,
    secret_values: Iterable[str] = (),
    trace_id_factory: Callable[[], str] = new_trace_id,
) -> None:
    """Configure newline-delimited JSON logging once per process entrypoint."""

    redactor = Redactor(secret_values)
    structlog.configure(
        processors=[
            _EventAndContextProcessor(trace_id_factory),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _sanitize_exception,
            _RedactionProcessor(redactor),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(minimum_level),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(component: str) -> FilteringBoundLogger:
    """Return a structured logger bound to a stable component name."""

    if not _STABLE_NAME.fullmatch(component):
        raise ValueError("logging component must be a stable lowercase name")
    return cast(FilteringBoundLogger, structlog.get_logger().bind(component=component))
