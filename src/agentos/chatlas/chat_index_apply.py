# $kw: --from Capture.Plan --from Chat.Index --from Prefix.Stability --note [IMPL] anchors are ensured before a recoverable directory swap and the surface is audited staged and landed --supp ^c20260804-60u
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Iterator
import uuid

from agentos._core.errors import CliError

from agentos.chatlas.anchory_batch import chatlas_anchory_batch_register
from agentos.chatlas.chat_index import (
    chat_index_source_model,
    compare_v2_source_tail,
    session_locator,
)
from agentos.chatlas.chat_index_audit import audit_chat_index_surface
from agentos.chatlas.chat_index_plan import (
    CAPTURE_PLAN_SCHEMA,
    load_capture_plan,
)
from agentos.chatlas.chat_index_render import (
    RenderModel,
    build_render_model,
    render_surface,
)


LOCKS_ROOT = Path("locks") / "chat-index"


@contextmanager
def chat_index_lock(
    chatlas_root: Path, identity_hash: str, *, command: str
) -> Iterator[Path]:
    """A visible, identity-scoped lock; a stale one is a human decision."""
    path = chatlas_root / LOCKS_ROOT / f"{identity_hash}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise CliError(
            f"Chat.Index {identity_hash} is locked by another maintenance run: "
            f"{path}; remove it only after confirming no apply is in progress"
        ) from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(
                {"command": command, "pid": os.getpid(), "acquired_at": _now()},
                stream,
            )
        yield path
    finally:
        path.unlink(missing_ok=True)


def chatlas_chat_index_apply(
    *,
    plan: str | Path,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Ground, render, audit, and install one Capture.Plan."""
    loaded = load_capture_plan(Path(plan).expanduser().resolve())
    if loaded.status == "draft":
        raise CliError(
            "Chat.Index capture plan status is 'draft'; set 'ready' "
            "when the semantic region is authored"
        )
    # The pre-lock model resolves the chatlas root; everything that decides the
    # result is derived again under the lock.
    preview = build_render_model(loaded, chatlas_root=chatlas_root)
    root = preview.root
    identity_hash = preview.identity_hash

    with chat_index_lock(root, identity_hash, command="chatlas chat-index apply"):
        model = build_render_model(loaded, chatlas_root=root)
        anchors, anchor_result = _ensure_anchors(model)
        files = render_surface(model, anchors)
        stage_dir = _stage(model, files)
        try:
            staged_audit = _audit_stage(model, stage_dir)
            if not staged_audit["ok"]:
                raise CliError(
                    "Chat.Index staged surface failed its own audit; nothing was "
                    "installed: "
                    + "; ".join(
                        str(finding["message"])
                        for finding in staged_audit["findings"]
                        if finding["severity"] == "blocking"
                    )
                )
            installed = _install(model.surface_path, stage_dir)
        except BaseException:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

        landed_audit = audit_chat_index_surface(
            model.surface_path,
            identity_hash=identity_hash,
            session=model.session,
            chatlas_root=root,
        )
        _canonical, live_source = chat_index_source_model(
            model.session, chatlas_root=root
        )
        tail = compare_v2_source_tail(model.source, live_source)

    return {
        "status": "ok",
        "command": "chatlas chat-index apply",
        "schema": CAPTURE_PLAN_SCHEMA,
        "chatlas_root": str(root),
        "session": session_locator(model.session),
        "plan_path": str(loaded.path),
        "mode": model.mode,
        "surface_path": str(model.surface_path),
        "anchors": {
            "item_count": anchor_result["item_count"],
            "minted_count": anchor_result["minted_count"],
            "reused_count": anchor_result["reused_count"],
        },
        "installed": installed,
        "removed_paths": model.removed_paths,
        "audit": landed_audit,
        "tail": tail,
        "ok": bool(landed_audit["ok"]),
    }


def _ensure_anchors(model: RenderModel) -> tuple[dict[str, str], dict[str, object]]:
    """Exact line-bound ensure; a retry after a later failure reuses these."""
    if not model.batch_items:
        return {}, {"item_count": 0, "minted_count": 0, "reused_count": 0, "items": []}
    result = chatlas_anchory_batch_register(
        items=[
            {key: value for key, value in item.items() if key != "tape_bound"}
            for item in model.batch_items
        ],
        chatlas_root=model.root,
    )
    anchors = {
        str(item["client_id"]): str(item["anchor"]) for item in result["items"]
    }
    return anchors, result


def _stage(model: RenderModel, files: dict[str, str]) -> Path:
    """Stage from a copy of the live directory so unrelated files survive."""
    parent = model.surface_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage_dir = parent / f".{model.surface_path.name}.stage-{uuid.uuid4().hex[:12]}"
    if model.surface_path.is_dir():
        shutil.copytree(model.surface_path, stage_dir)
        for relative_path in model.removed_paths:
            (stage_dir / relative_path).unlink(missing_ok=True)
    else:
        stage_dir.mkdir()
    for relative_path, content in files.items():
        path = stage_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _prune_empty_delta_dirs(stage_dir)
    return stage_dir


def _prune_empty_delta_dirs(stage_dir: Path) -> None:
    deltas = stage_dir / "deltas"
    if deltas.is_dir() and not any(deltas.iterdir()):
        deltas.rmdir()


def _audit_stage(model: RenderModel, stage_dir: Path) -> dict[str, object]:
    return audit_chat_index_surface(
        stage_dir,
        identity_hash=model.identity_hash,
        session=model.session,
        chatlas_root=model.root,
        at_identity_path=False,
    )


def _install(surface_path: Path, stage_dir: Path) -> dict[str, object]:
    """Rename-based replacement that puts the old directory back on failure."""
    existed = surface_path.exists()
    backup = (
        surface_path.parent / f".{surface_path.name}.backup-{uuid.uuid4().hex[:12]}"
    )
    if existed:
        surface_path.rename(backup)
    try:
        stage_dir.rename(surface_path)
    except OSError as exc:
        if existed:
            backup.rename(surface_path)
        raise CliError(
            f"Chat.Index surface replacement failed and the prior surface was "
            f"restored: {exc}"
        ) from exc
    if existed:
        shutil.rmtree(backup, ignore_errors=True)
    return {
        "replaced_existing": existed,
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "LOCKS_ROOT",
    "chat_index_lock",
    "chatlas_chat_index_apply",
]
