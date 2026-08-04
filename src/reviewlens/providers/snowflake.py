"""Secret-safe Snowflake adapter and M1 foundation helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

import snowflake.connector

from reviewlens.config import R2Config, SnowflakeConfig


class _SnowflakeCursor(Protocol):
    def execute(self, command: str) -> _SnowflakeCursor: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


class _SnowflakeConnection(Protocol):
    def cursor(self) -> _SnowflakeCursor: ...

    def close(self) -> None: ...


class SnowflakeProviderError(RuntimeError):
    """A sanitized provider error that never includes SQL or credentials."""


_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]*$")
_STAGE_KEY = re.compile(r"^[A-Za-z0-9_./=-]+$")


def _identifier(value: str) -> str:
    normalized = value.upper()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"unsafe Snowflake identifier: {value!r}")
    return normalized


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def split_sql_statements(source: str) -> tuple[str, ...]:
    """Split foundation SQL while preserving semicolons inside quoted literals."""

    uncommented = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("--")
    )
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(uncommented):
        character = uncommented[index]
        next_character = uncommented[index + 1] if index + 1 < len(uncommented) else ""
        if character == "'" and not in_double_quote:
            current.append(character)
            if in_single_quote and next_character == "'":
                current.append(next_character)
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif character == '"' and not in_single_quote:
            current.append(character)
            if in_double_quote and next_character == '"':
                current.append(next_character)
                index += 2
                continue
            in_double_quote = not in_double_quote
        elif character == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(character)
        index += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return tuple(statements)


def render_r2_stage_sql(
    *,
    database: str,
    bucket: str,
    endpoint: str,
    access_key_id: str,
    secret_access_key: str,
) -> str:
    """Render sensitive stage DDL for immediate execution; callers must not log it."""

    database_name = _identifier(database)
    endpoint_host = urlparse(endpoint).netloc
    if not endpoint_host.endswith(".r2.cloudflarestorage.com"):
        raise ValueError("R2 endpoint must be a Cloudflare S3-compatible host")
    if not bucket or "/" in bucket:
        raise ValueError("R2 bucket must be a non-empty bucket name")
    return f"""CREATE OR REPLACE STAGE {database_name}.BRONZE.R2_STAGE
URL = {_sql_literal(f"s3compat://{bucket}/")}
ENDPOINT = {_sql_literal(endpoint_host)}
CREDENTIALS = (
  AWS_KEY_ID = {_sql_literal(access_key_id)}
  AWS_SECRET_KEY = {_sql_literal(secret_access_key)}
)
DIRECTORY = (ENABLE = TRUE AUTO_REFRESH = FALSE)
COMMENT = 'ReviewLens private R2 stage; synthetic cloud data only'"""


class SnowflakeClient:
    """Small connection boundary used by provisioning, ingestion and tests."""

    def __init__(self, connection: _SnowflakeConnection) -> None:
        self._connection = connection

    @classmethod
    def connect_bootstrap(cls, config: SnowflakeConfig) -> SnowflakeClient:
        """Connect without assuming that the target role/database/warehouse exists."""

        config.require_live_credentials()
        kwargs: dict[str, Any] = {
            "account": config.account,
            "user": config.user,
            "autocommit": True,
            "session_parameters": {
                "QUERY_TAG": "reviewlens:m1_foundation:synthetic",
                "STATEMENT_TIMEOUT_IN_SECONDS": 120,
            },
        }
        if config.private_key_path:
            kwargs.update(
                authenticator="SNOWFLAKE_JWT",
                private_key_file=config.private_key_path,
            )
        elif config.password is not None:
            kwargs["password"] = config.password.get_secret_value()
        try:
            connection = snowflake.connector.connect(**kwargs)
        except Exception:
            raise SnowflakeProviderError("Snowflake bootstrap connection failed") from None
        return cls(cast(_SnowflakeConnection, connection))

    def close(self) -> None:
        self._connection.close()

    def execute(self, statement: str, *, operation: str = "Snowflake statement") -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(statement)
        except Exception:
            raise SnowflakeProviderError(f"{operation} failed") from None
        finally:
            cursor.close()

    def execute_all(
        self,
        statements: Iterable[str],
        *,
        operation: str = "Snowflake statement",
    ) -> None:
        for statement in statements:
            self.execute(statement, operation=operation)

    def query_all(
        self,
        statement: str,
        *,
        operation: str = "Snowflake query",
    ) -> list[tuple[Any, ...]]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(statement)
            return cursor.fetchall()
        except Exception:
            raise SnowflakeProviderError(f"{operation} failed") from None
        finally:
            cursor.close()

    def apply_foundation(self, ddl_path: Path) -> None:
        self.apply_sql_file(ddl_path, operation="Snowflake foundation statement")

    def apply_sql_file(self, ddl_path: Path, *, operation: str) -> None:
        """Execute a committed, secret-free SQL artifact statement by statement."""

        statements = split_sql_statements(ddl_path.read_text(encoding="utf-8"))
        self.execute_all(statements, operation=operation)

    def create_or_replace_r2_stage(
        self,
        *,
        snowflake: SnowflakeConfig,
        r2: R2Config,
    ) -> None:
        r2.require_live_credentials()
        if r2.endpoint is None or r2.access_key_id is None or r2.secret_access_key is None:
            raise ValueError("R2 stage requires endpoint and scoped credentials")
        sensitive_statement = render_r2_stage_sql(
            database=snowflake.database,
            bucket=r2.bucket,
            endpoint=r2.endpoint,
            access_key_id=r2.access_key_id.get_secret_value(),
            secret_access_key=r2.secret_access_key.get_secret_value(),
        )
        self.execute(sensitive_statement, operation="sensitive R2 stage creation")

    def list_stage_path(self, *, database: str, key: str) -> list[tuple[Any, ...]]:
        if not _STAGE_KEY.fullmatch(key) or ".." in key:
            raise ValueError("unsafe R2 stage key")
        stage = f"{_identifier(database)}.BRONZE.R2_STAGE"
        return self.query_all(f"LIST @{stage}/{key}", operation="R2 stage LIST")

    def suspend_warehouse(self, warehouse: str) -> None:
        """Best-effort cleanup; safe to call even when setup failed partway."""

        try:
            self.execute(
                f"ALTER WAREHOUSE {_identifier(warehouse)} SUSPEND",
                operation="Snowflake warehouse suspend",
            )
        except SnowflakeProviderError:
            # A never-started/already-suspended warehouse needs no further cleanup.
            return
