"""Streamlit rendering for the authenticated M1 local shell."""

from __future__ import annotations

import logging

import streamlit as st
from pydantic import ValidationError

from reviewlens.app.auth import AuthDecision, verify_auth_token
from reviewlens.app.readiness import ReadinessReport, ReadinessState, collect_readiness
from reviewlens.config import AppSettings, load_settings
from reviewlens.observability import (
    CorrelationContext,
    bind_log_context,
    configure_logging,
    get_logger,
    new_trace_id,
)

_AUTHENTICATED_KEY = "_reviewlens_authenticated"
_AUTH_FEEDBACK_KEY = "_reviewlens_auth_feedback"
_AUTH_INPUT_KEY = "_reviewlens_access_input"


def _authenticate_from_session(settings: AppSettings) -> None:
    candidate = st.session_state.pop(_AUTH_INPUT_KEY, "")
    decision = verify_auth_token(candidate, settings.app.auth_token)
    st.session_state[_AUTHENTICATED_KEY] = decision is AuthDecision.GRANTED
    st.session_state[_AUTH_FEEDBACK_KEY] = decision.value


def _sign_out() -> None:
    st.session_state[_AUTHENTICATED_KEY] = False
    st.session_state.pop(_AUTH_INPUT_KEY, None)
    st.session_state.pop(_AUTH_FEEDBACK_KEY, None)


def _render_auth_gate(settings: AppSettings) -> bool:
    if st.session_state.get(_AUTHENTICATED_KEY) is True:
        return True

    st.subheader("Local access")
    if settings.app.auth_token is None:
        st.error(
            "Local authentication is not configured. Add APP_AUTH_TOKEN to the ignored .env file."
        )
        return False

    st.text_input(
        "Access token",
        type="password",
        key=_AUTH_INPUT_KEY,
        max_chars=512,
        autocomplete="off",
    )
    st.button(
        "Unlock local demo",
        type="primary",
        on_click=_authenticate_from_session,
        args=(settings,),
    )
    feedback = st.session_state.get(_AUTH_FEEDBACK_KEY)
    if feedback == AuthDecision.DENIED.value:
        st.warning("Access denied. Check the local token and try again.")
    elif feedback == AuthDecision.CONFIGURATION_ERROR.value:
        st.error("Local authentication is not configured correctly.")
    return False


def _render_readiness(report: ReadinessReport) -> None:
    st.subheader("Configuration readiness")
    st.caption("Boolean configuration check only — no managed provider call is made on page load.")
    if report.state is ReadinessState.READY:
        st.success("All M1 runtime credentials are configured.")
    elif report.state is ReadinessState.DEGRADED:
        st.warning(
            "The shell is available, but one or more runtime integrations are not configured."
        )
    else:
        st.error("Readiness is temporarily unavailable. No provider request was attempted.")

    for check in report.checks:
        icon = "✅" if check.configured else "⚠️"
        st.write(f"{icon} **{check.name}** — {check.detail}")


def _render_authenticated_shell(settings: AppSettings, report: ReadinessReport) -> None:
    st.header("ReviewLens foundation shell")
    st.caption(f"Local portfolio runtime · data mode: {settings.data_mode.value}")
    st.info(
        "M1 contains synthetic/configuration evidence only. "
        "No active analytics release is published yet."
    )
    _render_readiness(report)
    st.button("Sign out", on_click=_sign_out)


def main() -> None:
    st.set_page_config(page_title="ReviewLens", page_icon="🔎", layout="wide")
    st.title("ReviewLens local demo")
    try:
        settings = load_settings()
    except (OSError, ValueError, ValidationError):
        st.error(
            "Application configuration is unavailable. "
            "Validate config/config.toml and .env locally."
        )
        st.stop()

    secret_values = (
        (settings.app.auth_token.get_secret_value(),) if settings.app.auth_token is not None else ()
    )
    configure_logging(minimum_level=logging.INFO, secret_values=secret_values)
    logger = get_logger("app.streamlit")
    with bind_log_context(CorrelationContext(trace_id=new_trace_id())):
        if not _render_auth_gate(settings):
            logger.info("app.authentication_required")
            st.stop()
        report = collect_readiness(settings)
        logger.info("app.readiness_rendered", readiness_state=report.state.value)
        _render_authenticated_shell(settings, report)
