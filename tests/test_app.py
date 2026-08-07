from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import ValidationError
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest

import reviewlens.app.ui as app_ui
from reviewlens.app.auth import MAX_TOKEN_LENGTH, AuthDecision, verify_auth_token
from reviewlens.app.launcher import build_streamlit_command
from reviewlens.app.readiness import (
    ReadinessCheck,
    ReadinessReport,
    ReadinessState,
    collect_readiness,
)
from reviewlens.config import AppSettings, ServiceName, load_settings
from reviewlens.security.credentials import CredentialReadiness

APP_SCRIPT = Path("src/reviewlens/app/streamlit_app.py").resolve()
APP_TOKEN = "seeded-local-app-token-32-characters"
LEAK_CANARY = "seeded-app-leak-canary"


def _settings(tmp_path: Path, *, with_token: bool = True) -> AppSettings:
    environment = {"APP_AUTH_TOKEN": APP_TOKEN} if with_token else {}
    return load_settings(environ=environment, env_file=tmp_path / ".missing.env")


def _ready_report() -> ReadinessReport:
    return ReadinessReport(
        state=ReadinessState.READY,
        checks=(ReadinessCheck("local_auth", True, "Local token is configured."),),
        data_mode="synthetic",
    )


def _patch_app(
    monkeypatch: pytest.MonkeyPatch,
    settings: AppSettings,
    report: ReadinessReport,
) -> None:
    monkeypatch.setattr(app_ui, "load_settings", lambda: settings)
    monkeypatch.setattr(app_ui, "collect_readiness", lambda _settings: report)


def _rendered_values(app: AppTest) -> str:
    values = [element.value for element in app.title]
    values.extend(element.value for element in app.header)
    values.extend(element.value for element in app.subheader)
    values.extend(element.value for element in app.caption)
    values.extend(element.value for element in app.info)
    values.extend(element.value for element in app.success)
    values.extend(element.value for element in app.warning)
    values.extend(element.value for element in app.error)
    return " ".join(str(value) for value in values)


def _unlock(app: AppTest, token: str) -> AppTest:
    app.text_input[0].input(token).run()
    return app.button[0].click().run()


@pytest.mark.parametrize(
    ("candidate", "configured", "expected"),
    [
        (APP_TOKEN, APP_TOKEN, AuthDecision.GRANTED),
        ("wrong-token", APP_TOKEN, AuthDecision.DENIED),
        ("", APP_TOKEN, AuthDecision.DENIED),
        ("x" * (MAX_TOKEN_LENGTH + 1), APP_TOKEN, AuthDecision.DENIED),
        (APP_TOKEN, None, AuthDecision.CONFIGURATION_ERROR),
    ],
)
def test_auth_decision_is_fail_closed_and_secret_free(
    candidate: str,
    configured: str | None,
    expected: AuthDecision,
) -> None:
    from pydantic import SecretStr

    configured_secret = SecretStr(configured) if configured is not None else None
    decision = verify_auth_token(candidate, configured_secret)

    assert decision is expected
    if candidate:
        assert candidate not in repr(decision)


