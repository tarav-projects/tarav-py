from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.agent.providers.claude_code.session import read_claude_project_session


SUPPORTED_SESSION_COPY_PROVIDERS = ("claude-code",)


def copy_agent_session(
    *,
    provider: str,
    from_home: Path,
    to_home: Path,
    session_id: str,
    check: bool = False,
    force: bool = False,
) -> dict[str, object]:
    if provider == "claude-code":
        return _copy_claude_session(
            from_home=from_home,
            to_home=to_home,
            session_id=session_id,
            check=check,
            force=force,
        )
    raise CliError(f"agent sessions copy is not supported for provider {provider}")


def _copy_claude_session(
    *,
    from_home: Path,
    to_home: Path,
    session_id: str,
    check: bool,
    force: bool,
) -> dict[str, object]:
    source_home = from_home.expanduser().resolve()
    destination_home = to_home.expanduser().resolve()
    _reject_linked_claude_projects(source_home, role="source")
    _reject_linked_claude_projects(destination_home, role="destination")
    source = _find_claude_transcript(source_home=source_home, session_id=session_id)
    destination = destination_home / source.relative_to(source_home)
    action = _copy_file_action(
        source=source,
        destination=destination,
        check=check,
        force=force,
    )
    return {
        "status": "ok",
        "command": "agent sessions copy",
        "provider": "claude-code",
        "session_id": session_id,
        "from_home": str(source_home),
        "to_home": str(destination_home),
        "actions": [action],
        "warnings": [],
    }


def _reject_linked_claude_projects(home: Path, *, role: str) -> None:
    projects_root = home / "projects"
    if projects_root.is_symlink():
        raise CliError(
            f"agent sessions copy does not support linked Claude {role} homes: "
            f"{projects_root} -> {projects_root.readlink()}"
        )


def _find_claude_transcript(*, source_home: Path, session_id: str) -> Path:
    projects_root = source_home / "projects"
    candidates = [
        session.transcript_path.resolve()
        for path in sorted(projects_root.rglob(f"{session_id}.jsonl"))
        if path.is_file()
        if (session := read_claude_project_session(path)) is not None
        if session.native_session_id == session_id
    ]
    if not candidates:
        raise CliError(f"claude-code session not found: {session_id}")
    if len(candidates) > 1:
        choices = ", ".join(str(path) for path in candidates)
        raise CliError(f"multiple claude-code sessions matched {session_id}: {choices}")
    transcript = candidates[0]
    try:
        transcript.relative_to(projects_root)
    except ValueError as exc:
        raise CliError(
            f"claude-code session transcript is outside projects root: {transcript}"
        ) from exc
    if transcript.suffix != ".jsonl":
        raise CliError(f"claude-code session transcript is not JSONL: {transcript}")
    return transcript


def _copy_file_action(
    *,
    source: Path,
    destination: Path,
    check: bool,
    force: bool,
) -> dict[str, object]:
    base_action = {
        "role": "transcript",
        "source_path": str(source),
        "destination_path": str(destination),
    }
    if destination.exists():
        if filecmp.cmp(source, destination, shallow=False):
            return {"kind": "noop", "status": "identical", **base_action}
        if not force:
            raise CliError(f"destination session artifact already exists: {destination}")
        if check:
            return {"kind": "overwrite", "status": "planned", **base_action}
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return {"kind": "overwrite", "status": "copied", **base_action}

    if check:
        return {"kind": "copy", "status": "planned", **base_action}

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"kind": "copy", "status": "copied", **base_action}


__all__ = ["SUPPORTED_SESSION_COPY_PROVIDERS", "copy_agent_session"]
