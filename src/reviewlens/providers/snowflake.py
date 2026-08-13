"""Secret-safe Snowflake adapter and M1 foundation helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

import snowflake.connector

from reviewlens.config import (
    IdentityConfig,
    R2Config,
    SnowflakeConfig,
    SnowflakeServiceIdentityConfig,
)


class _SnowflakeCursor(Protocol):
    def execute(self, command: str) -> _SnowflakeCursor: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...

    @property
    def sfqid(self) -> str | None: ...


class _SnowflakeConnection(Protocol):
    def cursor(self) -> _SnowflakeCursor: ...

    def close(self) -> None: ...


class SnowflakeProviderError(RuntimeError):
    """A sanitized provider error that never includes SQL or credentials."""


@dataclass(frozen=True, slots=True)
class SnowflakeQueryResult:
    """Provider-neutral query identity and rows for auditable operations."""

    query_id: str
    rows: tuple[tuple[Any, ...], ...]


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
COMMENT = 'ReviewLens private R2 stage; approved private or synthetic data only'"""


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

    @classmethod
    def connect_service(
        cls,
        config: SnowflakeConfig,
        identity: SnowflakeServiceIdentityConfig,
        *,
        credential_values: Mapping[str, str],
    ) -> SnowflakeClient:
        """Connect one runtime identity with its exact role and no secondary roles."""

        if not config.account:
            raise ValueError("Snowflake service access requires SNOWFLAKE_ACCOUNT")
        private_key_path = credential_values.get(identity.private_key_path_env)
        if not private_key_path:
            raise ValueError(
                f"Snowflake {identity.service.value} access requires "
                f"{identity.private_key_path_env}"
            )
        kwargs: dict[str, Any] = {
            "account": config.account,
            "user": identity.user,
            "authenticator": "SNOWFLAKE_JWT",
            "private_key_file": private_key_path,
            "database": config.database,
            "warehouse": identity.warehouse,
            "role": identity.role,
            "autocommit": True,
            "session_parameters": {
                "QUERY_TAG": f"reviewlens:{identity.service.value}:runtime",
                "STATEMENT_TIMEOUT_IN_SECONDS": 120,
            },
        }
        passphrase = credential_values.get(identity.private_key_passphrase_env)
        if passphrase:
            kwargs["private_key_file_pwd"] = passphrase
        try:
            connection = snowflake.connector.connect(**kwargs)
            client = cls(cast(_SnowflakeConnection, connection))
            secondary_roles = client.query_all(
                "SELECT CURRENT_SECONDARY_ROLES()",
                operation="Snowflake service secondary-role verification",
            )
            secondary_role_state = json.loads(str(secondary_roles[0][0]))
            if secondary_role_state.get("roles") or secondary_role_state.get("value"):
                raise SnowflakeProviderError("Snowflake service secondary roles are active")
        except Exception:
            if "connection" in locals():
                with suppress(Exception):
                    connection.close()
            raise SnowflakeProviderError("Snowflake service connection failed") from None
        return client

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

    def execute_with_results(
        self,
        statement: str,
        *,
        operation: str = "Snowflake statement",
    ) -> SnowflakeQueryResult:
        """Execute once and return the provider query ID plus its result rows."""

        cursor = self._connection.cursor()
        try:
            cursor.execute(statement)
            query_id = getattr(cursor, "sfqid", None)
            if not isinstance(query_id, str) or not query_id:
                raise SnowflakeProviderError(f"{operation} returned no query ID")
            return SnowflakeQueryResult(query_id=query_id, rows=tuple(cursor.fetchall()))
        except SnowflakeProviderError:
            raise
        except Exception:
            raise SnowflakeProviderError(f"{operation} failed") from None
        finally:
            cursor.close()

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
        self._grant_r2_stage_usage(snowflake.database)

    def create_or_replace_r2_runtime_stage(
        self,
        *,
        snowflake: SnowflakeConfig,
        r2: R2Config,
        identities: IdentityConfig,
        credential_values: Mapping[str, str],
    ) -> None:
        """Create the external stage with its dedicated read-only R2 identity."""

        account_id = r2.account_id or credential_values.get("R2_ACCOUNT_ID")
        access_key_id = credential_values.get(identities.r2_stage_access_key_env)
        secret_access_key = credential_values.get(identities.r2_stage_secret_key_env)
        if not account_id or not access_key_id or not secret_access_key:
            raise ValueError("R2 runtime stage requires account ID and stage credentials")
        sensitive_statement = render_r2_stage_sql(
            database=snowflake.database,
            bucket=r2.bucket,
            endpoint=f"https://{account_id}.r2.cloudflarestorage.com",
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
        self.execute(sensitive_statement, operation="sensitive R2 runtime stage creation")
        self._grant_r2_stage_usage(snowflake.database)

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

    def _grant_r2_stage_usage(self, database: str) -> None:
        self.execute(
            f"GRANT USAGE ON STAGE {_identifier(database)}.BRONZE.R2_STAGE TO ROLE INGEST_ROLE",
            operation="R2 stage ingestion grant",
        )