def test_readiness_uses_boolean_signals_without_provider_calls(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    calls = 0

    def inspector(
        settings: AppSettings,
        *,
        environ: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> CredentialReadiness:
        nonlocal calls
        calls += 1
        assert settings.app.auth_required
        assert environ == {"synthetic": "only"}
        assert env_file == tmp_path / ".missing.env"
        return CredentialReadiness(
            snowflake=dict.fromkeys(ServiceName, True),
            r2_ingest=True,
            r2_stage=True,
            openrouter=True,
            chroma=True,
            app=True,
        )

    report = collect_readiness(
        settings,
        environ={"synthetic": "only"},
        env_file=tmp_path / ".missing.env",
        inspector=inspector,
    )

    assert calls == 1
    assert report.state is ReadinessState.READY
    assert report.provider_calls_performed is False
    assert report.public_payload()["provider_calls_performed"] is False


def test_readiness_failure_is_generic_and_does_not_leak_exception(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def failing_inspector(
        settings: AppSettings,
        *,
        environ: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> CredentialReadiness:
        assert settings.app.auth_required
        raise RuntimeError(f"provider leaked {LEAK_CANARY}")

    report = collect_readiness(settings, inspector=failing_inspector)
    serialized = str(report.public_payload())

    assert report.state is ReadinessState.UNAVAILABLE
    assert LEAK_CANARY not in serialized
    assert "RuntimeError" not in serialized


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('bind_host = "127.0.0.1"', 'bind_host = "0.0.0.0"', "loopback"),
        ("auth_required = true", "auth_required = false", "authentication"),
    ],
)
def test_local_app_rejects_remote_bind_or_disabled_auth(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    source = Path("config/config.toml").read_text(encoding="utf-8").replace(old, new)
    config_path = tmp_path / "config.toml"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValidationError, match=message):
        load_settings(environ={}, config_path=config_path, env_file=tmp_path / ".missing.env")


def test_launcher_uses_canonical_loopback_config_and_security_flags(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    command = build_streamlit_command(
        settings,
        python_executable="python-test",
        script_path=Path("synthetic_streamlit_app.py"),
    )
    rendered = " ".join(command)

    assert command[:4] == ("python-test", "-m", "streamlit", "run")
    assert "--server.address=127.0.0.1" in command
    assert "--server.port=8501" in command
    assert "--server.headless=true" in command
    assert "--server.enableCORS=true" in command
    assert "--server.enableXsrfProtection=true" in command
    assert "--client.showErrorDetails=none" in command
    assert "--browser.gatherUsageStats=false" in command
    assert "0.0.0.0" not in rendered  # noqa: S104 - negative bind assertion
    assert APP_TOKEN not in rendered


def test_streamlit_shell_denies_anonymous_and_invalid_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_app(monkeypatch, _settings(tmp_path), _ready_report())
    app = AppTest.from_file(APP_SCRIPT, default_timeout=5).run()

    assert not app.exception
    assert app.subheader[0].value == "Local access"
    assert not app.header
    assert app.text_input[0].proto.type == TextInputProto.PASSWORD

    app = _unlock(app, LEAK_CANARY)

    assert not app.exception
    assert app.warning[0].value == "Access denied. Check the local token and try again."
    assert not app.header
    assert LEAK_CANARY not in _rendered_values(app)


def test_streamlit_shell_authenticates_renders_health_and_signs_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_app(monkeypatch, _settings(tmp_path), _ready_report())
    app = AppTest.from_file(APP_SCRIPT, default_timeout=5).run()

    app = _unlock(app, APP_TOKEN)

    assert not app.exception
    assert app.header[0].value == "ReviewLens foundation shell"
    assert app.subheader[0].value == "Configuration readiness"
    assert app.success[0].value == "All M1 runtime credentials are configured."
    assert not app.text_input
    assert APP_TOKEN not in _rendered_values(app)

    app = app.button[0].click().run()

    assert not app.exception
    assert app.subheader[0].value == "Local access"
    assert not app.header


def test_streamlit_shell_renders_degraded_integration_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    degraded = collect_readiness(
        settings,
        environ={"APP_AUTH_TOKEN": APP_TOKEN},
        env_file=tmp_path / ".missing.env",
    )
    assert degraded.state is ReadinessState.DEGRADED
    _patch_app(monkeypatch, settings, degraded)

    app = _unlock(AppTest.from_file(APP_SCRIPT, default_timeout=5).run(), APP_TOKEN)

    assert not app.exception
    assert app.warning[0].value == (
        "The shell is available, but one or more runtime integrations are not configured."
    )
    assert "No active analytics release is published yet." in app.info[0].value


def test_streamlit_shell_has_explicit_unavailable_and_config_error_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable = ReadinessReport(
        state=ReadinessState.UNAVAILABLE,
        checks=(ReadinessCheck("credential_readiness", False, "Readiness unavailable."),),
        data_mode="synthetic",
    )
    _patch_app(monkeypatch, _settings(tmp_path), unavailable)
    app = _unlock(AppTest.from_file(APP_SCRIPT, default_timeout=5).run(), APP_TOKEN)

    assert not app.exception
    assert app.error[0].value == (
        "Readiness is temporarily unavailable. No provider request was attempted."
    )

    def fail_config() -> NoReturn:
        raise ValueError(f"configuration leaked {LEAK_CANARY}")

    monkeypatch.setattr(app_ui, "load_settings", fail_config)
    failed_app = AppTest.from_file(APP_SCRIPT, default_timeout=5).run()
    rendered = _rendered_values(failed_app)

    assert not failed_app.exception
    assert "Application configuration is unavailable." in failed_app.error[0].value
    assert LEAK_CANARY not in rendered


def test_streamlit_shell_fails_closed_when_app_token_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_app(monkeypatch, _settings(tmp_path, with_token=False), _ready_report())
    app = AppTest.from_file(APP_SCRIPT, default_timeout=5).run()

    assert not app.exception
    assert "APP_AUTH_TOKEN" in app.error[0].value
    assert not app.text_input
    assert not app.header
