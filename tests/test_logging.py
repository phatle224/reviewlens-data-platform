from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from reviewlens.observability.logging import (
    INVALID_EVENT,
    REDACTED,
    CorrelationContext,
    Redactor,
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
)

SECRET = "seeded-runtime-secret-value"
REVIEW_TEXT = "The courier asked me to share a private delivery detail."
EMAIL = "student.portfolio@example.com"
PHONE = "+84 912 345 678"
PAYMENT_LIKE = "4111 1111 1111 1111"
URL = "https://example.invalid/private?signature=seeded"


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    structlog.reset_defaults()
    clear_log_context()
    yield
    clear_log_context()
    structlog.reset_defaults()


def _payloads(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_structured_log_has_stable_event_level_timestamp_and_correlation() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream, trace_id_factory=lambda: "fallback-trace")
    logger = get_logger("pipeline.ingestion")
    context = CorrelationContext(
        trace_id="trace-001",
        source_release_id="source-release-001",
        ingestion_batch_id="batch-001",
        dataset_run_id="dataset-run-001",
        process_run_id="process-run-001",
        release_id="release-001",
    )

    with bind_log_context(context):
        logger.info("ingestion.validated", record_count=9)

    payload = _payloads(stream)[0]
    assert payload["event"] == "ingestion.validated"
    assert payload["component"] == "pipeline.ingestion"
    assert payload["level"] == "info"
    assert payload["timestamp"].endswith("Z")
    assert payload["trace_id"] == "trace-001"
    assert payload["source_release_id"] == "source-release-001"
    assert payload["ingestion_batch_id"] == "batch-001"
    assert payload["dataset_run_id"] == "dataset-run-001"
    assert payload["process_run_id"] == "process-run-001"
    assert payload["release_id"] == "release-001"
    assert payload["record_count"] == 9


def test_redaction_removes_nested_secrets_pii_urls_payment_and_review_text() -> None:
    stream = io.StringIO()
    configure_logging(
        stream=stream,
        secret_values=(SECRET,),
        trace_id_factory=lambda: "trace-redaction",
    )
    logger = get_logger("provider.openrouter")

    logger.warning(
        "provider.request_denied",
        api_key=SECRET,
        review_text=REVIEW_TEXT,
        nested={
            "authorization": f"Bearer {SECRET}",
            "contact": f"email={EMAIL}; phone={PHONE}",
            "checkout": PAYMENT_LIKE,
            "source_url": URL,
            "items": [SECRET, {"response_body": REVIEW_TEXT}],
            "unsafe_keys": {SECRET: "secret-key-value", EMAIL: "email-key-value"},
        },
    )

    serialized = stream.getvalue()
    for canary in (SECRET, REVIEW_TEXT, EMAIL, PHONE, PAYMENT_LIKE, URL):
        assert canary not in serialized
    payload = _payloads(stream)[0]
    assert payload["api_key"] == REDACTED
    assert payload["review_text"] == REDACTED
    assert payload["nested"]["authorization"] == REDACTED
    assert payload["nested"]["items"][1]["response_body"] == REDACTED
    assert payload["nested"]["unsafe_keys"] == {
        "invalid_field_0": "secret-key-value",
        "invalid_field_1": "email-key-value",
    }


def test_invalid_or_raw_event_name_is_replaced_without_leaking_text() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream, trace_id_factory=lambda: "trace-event")
    logger = get_logger("app.local")

    logger.info(REVIEW_TEXT)

    assert REVIEW_TEXT not in stream.getvalue()
    assert _payloads(stream)[0]["event"] == INVALID_EVENT


def test_exception_logging_keeps_type_but_drops_message_and_traceback_values() -> None:
    stream = io.StringIO()
    configure_logging(
        stream=stream,
        secret_values=(SECRET,),
        trace_id_factory=lambda: "trace-exception",
    )
    logger = get_logger("provider.snowflake")

    try:
        raise RuntimeError(f"provider leaked {SECRET}, {EMAIL}, and {REVIEW_TEXT}")
    except RuntimeError:
        logger.exception("provider.request_failed")

    serialized = stream.getvalue()
    for canary in (SECRET, EMAIL, REVIEW_TEXT):
        assert canary not in serialized
    payload = _payloads(stream)[0]
    assert payload["exception_type"] == "RuntimeError"
    assert "exception" not in payload


def test_context_isolation_restores_outer_context_and_denies_callsite_spoofing() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream, trace_id_factory=lambda: "fallback-trace")
    logger = get_logger("pipeline.transform")

    with bind_log_context(CorrelationContext(trace_id="outer-trace", dataset_run_id="run-1")):
        logger.info("outer.before", trace_id="spoofed", release_id="spoofed-release")
        with bind_log_context(CorrelationContext(trace_id="inner-trace", release_id="release-2")):
            logger.info("inner.event")
        logger.info("outer.after")
    logger.info("outside.event", dataset_run_id="spoofed-run")

    before, inner, after, outside = _payloads(stream)
    assert before["trace_id"] == "outer-trace"
    assert before["dataset_run_id"] == "run-1"
    assert "release_id" not in before
    assert inner["trace_id"] == "inner-trace"
    assert inner["dataset_run_id"] == "run-1"
    assert inner["release_id"] == "release-2"
    assert after["trace_id"] == "outer-trace"
    assert after["dataset_run_id"] == "run-1"
    assert outside["trace_id"] == "fallback-trace"
    assert "dataset_run_id" not in outside


@pytest.mark.parametrize(
    "context",
    [
        CorrelationContext,
        lambda: CorrelationContext(trace_id=""),
        lambda: CorrelationContext(trace_id="trace with spaces"),
        lambda: CorrelationContext(trace_id="trace", release_id="customer@example.com"),
    ],
)
def test_correlation_context_rejects_invalid_or_identifier_like_pii(
    context: Any,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        context()


def test_configuration_is_reentrant_and_minimum_level_filters_debug() -> None:
    first_stream = io.StringIO()
    second_stream = io.StringIO()
    configure_logging(
        stream=first_stream,
        minimum_level=logging.INFO,
        trace_id_factory=lambda: "first-trace",
    )
    get_logger("test.first").info("first.event")

    configure_logging(
        stream=second_stream,
        minimum_level=logging.WARNING,
        trace_id_factory=lambda: "second-trace",
    )
    logger = get_logger("test.second")
    logger.debug("filtered.event")
    logger.warning("second.event")

    assert len(_payloads(first_stream)) == 1
    assert [payload["event"] for payload in _payloads(second_stream)] == ["second.event"]
    assert _payloads(second_stream)[0]["trace_id"] == "second-trace"


def test_redactor_bounds_collections_depth_binary_and_unknown_objects() -> None:
    redactor = Redactor()
    event: dict[str, Any] = {
        "event": "redaction.bounds",
        "binary": b"seeded-binary",
        "items": list(range(55)),
        "unknown": object(),
        "nested": {"a": {"b": {"c": {"d": {"e": {"f": "too-deep"}}}}}},
    }

    redacted = redactor.redact_event(event)

    assert redacted["binary"] == "[REDACTED_BINARY]"
    assert redacted["items"][-1] == "[TRUNCATED:5]"
    assert redacted["unknown"] == "[OBJECT:object]"
    assert "too-deep" not in json.dumps(redacted)
