from __future__ import annotations

from pathlib import Path

from tarav.chatlas2 import normal_model


class _Reader:
    def __init__(self) -> None:
        self.model = {"class": "tarav.chatlas2.normal_model"}

    def load_normal_model(self) -> dict[str, object]:
        return self.model


def test_default_normal_model_access_uses_transparent_cache_provider(
    monkeypatch,
) -> None:
    reader = _Reader()
    calls: list[tuple[str, dict[str, object]]] = []

    def open_or_materialize(**kwargs):
        calls.append(("default", kwargs))
        return reader

    monkeypatch.setattr(
        normal_model,
        "open_or_materialize_normal_model_cache",
        open_or_materialize,
    )

    assert normal_model.provide_normal_model(identity_hash="abc") is reader.model
    assert calls == [
        (
            "default",
            {"session_id": None, "identity_hash": "abc", "chatlas_root": None},
        )
    ]


def test_refresh_forces_cache_replacement(monkeypatch, tmp_path: Path) -> None:
    reader = _Reader()
    calls: list[dict[str, object]] = []

    def materialize(**kwargs):
        calls.append(kwargs)
        return reader

    monkeypatch.setattr(
        normal_model,
        "materialize_normal_model_cache",
        materialize,
    )

    assert (
        normal_model.provide_normal_model_reader(
            session_id="session-one",
            chatlas_root=tmp_path,
            refresh=True,
        )
        is reader
    )
    assert calls == [
        {
            "session_id": "session-one",
            "identity_hash": None,
            "chatlas_root": tmp_path,
        }
    ]


def test_diagnostic_computation_bypasses_cache(monkeypatch, tmp_path: Path) -> None:
    expected = {"raw": [{"value": "native"}]}
    calls: list[dict[str, object]] = []

    def build(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(normal_model, "build_normal_model", build)

    assert (
        normal_model.compute_normal_model(
            identity_hash="abc",
            chatlas_root=tmp_path,
            include_raw=True,
        )
        is expected
    )
    assert calls == [
        {
            "session_id": None,
            "identity_hash": "abc",
            "chatlas_root": tmp_path,
            "include_raw": True,
        }
    ]
