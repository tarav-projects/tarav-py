"""One-boundary migration from Diagram.View schema v1 to v2."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from tarav._core.persistence import atomic_write_json

from .views import (
    VIEW_CLASS,
    VIEW_CONFIGURATION_CLASS,
    VIEW_MANIFEST_TYPE,
    VIEW_REPOSITORY_CLASS,
    VIEW_REPOSITORY_FILENAME,
    VIEW_SCHEMA_VERSION,
    DiagramViewError,
)

JsonObject = dict[str, Any]
LEGACY_VIEW_MANIFEST_TYPE = "Diagram.View.Annotation"


@dataclass(frozen=True, slots=True)
class ViewMigrationReport:
    source_commit: str
    views: int
    line_editions: int

    def to_dict(self) -> JsonObject:
        return {
            "source_commit": self.source_commit,
            "views": self.views,
            "line_editions": self.line_editions,
        }


def migrate_view_repository_v1(root: Path) -> ViewMigrationReport:
    """Advance one complete View repository without committing the result."""

    resolved = root.expanduser().resolve()
    if not (resolved / ".git").is_dir():
        raise DiagramViewError(
            f"Diagram.View repository is not initialized: {resolved}"
        )
    repository_path = resolved / VIEW_REPOSITORY_FILENAME
    repository = _read(repository_path)
    _expect_schema(
        repository,
        expected_class=VIEW_REPOSITORY_CLASS,
        path=repository_path,
    )
    source_commit = _git(resolved, "rev-parse", "HEAD")

    views = 0
    line_editions = 0
    for view_root in sorted(resolved.iterdir()):
        manifest_path = view_root / "manifest.json"
        if not view_root.is_dir() or not manifest_path.is_file():
            continue
        config_path = view_root / "config.json"
        state_path = view_root / "view.json"
        manifest = _read(manifest_path)
        config = _read(config_path)
        state = _read(state_path)
        if (
            manifest.get("type") != LEGACY_VIEW_MANIFEST_TYPE
            or manifest.get("schema_version") != 1
        ):
            raise DiagramViewError(
                f"Diagram.View manifest is not schema v1: {manifest_path}"
            )
        _expect_schema(
            config,
            expected_class=VIEW_CONFIGURATION_CLASS,
            path=config_path,
        )
        _expect_schema(state, expected_class=VIEW_CLASS, path=state_path)

        manifest["type"] = VIEW_MANIFEST_TYPE
        manifest["schema_version"] = VIEW_SCHEMA_VERSION
        config["schema_version"] = VIEW_SCHEMA_VERSION
        state["schema_version"] = VIEW_SCHEMA_VERSION
        for block_index, block in enumerate(_array(state.get("blocks"), state_path)):
            disclosure = _object(
                block.get("disclosure"),
                path=state_path,
                field=f"blocks[{block_index}].disclosure",
            )
            for line_index, line in enumerate(
                _array(disclosure.get("lines"), state_path)
            ):
                for edition_index, edition in enumerate(
                    _array(line.get("editions"), state_path)
                ):
                    if "edition_id" in edition or "annotation_id" not in edition:
                        raise DiagramViewError(
                            "View Line edition is not unambiguously schema v1: "
                            f"{state_path}:blocks[{block_index}].disclosure.lines"
                            f"[{line_index}].editions[{edition_index}]"
                        )
                    edition["edition_id"] = edition.pop("annotation_id")
                    line_editions += 1

        atomic_write_json(manifest_path, manifest, ensure_ascii=False)
        atomic_write_json(config_path, config, ensure_ascii=False)
        atomic_write_json(state_path, state, ensure_ascii=False)
        views += 1

    repository["schema_version"] = VIEW_SCHEMA_VERSION
    atomic_write_json(repository_path, repository, ensure_ascii=False)
    return ViewMigrationReport(source_commit, views, line_editions)


def _expect_schema(
    value: JsonObject,
    *,
    expected_class: str,
    path: Path,
) -> None:
    if value.get("class") != expected_class or value.get("schema_version") != 1:
        raise DiagramViewError(f"Diagram.View record is not schema v1: {path}")


def _read(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagramViewError(f"Cannot read Diagram.View JSON {path}: {exc}") from exc
    return _object(value, path=path, field="record")


def _object(value: object, *, path: Path, field: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DiagramViewError(f"Diagram.View {field} is not an object: {path}")
    return value


def _array(value: object, path: Path) -> list[JsonObject]:
    if not isinstance(value, list):
        raise DiagramViewError(f"Diagram.View value is not an array: {path}")
    return [
        _object(item, path=path, field=f"array[{index}]")
        for index, item in enumerate(value)
    ]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise DiagramViewError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    args = parser.parse_args(argv)
    report = migrate_view_repository_v1(Path(args.repository))
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
