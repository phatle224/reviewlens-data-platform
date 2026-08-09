"""Provider-free local health and Prometheus metrics endpoint."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from reviewlens.app.readiness import ReadinessReport, ReadinessState, collect_readiness
from reviewlens.config import load_settings

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def build_metrics_payload(report: ReadinessReport) -> bytes:
    """Render a fresh, bounded registry without global metric side effects."""

    registry = CollectorRegistry()
    ready = Gauge(
        "reviewlens_foundation_ready",
        "Whether the local foundation configuration is fully ready.",
        registry=registry,
    )
    configured = Gauge(
        "reviewlens_integration_configured",
        "Whether a local integration has the required credential configuration.",
        ("integration",),
        registry=registry,
    )
    errors = Counter(
        "reviewlens_service_errors_total",
        "Bootstrap count of sanitized service errors.",
        ("service",),
        registry=registry,
    )
    ready.set(report.state is ReadinessState.READY)
    for check in report.checks:
        configured.labels(integration=check.name).set(check.configured)
    foundation_errors = errors.labels(service="foundation")
    if report.state is ReadinessState.UNAVAILABLE:
        foundation_errors.inc()
    return generate_latest(registry)


def _handler_for(report: ReadinessReport) -> type[BaseHTTPRequestHandler]:
    health_payload = json.dumps(
        report.public_payload(), separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    metrics_payload = build_metrics_payload(report)

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._respond(HTTPStatus.OK, "application/json", health_payload)
            elif self.path == "/metrics":
                self._respond(HTTPStatus.OK, PROMETHEUS_CONTENT_TYPE, metrics_payload)
            else:
                self._respond(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")

        def _respond(self, status: HTTPStatus, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return HealthHandler


def create_health_server(
    report: ReadinessReport,
    *,
    host: str = "127.0.0.1",
    port: int = 9108,
) -> ThreadingHTTPServer:
    if (
        host not in {"127.0.0.1", "localhost", "::1"}
        and os.environ.get("REVIEWLENS_CONTAINER_RUNTIME") != "compose"
    ):
        raise ValueError("non-loopback health bind is permitted only inside local Compose")
    return ThreadingHTTPServer((host, port), _handler_for(report))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve local ReviewLens health and metrics")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9108)
    args = parser.parse_args(argv)
    report = collect_readiness(load_settings())
    server = create_health_server(report, host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
