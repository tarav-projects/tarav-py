from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import shutil
import sys
from typing import Any, Iterator
from uuid import uuid4

from agentos._core.errors import CliError
from filelock import FileLock, Timeout

from agentos.chatlas._payload_helpers import dict_list
from agentos.chatlas.normalization.session_model import (
    validate_session_model_schema_version,
)
from agentos.chatlas.normalization.session_model.artifact import (
    load_session_model_artifact,
    session_model_artifact_files,
)
from agentos.chatlas.paths import default_chatlas_root


SESSION_MODELS_ROOT = "session-models"
MANIFEST_FILENAME = "manifest.json"
LOCKS_ROOT = "locks"
SESSION_MODEL_MATERIALIZATION_REVISION = "stable-event-place-v1"


def session_model_cache_path(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> Path:
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError("Chatlas session-model cache requires identity_hash")
    return _chatlas_root(chatlas_root) / SESSION_MODELS_ROOT / identity_hash


def session_model_lock_path(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> Path:
    return (
        _chatlas_root(chatlas_root)
        / LOCKS_ROOT
        / SESSION_MODELS_ROOT
        / f"{session_model_cache_path(session, chatlas_root=chatlas_root).name}.lock"
    )


@contextmanager
def session_model_materialization_lock(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> Iterator[None]:
    lock_path = session_model_lock_path(session, chatlas_root=chatlas_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(lock_path)
    print(f"[chatlas] acquiring session-model lock: {lock_path}", file=sys.stderr)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(f"[chatlas] waiting for session-model lock: {lock_path}", file=sys.stderr)
        lock.acquire()
    print(f"[chatlas] acquired session-model lock: {lock_path}", file=sys.stderr)
    try:
        yield
    finally:
        lock.release()
        print(f"[chatlas] released session-model lock: {lock_path}", file=sys.stderr)


def load_chatlas_session_model(
    session: dict[str, Any], *, chatlas_root: Path | None = None
) -> dict[str, Any]:
    root = _chatlas_root(chatlas_root)
    cache_path = session_model_cache_path(session, chatlas_root=root)
    fingerprint = session_model_source_fingerprint(session)
    if not _cache_is_fresh(cache_path, fingerprint=fingerprint):
        with session_model_materialization_lock(session, chatlas_root=root):
            if not _cache_is_fresh(cache_path, fingerprint=fingerprint):
                _materialize_session_model(
                    session,
                    chatlas_root=root,
                    cache_path=cache_path,
                    fingerprint=fingerprint,
                )
    model = load_session_model_artifact(cache_path)
    validate_session_model_schema_version(model)
    return model


def session_model_source_fingerprint(session: dict[str, Any]) -> str:
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError("Chatlas session-model fingerprint requires identity_hash")
    artifacts: list[dict[str, object]] = []
    for artifact in dict_list(session.get("backing_artifacts")):
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            continue
        try:
            stat = Path(path).stat()
        except OSError:
            size_bytes = -1
            modified_ns = -1
        else:
            size_bytes = stat.st_size
            modified_ns = stat.st_mtime_ns
        artifacts.append(
            {
                "path": path,
                "size_bytes": size_bytes,
                "modified_ns": modified_ns,
            }
        )
    return _json_sha256(
        {
            "identity_hash": identity_hash,
            "backing_artifacts": sorted(artifacts, key=lambda value: str(value["path"])),
        }
    )


def _materialize_session_model(
    session: dict[str, Any],
    *,
    chatlas_root: Path,
    cache_path: Path,
    fingerprint: str,
) -> None:
    from agentos.chatlas.normalization.session_model._model import (
        build_session_model_with_delta_state,
        record_delta_checkpoint,
    )

    model, delta_state = build_session_model_with_delta_state(
        session, chatlas_root=chatlas_root
    )
    files = session_model_artifact_files(model)
    files[MANIFEST_FILENAME] = _json_bytes(
        {
            "class": "agentos_chatlas.session_model_cache",
            "schema_version": 2,
            "identity_hash": session.get("identity_hash"),
            "source_fingerprint": fingerprint,
            "materialization_revision": SESSION_MODEL_MATERIALIZATION_REVISION,
        }
    )
    _replace_directory_with_files(cache_path, files)
    record_delta_checkpoint(
        session,
        chatlas_root=chatlas_root,
        delta_state=delta_state,
    )


def _cache_is_fresh(cache_path: Path, *, fingerprint: str) -> bool:
    manifest_path = cache_path / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(manifest, dict)
        and manifest.get("source_fingerprint") == fingerprint
        and manifest.get("materialization_revision")
        == SESSION_MODEL_MATERIALIZATION_REVISION
    )


def _replace_directory_with_files(path: Path, files: dict[str, bytes]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    backup_path = path.with_name(f".{path.name}.old-{uuid4().hex}")
    temp_path.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items():
            target = temp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.rename(backup_path)
        try:
            temp_path.rename(path)
        except Exception:
            if backup_path.exists() and not path.exists():
                backup_path.rename(path)
            raise
        if backup_path.exists():
            shutil.rmtree(backup_path)
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)


def _chatlas_root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")


def _json_sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


__all__ = [
    "load_chatlas_session_model",
    "session_model_cache_path",
    "session_model_materialization_lock",
    "session_model_source_fingerprint",
]
