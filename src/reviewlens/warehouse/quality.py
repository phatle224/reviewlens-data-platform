"""Privacy-safe data-quality gate contracts for M3 warehouse candidates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

DQ_CONTRACT_VERSION = "reviewlens-silver-dq-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_RULE_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_MODEL_NAME = re.compile(r"^SIL_[A-Z0-9_]{2,127}$")


class WarehouseQualityError(ValueError):
    """Sanitized DQ error that never echoes a failed value or identifier."""

    code = "WAREHOUSE_QUALITY_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class DQSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    WARN = "WARN"
    QUARANTINE = "QUARANTINE"


class DQGateStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 - quality outcome, not a credential
    PASS_WITH_FINDINGS = "PASS_WITH_FINDINGS"  # noqa: S105 - quality outcome
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True, order=True)
class DQFinding:
    """Aggregated metadata-only finding; raw keys and failed values are forbidden."""

    rule_id: str
    model_name: str
    grain_key_hash: str
    severity: DQSeverity
    failure_count: int = 1

    def __post_init__(self) -> None:
        if (
            _RULE_ID.fullmatch(self.rule_id) is None
            or _MODEL_NAME.fullmatch(self.model_name) is None
            or _HASH.fullmatch(self.grain_key_hash) is None
            or not isinstance(self.severity, DQSeverity)
            or isinstance(self.failure_count, bool)
            or self.failure_count < 1
        ):
            raise WarehouseQualityError()

    @property
    def canonical_key(self) -> tuple[str, str, str, str, int]:
        return (
            self.model_name,
            self.rule_id,
            self.grain_key_hash,
            self.severity.value,
            self.failure_count,
        )


@dataclass(frozen=True, slots=True)
class DQGateResult:
    status: DQGateStatus
    findings: tuple[DQFinding, ...]
    critical_failure_count: int
    warning_failure_count: int
    quarantined_failure_count: int
    fingerprint: str
    contract_version: str = DQ_CONTRACT_VERSION

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.findings, key=lambda item: item.canonical_key))
        expected_counts = (
            sum(item.failure_count for item in ordered if item.severity is DQSeverity.CRITICAL),
            sum(item.failure_count for item in ordered if item.severity is DQSeverity.WARN),
            sum(item.failure_count for item in ordered if item.severity is DQSeverity.QUARANTINE),
        )
        expected_status = (
            DQGateStatus.BLOCKED
            if expected_counts[0]
            else DQGateStatus.PASS_WITH_FINDINGS
            if ordered
            else DQGateStatus.PASS
        )
        counts = (
            self.critical_failure_count,
            self.warning_failure_count,
            self.quarantined_failure_count,
        )
        if (
            not isinstance(self.status, DQGateStatus)
            or any(isinstance(value, bool) or value < 0 for value in counts)
            or _HASH.fullmatch(self.fingerprint) is None
            or self.contract_version != DQ_CONTRACT_VERSION
            or self.findings != ordered
            or counts != expected_counts
            or self.status is not expected_status
            or self.fingerprint != _gate_fingerprint(self.status, ordered)
        ):
            raise WarehouseQualityError()

    @property
    def can_publish(self) -> bool:
        return self.status is not DQGateStatus.BLOCKED


def evaluate_quality_gate(findings: Iterable[DQFinding]) -> DQGateResult:
    """Return a deterministic gate result from privacy-safe failed-rule metadata."""

    ordered = tuple(sorted(findings, key=lambda item: item.canonical_key))
    if len({item.canonical_key for item in ordered}) != len(ordered):
        raise WarehouseQualityError()
    critical = sum(item.failure_count for item in ordered if item.severity is DQSeverity.CRITICAL)
    warning = sum(item.failure_count for item in ordered if item.severity is DQSeverity.WARN)
    quarantined = sum(
        item.failure_count for item in ordered if item.severity is DQSeverity.QUARANTINE
    )
    if critical:
        status = DQGateStatus.BLOCKED
    elif ordered:
        status = DQGateStatus.PASS_WITH_FINDINGS
    else:
        status = DQGateStatus.PASS
    return DQGateResult(
        status=status,
        findings=ordered,
        critical_failure_count=critical,
        warning_failure_count=warning,
        quarantined_failure_count=quarantined,
        fingerprint=_gate_fingerprint(status, ordered),
    )


def _gate_fingerprint(status: DQGateStatus, findings: tuple[DQFinding, ...]) -> str:
    payload = json.dumps(
        {
            "contract_version": DQ_CONTRACT_VERSION,
            "findings": [item.canonical_key for item in findings],
            "status": status.value,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()
