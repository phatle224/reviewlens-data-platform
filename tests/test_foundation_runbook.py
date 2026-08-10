from __future__ import annotations

import re
from pathlib import Path

RUNBOOK = Path("docs/runbooks/M1_FOUNDATION_OPERATIONS.md")


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _fenced_blocks(language: str) -> tuple[str, ...]:
    pattern = re.compile(rf"```{re.escape(language)}\n(.*?)\n```", re.DOTALL)
    return tuple(pattern.findall(_text()))


def test_foundation_runbook_covers_required_operator_workflows() -> None:
    text = _text()
    required = (
        "## 2. Prerequisites cho máy Windows sạch",
        "## 3. Bootstrap clean clone",
        "## 4. Cấu hình local và credential readiness",
        "## 5. Artifact tag và image lifecycle",
        "## 6. Start và verify local stack",
        "## 7. Test tiers",
        "## 8. Stop, restart và update source",
        "## 9. Cost stop",
        "## 10. Recovery và troubleshooting",
        "## 11. Break-glass security response",
        "## 12. Clean-machine solo dry-run checklist",
        "reviewlens-artifacts.exe --check",
        "docker compose config --quiet",
        "docker compose up -d --wait --wait-timeout 180 app metrics airflow",
        "docker compose down",
        "reviewlens-policy.exe --root .",
        "validate_project_status.py --root .",
        "--no-introspect",
        "--strict --require-hashes --disable-pip",
        "provider_calls_performed=false",
        "ALTER WAREHOUSE IF EXISTS REVIEWLENS_WH SUSPEND",
        "M1_CREDENTIAL_ROTATION.md",
    )

    assert all(value in text for value in required)


def test_image_cleanup_is_allowlisted_dry_run_first_and_never_forced() -> None:
    text = _text()
    powershell = "\n".join(_fenced_blocks("powershell"))

    assert "@('reviewlens/app', 'reviewlens/airflow')" in powershell
    assert '$_ -ne "${repository}:$currentTag"' in powershell
    assert "$staleReviewlensImages" in powershell
    assert "docker image rm @staleReviewlensImages" in powershell
    assert "docker image rm --force" not in powershell
    assert "docker image prune" not in powershell
    assert "docker system prune" not in powershell
    assert "Không dùng `docker system prune`" in text


def test_destructive_airflow_reset_requires_exact_confirmation() -> None:
    reset_block = next(
        block for block in _fenced_blocks("powershell") if "docker volume rm" in block
    )

    assert "Read-Host 'Type DELETE_LOCAL_AIRFLOW_METADATA to continue'" in reset_block
    assert "-ceq 'DELETE_LOCAL_AIRFLOW_METADATA'" in reset_block
    assert reset_block.index("-ceq 'DELETE_LOCAL_AIRFLOW_METADATA'") < reset_block.index(
        "docker volume rm reviewlens-local-airflow-runtime"
    )
    assert "docker compose down -v" not in _text()


def test_default_runbook_path_has_no_live_flags_secret_material_or_public_bind() -> None:
    text = _text()
    code = "\n".join((*_fenced_blocks("powershell"), *_fenced_blocks("sql")))
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    forbidden = (
        "REVIEWLENS_RUN_LIVE_",
        "sk-or-v1-",
        "AKIA",
        private_key_marker,
        "R2_SECRET_ACCESS_KEY=",
        "OPENROUTER_API_KEY=",
        "0.0.0.0",  # noqa: S104 - forbidden-bind assertion
        "docker compose down -v",
        "Remove-Item -Recurse",
    )

    assert not any(value in code for value in forbidden)
    assert "Không chạy hàng loạt live tests" in text
    assert "không public" in text.lower()


def test_runbook_relative_links_resolve() -> None:
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", _text())
    relative_links = [link for link in links if "://" not in link and not link.startswith("#")]

    assert relative_links
    for link in relative_links:
        target = (RUNBOOK.parent / link.split("#", maxsplit=1)[0]).resolve()
        assert target.exists(), link


def test_clean_machine_checklist_preserves_data_cost_and_evidence_boundaries() -> None:
    text = _text()
    checklist = text.split("## 12. Clean-machine solo dry-run checklist", maxsplit=1)[1]

    for expected in (
        "private keys nằm ngoài clone",
        "App/metrics/Airflow healthy trên 127.0.0.1",
        "Final image UID là 10001 và 50000",
        "Không có cloud call, Olist upload, paid AI call hoặc secret trong evidence",
        "Chỉ đánh dấu TC-M1-027 `PASS` sau một",
    ):
        assert expected in checklist
