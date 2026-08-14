"""Repository-scoped Docker image retention for the local ReviewLens demo."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reviewlens.config import project_root
from reviewlens.deploy.artifacts import expected_manifest, load_manifest

REVIEWLENS_IMAGE_REPOSITORIES = ("reviewlens/app", "reviewlens/airflow")
_TAG = re.compile(r"^local-sha256-[0-9a-f]{16}$")
_IMAGE_ID = re.compile(r"^(?:sha256:)?[0-9a-f]{12,64}$")


class ImageRetentionError(RuntimeError):
    """Sanitized local Docker retention failure."""

    code = "REVIEWLENS_IMAGE_RETENTION_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class LocalImage:
    repository: str
    tag: str
    image_id: str
    containers: int

    def __post_init__(self) -> None:
        if (
            self.repository not in REVIEWLENS_IMAGE_REPOSITORIES
            or _TAG.fullmatch(self.tag) is None
            or _IMAGE_ID.fullmatch(self.image_id) is None
            or self.containers < 0
        ):
            raise ImageRetentionError()

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"


@dataclass(frozen=True, slots=True)
class ImageRetentionPlan:
    protected: tuple[str, ...]
    stale: tuple[str, ...]


CommandRunner = Callable[[Sequence[str]], str]


def parse_image_listing(repository: str, output: str) -> tuple[LocalImage, ...]:
    if repository not in REVIEWLENS_IMAGE_REPOSITORIES:
        raise ImageRetentionError()
    records: list[LocalImage] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            payload: dict[str, Any] = json.loads(line)
            if payload.get("Tag") == "<none>":
                continue
            records.append(
                LocalImage(
                    repository=str(payload["Repository"]),
                    tag=str(payload["Tag"]),
                    image_id=str(payload["ID"]),
                    containers=int(payload["Containers"]),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ImageRetentionError() from error
    return tuple(records)


def build_retention_plan(
    records: Sequence[LocalImage],
    *,
    manifest_references: Sequence[str],
    keep_latest: int = 1,
) -> ImageRetentionPlan:
    if keep_latest < 1 or keep_latest > 5:
        raise ImageRetentionError()
    allowed_prefixes = tuple(f"{item}:" for item in REVIEWLENS_IMAGE_REPOSITORIES)
    if any(not item.startswith(allowed_prefixes) for item in manifest_references):
        raise ImageRetentionError()

    protected = set(manifest_references)
    for repository in REVIEWLENS_IMAGE_REPOSITORIES:
        repository_records = [item for item in records if item.repository == repository]
        protected.update(item.reference for item in repository_records[:keep_latest])
    protected.update(item.reference for item in records if item.containers > 0)

    stale = tuple(
        item.reference
        for item in records
        if item.reference not in protected and item.containers == 0
    )
    return ImageRetentionPlan(
        protected=tuple(sorted(protected)),
        stale=stale,
    )


def collect_images(runner: CommandRunner) -> tuple[LocalImage, ...]:
    records: list[LocalImage] = []
    for repository in REVIEWLENS_IMAGE_REPOSITORIES:
        output = runner(
            (
                "docker",
                "image",
                "ls",
                repository,
                "--format",
                "{{json .}}",
            )
        )
        records.extend(parse_image_listing(repository, output))
    return tuple(records)


def apply_retention_plan(plan: ImageRetentionPlan, runner: CommandRunner) -> None:
    for reference in plan.stale:
        if not reference.startswith(tuple(f"{item}:" for item in REVIEWLENS_IMAGE_REPOSITORIES)):
            raise ImageRetentionError()
        runner(("docker", "image", "rm", reference))


def _subprocess_runner(command: Sequence[str]) -> str:
    executable = shutil.which(command[0])
    if executable is None:
        raise ImageRetentionError()
    try:
        result = subprocess.run(  # noqa: S603 - resolved executable and fixed command tokens
            (executable, *command[1:]),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.SubprocessError as error:
        raise ImageRetentionError() from error
    return result.stdout


def _manifest_references(root: Path) -> tuple[str, ...]:
    manifest = load_manifest(root)
    if manifest != expected_manifest(root):
        raise ImageRetentionError()
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise ImageRetentionError()
    return tuple(str(images[key]) for key in ("app", "airflow"))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run/apply retention for ReviewLens images only; never prunes globally."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--keep-latest", type=int, default=1)
    parser.add_argument("--root", type=Path, default=project_root())
    args = parser.parse_args(argv)

    plan = build_retention_plan(
        collect_images(_subprocess_runner),
        manifest_references=_manifest_references(args.root.resolve()),
        keep_latest=args.keep_latest,
    )
    print(json.dumps({"apply": args.apply, "protected": plan.protected, "stale": plan.stale}))
    if args.apply:
        apply_retention_plan(plan, _subprocess_runner)


if __name__ == "__main__":
    main()
