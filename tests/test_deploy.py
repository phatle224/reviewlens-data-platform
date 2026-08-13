from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.deploy.artifacts import expected_manifest, load_manifest, source_files


def test_container_bases_are_digest_pinned_and_runtime_users_are_non_root() -> None:
    app = Path("Dockerfile.app").read_text(encoding="utf-8")
    airflow = Path("Dockerfile.airflow").read_text(encoding="utf-8")
    digest_reference = re.compile(r"^FROM [^\s]+@sha256:[0-9a-f]{64}(?: AS \w+)?$", re.MULTILINE)

    assert len(digest_reference.findall(app)) == 2
    assert len(digest_reference.findall(airflow)) == 2
    assert "USER 10001:10001" in app
    assert "USER airflow" in airflow
    assert "USER 50000:0" in airflow
    assert "USER root\n" in airflow
    assert airflow.rfind("USER 50000:0") > airflow.rfind("USER root")
    assert 'ENTRYPOINT ["/opt/reviewlens/deploy/airflow-entrypoint.sh"]' in airflow
    assert ":latest" not in app + airflow


def test_compose_is_local_only_hardened_and_excludes_vulnerable_chroma() -> None:
    compose_text = Path("compose.yaml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    services = compose["services"]

    assert set(services) == {"app", "metrics", "airflow"}
    assert "chroma" not in compose_text.lower()
    assert all(
        str(port).startswith("127.0.0.1:")
        for service in services.values()
        for port in service.get("ports", [])
    )
    for service in services.values():
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["restart"] == "no"
    assert all("latest" not in service["image"] for service in services.values())
    assert services["app"]["env_file"][0]["path"] == ".env"
    assert services["metrics"]["env_file"][0]["path"] == ".env"
    assert services["airflow"]["env_file"][0]["path"] == ".env"
    assert (
        services["airflow"]["environment"]["REVIEWLENS_ENABLE_OLIST_PIPELINE"]
        == "${REVIEWLENS_ENABLE_OLIST_PIPELINE:-0}"
    )
    airflow_targets = {
        volume["target"] for volume in services["airflow"]["volumes"] if isinstance(volume, dict)
    }
    assert "/opt/reviewlens/archive" in airflow_targets
    assert "/run/reviewlens/keys/ingestion.p8" in airflow_targets
    assert "/run/reviewlens/keys/transform.p8" in airflow_targets
    assert "127.0.0.1:9108/healthz" in services["metrics"]["healthcheck"]["test"][-1]
    assert "config/environments" not in compose_text


def test_airflow_image_contains_runtime_code_and_locked_dependencies() -> None:
    airflow = Path("Dockerfile.airflow").read_text(encoding="utf-8")

    assert 'ENV PYTHONPATH="/opt/reviewlens/src"' in airflow
    assert "uv export --locked --no-dev --group airflow" in airflow
    assert "uv pip install --system" in airflow
    assert "pip uninstall --yes chardet" not in airflow
    assert '"chardet==5.2.0"' in airflow
    assert "COPY --chown=airflow:root src /opt/reviewlens/src" in airflow
    assert "COPY --chown=airflow:root config /opt/reviewlens/config" in airflow
    assert "docs/DATA_ATTRIBUTION.md" in airflow


def test_artifact_manifest_matches_all_declared_build_inputs() -> None:
    root = Path.cwd()
    manifest = load_manifest(root)

    assert manifest == expected_manifest(root)
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"])
    assert manifest["artifact_tag"] == f"local-sha256-{manifest['source_sha256'][:16]}"
    assert manifest["deployment_scope"] == "local-demo-only"
    assert Path("deploy/artifacts.lock.json") not in source_files(root)


def test_artifact_manifest_detects_source_change(tmp_path: Path) -> None:
    root = Path.cwd()
    for relative in source_files(root):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    before = expected_manifest(tmp_path)
    (tmp_path / "README.md").write_text("changed synthetic input", encoding="utf-8")

    assert expected_manifest(tmp_path)["source_sha256"] != before["source_sha256"]


def test_artifact_manifest_contains_no_timestamp_or_host_path() -> None:
    serialized = json.dumps(load_manifest(Path.cwd()), sort_keys=True)

    assert "created_at" not in serialized
    assert str(Path.cwd()) not in serialized


@pytest.mark.parametrize("filename", [".env", "snowflake_key.p8", "sample.csv"])
def test_docker_context_excludes_secret_key_and_row_data_patterns(filename: str) -> None:
    ignore = Path(".dockerignore").read_text(encoding="utf-8").splitlines()

    suffix = Path(filename).suffix
    assert filename in ignore or f"*{suffix}" in ignore
