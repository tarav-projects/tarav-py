from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
from threading import Event, Lock
import time

import pytest

from agentos.chatlas import session_cache


SESSION = {"identity_hash": "a" * 64, "backing_artifacts": []}


def test_cache_freshness_requires_materialization_revision(tmp_path: Path) -> None:
    manifest = tmp_path / session_cache.MANIFEST_FILENAME
    manifest.write_text(
        json.dumps(
            {
                "source_fingerprint": "same-raw",
                "materialization_revision": "older-normalizer",
            }
        ),
        encoding="utf-8",
    )
    assert not session_cache._cache_is_fresh(tmp_path, fingerprint="same-raw")

    manifest.write_text(
        json.dumps(
            {
                "source_fingerprint": "same-raw",
                "materialization_revision": session_cache.SESSION_MODEL_MATERIALIZATION_REVISION,
            }
        ),
        encoding="utf-8",
    )
    assert session_cache._cache_is_fresh(tmp_path, fingerprint="same-raw")


def test_session_model_lock_reports_lifecycle_and_releases_after_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path = session_cache.session_model_lock_path(SESSION, chatlas_root=tmp_path)
    with pytest.raises(RuntimeError):
        with session_cache.session_model_materialization_lock(
            SESSION, chatlas_root=tmp_path
        ):
            raise RuntimeError("failure")

    assert capsys.readouterr().err.splitlines() == [
        f"[chatlas] acquiring session-model lock: {lock_path}",
        f"[chatlas] acquired session-model lock: {lock_path}",
        f"[chatlas] released session-model lock: {lock_path}",
    ]


def test_session_model_lock_serializes_same_identity_only(tmp_path: Path) -> None:
    first_acquired = Event()
    same_attempted = Event()
    release_first = Event()
    output = io.StringIO()
    other = {**SESSION, "identity_hash": "b" * 64}

    def hold_first() -> None:
        with session_cache.session_model_materialization_lock(
            SESSION, chatlas_root=tmp_path
        ):
            first_acquired.set()
            release_first.wait()

    def acquire_same() -> None:
        first_acquired.wait()
        same_attempted.set()
        with session_cache.session_model_materialization_lock(
            SESSION, chatlas_root=tmp_path
        ):
            pass

    def acquire_other() -> None:
        same_attempted.wait()
        time.sleep(0.02)
        with session_cache.session_model_materialization_lock(
            other, chatlas_root=tmp_path
        ):
            release_first.set()

    with redirect_stderr(output), ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fn) for fn in (hold_first, acquire_same, acquire_other)]
        for future in futures:
            future.result()

    same_path = session_cache.session_model_lock_path(SESSION, chatlas_root=tmp_path)
    other_path = session_cache.session_model_lock_path(other, chatlas_root=tmp_path)
    messages = output.getvalue().splitlines()
    assert f"[chatlas] waiting for session-model lock: {same_path}" in messages
    assert f"[chatlas] waiting for session-model lock: {other_path}" not in messages


def test_concurrent_session_model_load_materializes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    materialized = False
    produce_count = 0
    count_lock = Lock()

    def is_fresh(_path: Path, *, fingerprint: str) -> bool:
        _ = fingerprint
        return materialized

    def materialize(*_args: object, **_kwargs: object) -> None:
        nonlocal materialized, produce_count
        with count_lock:
            produce_count += 1
        time.sleep(0.05)
        materialized = True

    monkeypatch.setattr(session_cache, "_cache_is_fresh", is_fresh)
    monkeypatch.setattr(session_cache, "_materialize_session_model", materialize)
    monkeypatch.setattr(
        session_cache, "load_session_model_artifact", lambda _path: {"schema_version": 4}
    )
    monkeypatch.setattr(
        session_cache, "validate_session_model_schema_version", lambda _model: None
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        models = list(
            executor.map(
                lambda _value: session_cache.load_chatlas_session_model(
                    SESSION, chatlas_root=tmp_path
                ),
                range(8),
            )
        )

    assert produce_count == 1
    assert models == [{"schema_version": 4}] * 8
