#!/usr/bin/env python3
"""Validate ReviewLens status, phase checklist, and test artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


WORK_STATUSES = {"DONE", "PARTIAL", "BLOCKED", "DEFERRED", "NOT_STARTED"}
TEST_STATUSES = {"PASS", "FAIL", "PENDING", "BLOCKED", "DEFERRED", "SKIPPED"}
REQUIRED_STATUS_HEADINGS = (
    "## Tổng quan",
    "## Tiến độ theo phase",
    "## Kết quả phiên gần nhất",
    "## Kiểm thử",
    "## Blocker và rủi ro",
    "## Chi phí và tài nguyên",
    "## Input cần từ chủ project",
    "## Việc tiếp theo",
    "## Tài liệu nguồn",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def table_statuses(text: str, id_pattern: str, allowed: set[str]) -> tuple[dict[str, str], list[str]]:
    found: dict[str, str] = {}
    errors: list[str] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        identifier = re.search(id_pattern, line)
        if not identifier:
            continue
        status_tokens = re.findall(r"`([A-Z_]+)`", line)
        status = next((token for token in status_tokens if token in allowed), None)
        item_id = identifier.group(0)
        if status is None and item_id in found:
            continue
        if status is None:
            errors.append(f"missing or invalid status: {item_id}")
        elif item_id in found and found[item_id] != status:
            errors.append(
                f"conflicting statuses for {item_id}: {found[item_id]} vs {status}"
            )
        elif item_id in found:
            continue
        else:
            found[item_id] = status
    return found, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    docs = root / "docs"
    errors: list[str] = []
    warnings: list[str] = []

    status_path = docs / "PROJECT_STATUS.md"
    if not status_path.is_file():
        errors.append("missing docs/PROJECT_STATUS.md")
    else:
        status_text = read_text(status_path)
        for heading in REQUIRED_STATUS_HEADINGS:
            if heading not in status_text:
                errors.append(f"PROJECT_STATUS.md missing heading: {heading}")
        if not re.search(r"\|\s*Phase hiện tại\s*\|\s*`M[0-8]`", status_text):
            errors.append("PROJECT_STATUS.md must declare Phase hiện tại as `M0`...`M8`")
        if not re.search(r"\|\s*Cập nhật lần cuối\s*\|\s*\d{4}-\d{2}-\d{2}", status_text):
            errors.append("PROJECT_STATUS.md must contain an ISO last-updated date")

    phase_root = docs / "phases"
    phase_summaries: list[str] = []
    if not phase_root.is_dir():
        errors.append("missing docs/phases directory")
    else:
        phase_dirs = sorted(
            p for p in phase_root.iterdir() if p.is_dir() and re.fullmatch(r"M[0-8]", p.name)
        )
        for phase_dir in phase_dirs:
            phase = phase_dir.name
            required = {
                "README": phase_dir / "README.md",
                "checklist": phase_dir / f"{phase}_CHECKLIST.md",
                "tests": phase_dir / f"{phase}_TEST_CASES.md",
            }
            missing = [label for label, path in required.items() if not path.is_file()]
            if missing:
                errors.append(f"{phase} missing artifacts: {', '.join(missing)}")
                continue

            checklist_text = read_text(required["checklist"])
            tests_text = read_text(required["tests"])
            work, work_errors = table_statuses(checklist_text, rf"IMP-{phase}-\d{{3}}", WORK_STATUSES)
            tests, test_errors = table_statuses(tests_text, rf"TC-{phase}-\d{{3}}", TEST_STATUSES)
            errors.extend(f"{phase}: {item}" for item in work_errors + test_errors)
            if not work:
                errors.append(f"{phase} checklist has no work-item rows")
            if not tests:
                errors.append(f"{phase} test file has no test-case rows")

            phase_status_match = re.search(
                r"\|\s*Phase status\s*\|\s*`([A-Z_]+)`", checklist_text
            )
            phase_status = phase_status_match.group(1) if phase_status_match else "UNKNOWN"
            if not phase_status_match:
                errors.append(f"{phase} checklist is missing Phase status")

            if phase_status == "COMPLETE":
                incomplete = {key: value for key, value in work.items() if value not in {"DONE", "DEFERRED"}}
                unresolved = {key: value for key, value in tests.items() if value in {"FAIL", "PENDING", "BLOCKED"}}
                if incomplete:
                    errors.append(f"{phase} is COMPLETE but work remains: {incomplete}")
                if unresolved:
                    errors.append(f"{phase} is COMPLETE but tests are unresolved: {unresolved}")

            work_counts = {value: list(work.values()).count(value) for value in sorted(WORK_STATUSES)}
            test_counts = {value: list(tests.values()).count(value) for value in sorted(TEST_STATUSES)}
            phase_summaries.append(
                f"{phase}: phase={phase_status}, work={len(work)} {work_counts}, tests={len(tests)} {test_counts}"
            )

    plan_path = docs / "IMPLEMENTATION_PLAN.md"
    if not plan_path.is_file():
        errors.append("missing docs/IMPLEMENTATION_PLAN.md")
    else:
        plan_text = read_text(plan_path)
        for phase_dir in sorted(p for p in phase_root.glob("M[0-8]") if p.is_dir()):
            phase = phase_dir.name
            checklist_path = phase_dir / f"{phase}_CHECKLIST.md"
            if not checklist_path.is_file():
                continue
            checklist_ids, _ = table_statuses(
                read_text(checklist_path), rf"IMP-{phase}-\d{{3}}", WORK_STATUSES
            )
            planned_ids = set(re.findall(rf"IMP-{phase}-\d{{3}}", plan_text))
            missing_ids = planned_ids - set(checklist_ids)
            extra_ids = set(checklist_ids) - planned_ids
            if missing_ids:
                errors.append(f"{phase} checklist missing planned IDs: {sorted(missing_ids)}")
            if extra_ids:
                warnings.append(f"{phase} checklist has IDs absent from plan: {sorted(extra_ids)}")

    print(f"ReviewLens status validation: {root}")
    for summary in phase_summaries:
        print(f"  {summary}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"PASS: 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
