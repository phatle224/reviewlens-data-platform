from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from reviewlens.config import load_settings
from reviewlens.security.snowflake_rotation import (
    ROTATION_SMOKE_CONFIRMATION,
    ROTATION_SMOKE_KEY_PAIR_NAME,
    RotationSafetyError,
    build_rotation_smoke_plan,
    generate_ephemeral_rsa_key_pair,
    render_add_smoke_key_sql,
    render_remove_smoke_key_sql,
    render_rotate_smoke_key_sql,
    render_show_key_pairs_sql,
    require_rotation_confirmation,
)

EMPTY_ENV = Path("tests/fixtures/.missing-snowflake-rotation.env")
LIVE_TEST = Path("tests/live/test_snowflake_rotation_live.py")


def test_rotation_plan_is_pinned_to_read_only_analytics_canary() -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)

    plan = build_rotation_smoke_plan(settings)

    assert plan.identity.user == "REVIEWLENS_ANALYTICS_SVC"
    assert plan.identity.role == "ANALYST_ROLE"
    assert plan.key_pair_name == ROTATION_SMOKE_KEY_PAIR_NAME
    assert plan.rotated_key_grace_hours == 0
    assert plan.days_to_expiry == 1


@pytest.mark.parametrize(
    "confirmation",
    [None, "", "yes", ROTATION_SMOKE_CONFIRMATION.lower(), f"{ROTATION_SMOKE_CONFIRMATION} "],
)
def test_rotation_confirmation_fails_closed(confirmation: str | None) -> None:
    with pytest.raises(RotationSafetyError, match="exact"):
        require_rotation_confirmation(confirmation)


def test_rotation_confirmation_accepts_only_exact_value() -> None:
    require_rotation_confirmation(ROTATION_SMOKE_CONFIRMATION)


def test_ephemeral_key_generation_stays_in_requested_directory(tmp_path: Path) -> None:
    generated = generate_ephemeral_rsa_key_pair(tmp_path, stem="old_canary")

    assert generated.private_key_path.parent == tmp_path
    assert generated.private_key_path.suffix == ".p8"
    private_key_marker = b"-----BEGIN " + b"PRIVATE KEY-----"
    assert generated.private_key_path.read_bytes().startswith(private_key_marker)
    assert "BEGIN" not in generated.public_key_body
    assert "\n" not in generated.public_key_body


def test_ephemeral_key_generation_rejects_unsafe_filename(tmp_path: Path) -> None:
    with pytest.raises(RotationSafetyError, match="filename"):
        generate_ephemeral_rsa_key_pair(tmp_path, stem="../escape")


def test_rotation_sql_is_exactly_scoped_and_secret_free() -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    plan = build_rotation_smoke_plan(settings)
    public_key = "QUJDREVGRw=="

    add_sql = render_add_smoke_key_sql(plan, public_key)
    rotate_sql = render_rotate_smoke_key_sql(plan, public_key)

    assert add_sql == (
        "ALTER USER IF EXISTS REVIEWLENS_ANALYTICS_SVC ADD KEY PAIR "
        "REVIEWLENS_ROTATION_SMOKE PUBLIC_KEY = 'QUJDREVGRw==' "
        "ROLE_RESTRICTION = 'ANALYST_ROLE' DAYS_TO_EXPIRY = 1 "
        "COMMENT = 'ReviewLens M1 isolated rotation smoke; safe to remove'"
    )
    assert rotate_sql == (
        "ALTER USER IF EXISTS REVIEWLENS_ANALYTICS_SVC ROTATE KEY PAIR "
        "REVIEWLENS_ROTATION_SMOKE PUBLIC_KEY = 'QUJDREVGRw==' "
        "EXPIRE_ROTATED_KEY_PAIR_AFTER_HOURS = 0"
    )
    assert render_remove_smoke_key_sql(plan) == (
        "ALTER USER IF EXISTS REVIEWLENS_ANALYTICS_SVC REMOVE KEY PAIR REVIEWLENS_ROTATION_SMOKE"
    )
    assert render_show_key_pairs_sql(plan) == (
        "SHOW USER KEY PAIRS FOR USER REVIEWLENS_ANALYTICS_SVC"
    )
    assert "PRIVATE" not in add_sql + rotate_sql


@pytest.mark.parametrize("public_key", ["", "abc' OR TRUE", "-----BEGIN PUBLIC KEY-----"])
def test_rotation_sql_rejects_unsafe_public_key(public_key: str) -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    plan = build_rotation_smoke_plan(settings)

    with pytest.raises(RotationSafetyError, match="public key"):
        render_add_smoke_key_sql(plan, public_key)


def test_rotation_plan_rejects_weakened_safety_limits() -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    plan = build_rotation_smoke_plan(settings)

    with pytest.raises(RotationSafetyError, match="immediately"):
        render_rotate_smoke_key_sql(replace(plan, rotated_key_grace_hours=1), "QUJD")
    with pytest.raises(RotationSafetyError, match="one day"):
        render_add_smoke_key_sql(replace(plan, days_to_expiry=2), "QUJD")


def test_live_rotation_requires_owner_opt_in_and_guaranteed_cleanup() -> None:
    text = LIVE_TEST.read_text(encoding="utf-8")

    assert "_require_owner_opt_in()" in text
    assert "REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION" in text
    assert "REVIEWLENS_SNOWFLAKE_ROTATION_CONFIRM" in text
    assert text.index("_require_owner_opt_in()", text.index("def test_")) < text.index(
        "SnowflakeClient.connect_bootstrap", text.index("def test_")
    )
    assert "finally:" in text
    assert "render_remove_smoke_key_sql(plan)" in text
    assert "bootstrap.suspend_warehouse(plan.identity.warehouse)" in text
    assert "TemporaryDirectory" in text
