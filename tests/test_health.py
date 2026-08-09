from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from reviewlens.app.readiness import ReadinessCheck, ReadinessReport, ReadinessState
from reviewlens.observability.health import build_metrics_payload, create_health_server


def _report() -> ReadinessReport:
    return ReadinessReport(
        state=ReadinessState.DEGRADED,
        checks=(
            ReadinessCheck("local_auth", True, "Configured."),
            ReadinessCheck("openrouter", False, "Not configured."),
        ),
        data_mode="synthetic",
    )


def test_synthetic_health_metric_is_visible_over_loopback_http() -> None:
    server = create_health_server(_report(), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback test URL
            f"{base_url}/healthz", timeout=2
        ) as response:
            health = json.load(response)
            assert response.headers["Cache-Control"] == "no-store"
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback test URL
            f"{base_url}/metrics", timeout=2
        ) as response:
            metrics = response.read().decode("utf-8")
        with pytest.raises(urllib.error.HTTPError, match="HTTP Error 404"):
            urllib.request.urlopen(  # noqa: S310 - fixed loopback test URL
                f"{base_url}/unknown", timeout=2
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert health["provider_calls_performed"] is False
    assert health["state"] == "degraded"
    assert 'reviewlens_integration_configured{integration="local_auth"} 1.0' in metrics
    assert 'reviewlens_integration_configured{integration="openrouter"} 0.0' in metrics
    assert "reviewlens_foundation_ready 0.0" in metrics
    assert 'reviewlens_service_errors_total{service="foundation"} 0.0' in metrics


def test_health_metrics_have_bounded_labels_and_no_check_details() -> None:
    payload = build_metrics_payload(_report()).decode("utf-8")

    assert "Configured." not in payload
    assert "Not configured." not in payload
    assert "provider_calls" not in payload


def test_health_server_rejects_remote_bind_outside_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REVIEWLENS_CONTAINER_RUNTIME", raising=False)

    with pytest.raises(ValueError, match="local Compose"):
        create_health_server(_report(), host="0.0.0.0", port=0)  # noqa: S104
