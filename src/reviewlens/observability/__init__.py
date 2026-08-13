"""Structured observability primitives for ReviewLens runtimes."""

from reviewlens.observability.ingestion import (
    DatasetIngestionMetrics,
    IngestionAlertCode,
    IngestionOperationsSnapshot,
    build_ingestion_metrics_payload,
    evaluate_ingestion_alerts,
    write_ingestion_operations_artifacts,
)
from reviewlens.observability.logging import (
    CorrelationContext,
    Redactor,
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
    new_trace_id,
)

__all__ = [
    "CorrelationContext",
    "DatasetIngestionMetrics",
    "IngestionAlertCode",
    "IngestionOperationsSnapshot",
    "Redactor",
    "bind_log_context",
    "build_ingestion_metrics_payload",
    "clear_log_context",
    "configure_logging",
    "evaluate_ingestion_alerts",
    "get_logger",
    "new_trace_id",
    "write_ingestion_operations_artifacts",
]
