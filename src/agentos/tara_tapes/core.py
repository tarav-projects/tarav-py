from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path

TARA_TAPE_SPEC_VERSION = "0.1"
MANIFEST_FILENAME = "tape.json"
SEGMENTS_DIRNAME = "segments"
STAGE_DIRNAME = "stage"


def get_tara_tape_manifest_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / MANIFEST_FILENAME


def get_tara_tape_segments_dir(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / SEGMENTS_DIRNAME


def get_tara_tape_stage_dir(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / STAGE_DIRNAME


def _normalize_root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _normalize_tape_name(value: str | None, *, default_value: str) -> str:
    candidate = default_value if value is None else str(value).strip()
    if not candidate:
        raise CliError("tape_name must not be empty")
    return candidate


def _validate_iso8601_string(value: object, *, field_name: str) -> str:
    candidate = str(value).strip()
    if not candidate:
        raise CliError(f"{field_name} must not be empty")

    parse_candidate = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        datetime.fromisoformat(parse_candidate)
    except ValueError as exc:
        raise CliError(f"{field_name} must be a valid ISO 8601 string") from exc
    return candidate


def _validate_manifest_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CliError("tape manifest must be a JSON object")

    manifest = dict(payload)
    tape_name = manifest.get("tape_name")
    if not isinstance(tape_name, str) or not tape_name.strip():
        raise CliError("tape manifest field tape_name is required and must be a non-empty string")

    spec_version = manifest.get("tara_tape_spec")
    if spec_version != TARA_TAPE_SPEC_VERSION:
        raise CliError(
            "tape manifest field tara_tape_spec must be "
            f"'{TARA_TAPE_SPEC_VERSION}'"
        )

    created_at = manifest.get("created_at")
    if not isinstance(created_at, str):
        raise CliError("tape manifest field created_at is required and must be a string")
    manifest["created_at"] = _validate_iso8601_string(created_at, field_name="created_at")
    manifest["tape_name"] = tape_name.strip()
    return manifest


def load_tara_tape_manifest(root: Path | str) -> dict[str, object]:
    resolved_root = _normalize_root(root)
    if not resolved_root.exists():
        raise CliError(f"tape root does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise CliError(f"tape root is not a directory: {resolved_root}")

    manifest_path = get_tara_tape_manifest_path(resolved_root)
    if not manifest_path.exists():
        raise CliError(f"tape manifest does not exist: {manifest_path}")
    if not manifest_path.is_file():
        raise CliError(f"tape manifest path is not a file: {manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid tape manifest JSON: {exc}") from exc

    return _validate_manifest_payload(payload)


def save_tara_tape_manifest(root: Path | str, manifest: dict[str, object]) -> dict[str, object]:
    resolved_root = _normalize_root(root)
    if resolved_root.exists() and not resolved_root.is_dir():
        raise CliError(f"tape root is not a directory: {resolved_root}")
    resolved_root.mkdir(parents=True, exist_ok=True)

    validated_manifest = _validate_manifest_payload(manifest)
    manifest_path = get_tara_tape_manifest_path(resolved_root)
    manifest_path.write_text(json.dumps(validated_manifest, indent=2) + "\n", encoding="utf-8")
    return validated_manifest


def bootstrap_tara_tape(
    root: Path | str,
    *,
    tape_name: str | None = None,
    created_at: str | None = None,
    manifest_extra: dict[str, object] | None = None,
) -> tuple[dict[str, object], bool]:
    resolved_root = _normalize_root(root)
    if resolved_root.exists() and not resolved_root.is_dir():
        raise CliError(f"tape root is not a directory: {resolved_root}")

    resolved_root.mkdir(parents=True, exist_ok=True)
    get_tara_tape_segments_dir(resolved_root).mkdir(parents=True, exist_ok=True)
    get_tara_tape_stage_dir(resolved_root).mkdir(parents=True, exist_ok=True)

    manifest_path = get_tara_tape_manifest_path(resolved_root)
    if manifest_path.exists():
        return load_tara_tape_manifest(resolved_root), False

    manifest_payload = dict(manifest_extra or {})
    manifest_payload["tape_name"] = _normalize_tape_name(tape_name, default_value=resolved_root.name)
    manifest_payload["tara_tape_spec"] = TARA_TAPE_SPEC_VERSION
    manifest_payload["created_at"] = _validate_iso8601_string(
        created_at if created_at is not None else manifest_payload.get("created_at", utc_now_iso()),
        field_name="created_at",
    )

    return save_tara_tape_manifest(resolved_root, manifest_payload), True


def _require_tara_tape_layout(root: Path | str) -> tuple[Path, dict[str, object]]:
    resolved_root = _normalize_root(root)
    manifest = load_tara_tape_manifest(resolved_root)

    segments_dir = get_tara_tape_segments_dir(resolved_root)
    if not segments_dir.exists():
        raise CliError(f"segments directory does not exist: {segments_dir}")
    if not segments_dir.is_dir():
        raise CliError(f"segments path is not a directory: {segments_dir}")

    stage_dir = get_tara_tape_stage_dir(resolved_root)
    if not stage_dir.exists():
        raise CliError(f"stage directory does not exist: {stage_dir}")
    if not stage_dir.is_dir():
        raise CliError(f"stage path is not a directory: {stage_dir}")

    return resolved_root, manifest


def _normalize_writer_id(value: str) -> str:
    return validate_string_for_path(value, field_name="writer_id")


def _normalize_segment_name(value: str) -> str:
    normalized = validate_string_for_path(value, field_name="segment")
    if not normalized.endswith(".jsonl"):
        raise CliError("segment must end with .jsonl")
    return normalized


def append_tara_tape_stage_record(
    root: Path | str,
    *,
    writer_id: str,
    segment_name: str,
    record: object,
) -> Path:
    resolved_root, _manifest = _require_tara_tape_layout(root)
    normalized_writer_id = _normalize_writer_id(writer_id)
    normalized_segment_name = _normalize_segment_name(segment_name)

    try:
        record_line = json.dumps(record)
    except TypeError as exc:
        raise CliError(f"record is not JSON-serializable: {exc}") from exc

    stage_path = get_tara_tape_stage_dir(resolved_root) / normalized_writer_id / normalized_segment_name
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    with stage_path.open("a", encoding="utf-8") as handle:
        handle.write(record_line)
        handle.write("\n")
    return stage_path


def _read_jsonl_lines(path: Path) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line.strip():
                raise CliError(f"invalid blank JSONL line at {path}:{line_no}")
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise CliError(f"invalid JSONL record at {path}:{line_no}: {exc}") from exc
            lines.append(line)
    return lines


def _list_segment_paths(root: Path | str) -> list[Path]:
    resolved_root, _manifest = _require_tara_tape_layout(root)
    segments_dir = get_tara_tape_segments_dir(resolved_root)

    paths: list[Path] = []
    for candidate in sorted(segments_dir.iterdir(), key=lambda item: item.name):
        if not candidate.is_file():
            raise CliError(f"unexpected non-file entry under segments: {candidate}")
        if candidate.suffix != ".jsonl":
            raise CliError(f"unexpected non-jsonl file under segments: {candidate}")
        paths.append(candidate)
    return paths


def _list_stage_writer_dirs(root: Path | str) -> list[Path]:
    resolved_root, _manifest = _require_tara_tape_layout(root)
    stage_dir = get_tara_tape_stage_dir(resolved_root)

    writer_dirs: list[Path] = []
    for candidate in sorted(stage_dir.iterdir(), key=lambda item: item.name):
        if not candidate.is_dir():
            raise CliError(f"unexpected non-directory entry under stage: {candidate}")
        writer_dirs.append(candidate)
    return writer_dirs


def _list_stage_file_paths(root: Path | str) -> list[Path]:
    stage_file_paths: list[Path] = []
    for writer_dir in _list_stage_writer_dirs(root):
        for candidate in sorted(writer_dir.iterdir(), key=lambda item: item.name):
            if not candidate.is_file():
                raise CliError(f"unexpected non-file entry under stage writer directory: {candidate}")
            if candidate.suffix != ".jsonl":
                raise CliError(f"unexpected non-jsonl file under stage writer directory: {candidate}")
            stage_file_paths.append(candidate)
    return stage_file_paths


def commit_tara_tape_stage(root: Path | str) -> dict[str, object]:
    resolved_root, _manifest = _require_tara_tape_layout(root)
    stage_dir = get_tara_tape_stage_dir(resolved_root)
    segments_dir = get_tara_tape_segments_dir(resolved_root)

    committed_record_count = 0
    processed_stage_file_count = 0
    touched_segments: set[str] = set()
    touched_writers: set[str] = set()

    for writer_dir in _list_stage_writer_dirs(resolved_root):
        writer_touched = False
        for stage_path in sorted(writer_dir.iterdir(), key=lambda item: item.name):
            if not stage_path.is_file():
                raise CliError(f"unexpected non-file entry under stage writer directory: {stage_path}")
            if stage_path.suffix != ".jsonl":
                raise CliError(f"unexpected non-jsonl file under stage writer directory: {stage_path}")

            lines = _read_jsonl_lines(stage_path)
            if lines:
                segment_path = segments_dir / stage_path.name
                with segment_path.open("a", encoding="utf-8") as handle:
                    for line in lines:
                        handle.write(line)
                        handle.write("\n")
                committed_record_count += len(lines)
                touched_segments.add(stage_path.name)
            stage_path.unlink()
            processed_stage_file_count += 1
            writer_touched = True

        if writer_touched:
            touched_writers.add(writer_dir.name)
        if not any(writer_dir.iterdir()):
            writer_dir.rmdir()

    return {
        "committed_record_count": committed_record_count,
        "processed_stage_file_count": processed_stage_file_count,
        "segments_touched": sorted(touched_segments),
        "writers_touched": sorted(touched_writers),
        "stage_root": str(stage_dir),
    }


def list_tara_tape_segments(root: Path | str) -> list[str]:
    return [path.name for path in _list_segment_paths(root)]


def read_tara_tape_segment_records(root: Path | str, *, segment_name: str) -> list[object]:
    resolved_root, _manifest = _require_tara_tape_layout(root)
    normalized_segment_name = _normalize_segment_name(segment_name)
    segment_path = get_tara_tape_segments_dir(resolved_root) / normalized_segment_name
    if not segment_path.exists():
        raise CliError(f"segment does not exist: {segment_path}")
    if not segment_path.is_file():
        raise CliError(f"segment path is not a file: {segment_path}")
    return [json.loads(line) for line in _read_jsonl_lines(segment_path)]


def read_tara_tape_records(root: Path | str) -> list[object]:
    records: list[object] = []
    for segment_path in _list_segment_paths(root):
        records.extend(json.loads(line) for line in _read_jsonl_lines(segment_path))
    return records


def verify_tara_tape(root: Path | str) -> dict[str, object]:
    resolved_root, manifest = _require_tara_tape_layout(root)
    segment_paths = _list_segment_paths(resolved_root)
    stage_writer_dirs = _list_stage_writer_dirs(resolved_root)
    stage_file_paths = _list_stage_file_paths(resolved_root)

    committed_record_count = 0
    for path in segment_paths:
        committed_record_count += len(_read_jsonl_lines(path))

    staged_record_count = 0
    for path in stage_file_paths:
        staged_record_count += len(_read_jsonl_lines(path))

    return {
        "root_path": str(resolved_root),
        "manifest": manifest,
        "segment_count": len(segment_paths),
        "segment_filenames": [path.name for path in segment_paths],
        "committed_record_count": committed_record_count,
        "stage_writer_count": len(stage_writer_dirs),
        "stage_writer_ids": [path.name for path in stage_writer_dirs],
        "stage_file_count": len(stage_file_paths),
        "staged_record_count": staged_record_count,
    }
