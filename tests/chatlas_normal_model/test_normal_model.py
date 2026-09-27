from __future__ import annotations

from pathlib import Path

from tarav.l1.chatlas.normal_model import normal_model


def test_provide_resolves_one_index_row_then_uses_cache(monkeypatch, tmp_path: Path) -> None:
    row = {"identity_hash": "abc", "session_id": "session-one"}
    model = {"type": "Chatlas.Normal.Model"}
    calls: list[tuple[str, dict[str, object]]] = []

    def resolve(**kwargs):
        calls.append(("resolve", kwargs))
        return row

    def provide(selected, **kwargs):
        calls.append(("provide", {"row": selected, **kwargs}))
        return model

    monkeypatch.setattr(normal_model, "resolve_session_index_row", resolve)
    monkeypatch.setattr(normal_model, "provide_normal_model_from_row", provide)

    assert normal_model.provide_normal_model(
        identity_hash="abc", chatlas_root=tmp_path, refresh=True
    ) is model
    assert calls == [
        (
            "resolve",
            {
                "session_id": None,
                "identity_hash": "abc",
                "provider": None,
                "instance": None,
                "chatlas_root": tmp_path,
            },
        ),
        (
            "provide",
            {"row": row, "chatlas_root": tmp_path, "refresh": True},
        ),
    ]


def test_compute_bypasses_cache_and_can_attach_raw(monkeypatch) -> None:
    row = {"identity_hash": "abc"}
    expected = {"raw": [{"value": "native"}]}
    monkeypatch.setattr(normal_model, "resolve_session_index_row", lambda **_: row)
    monkeypatch.setattr(
        normal_model,
        "build_normal_model_from_row",
        lambda selected, *, include_raw: expected
        if selected is row and include_raw
        else None,
    )

    assert normal_model.compute_normal_model(identity_hash="abc", include_raw=True) is expected
