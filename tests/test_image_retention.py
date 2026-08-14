from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from reviewlens.deploy.images import (
    ImageRetentionError,
    LocalImage,
    apply_retention_plan,
    build_retention_plan,
    parse_image_listing,
)


def _image(repository: str, suffix: str, *, containers: int = 0) -> LocalImage:
    return LocalImage(
        repository=repository,
        tag=f"local-sha256-{suffix * 16}",
        image_id=suffix * 12,
        containers=containers,
    )


def test_retention_keeps_manifest_newest_and_container_images() -> None:
    records = (
        _image("reviewlens/airflow", "a"),
        _image("reviewlens/airflow", "b"),
        _image("reviewlens/airflow", "c", containers=1),
        _image("reviewlens/app", "d"),
        _image("reviewlens/app", "e"),
    )

    plan = build_retention_plan(
        records,
        manifest_references=(
            "reviewlens/app:local-sha256-ffffffffffffffff",
            "reviewlens/airflow:local-sha256-ffffffffffffffff",
        ),
    )

    assert plan.stale == (
        "reviewlens/airflow:local-sha256-bbbbbbbbbbbbbbbb",
        "reviewlens/app:local-sha256-eeeeeeeeeeeeeeee",
    )
    assert "reviewlens/airflow:local-sha256-cccccccccccccccc" in plan.protected


def test_listing_rejects_foreign_or_malformed_image_without_echoing_it() -> None:
    payload = json.dumps(
        {
            "Repository": "foreign/project",
            "Tag": "latest",
            "ID": "unsafe-value",
            "Containers": "0",
        }
    )

    with pytest.raises(ImageRetentionError) as error:
        parse_image_listing("reviewlens/airflow", payload)

    assert str(error.value) == ImageRetentionError.code
    assert "foreign" not in str(error.value)


def test_apply_uses_exact_non_force_references_only() -> None:
    commands: list[tuple[str, ...]] = []

    def runner(command: Sequence[str]) -> str:
        commands.append(tuple(command))
        return ""

    plan = build_retention_plan(
        (_image("reviewlens/airflow", "a"), _image("reviewlens/airflow", "b")),
        manifest_references=(
            "reviewlens/app:local-sha256-ffffffffffffffff",
            "reviewlens/airflow:local-sha256-ffffffffffffffff",
        ),
    )
    apply_retention_plan(plan, runner)

    assert commands == [
        ("docker", "image", "rm", "reviewlens/airflow:local-sha256-bbbbbbbbbbbbbbbb")
    ]
    assert all("--force" not in command for command in commands)


@pytest.mark.parametrize("keep_latest", [0, 6])
def test_retention_bound_fails_closed(keep_latest: int) -> None:
    with pytest.raises(ImageRetentionError):
        build_retention_plan(
            (),
            manifest_references=(
                "reviewlens/app:local-sha256-ffffffffffffffff",
                "reviewlens/airflow:local-sha256-ffffffffffffffff",
            ),
            keep_latest=keep_latest,
        )
