# $kw: --from Chat.Semantic.From.File.Content
"""File-touch extraction over `chat.tool_invocations`.

A *touch* is a tool invocation whose explicit path argument matches the query
path (substring, consistent with the `*-contains` filter family). All tool
knowledge lives in `_FILE_TOOLS`: extending coverage is a table edit.

Blind spot by design: command-string tools (Bash) carry paths invisibly to
this extractor; add them only when workflows demand it.
"""

from __future__ import annotations

from typing import Any

from agentos.chatlas._payload_helpers import dict_list, string_or_none



_FILE_TOOLS: dict[str, tuple[str, str]] = {
    "Read": ("read", "file_path"),
    "Write": ("write", "file_path"),
    "Edit": ("write", "file_path"),
    "NotebookEdit": ("write", "notebook_path"),
}

_TOUCH_MODES = ("read", "write", "touched")


def file_touch_invocations(
    session_model: dict[str, Any],
    *,
    path: str,
    mode: str,
) -> list[dict[str, Any]]:
    if mode not in _TOUCH_MODES:
        raise ValueError(f"unknown file-touch mode: {mode!r}")
    chat = session_model.get("chat")
    invocations = dict_list(chat.get("tool_invocations")) if isinstance(chat, dict) else []
    matched: list[dict[str, Any]] = []
    for invocation in invocations:
        tool_name = string_or_none(invocation.get("tool_name"))
        tool = _FILE_TOOLS.get(tool_name) if tool_name else None
        if tool is None:
            continue
        touch_class, path_key = tool
        if mode != "touched" and touch_class != mode:
            continue
        invocation_path = _find_path_argument(invocation.get("input"), path_key)
        if invocation_path is None or path not in invocation_path:
            continue
        matched.append(invocation)
    return matched


def _find_path_argument(value: object, path_key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(path_key)
        if isinstance(candidate, str):
            return candidate
        for item in value.values():
            found = _find_path_argument(item, path_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_path_argument(item, path_key)
            if found is not None:
                return found
    return None


def tool_contains_invocations(
    session_model: dict[str, Any],
    *,
    text: str,
    tool_name: str | None = None,
) -> list[dict[str, Any]]:
    """Recall-tier matcher: substring over the whole invocation (name+input+output).

    No verb claim - the caller reads the matches and judges read/write itself.
    """
    needle = text.casefold()
    chat = session_model.get("chat")
    invocations = dict_list(chat.get("tool_invocations")) if isinstance(chat, dict) else []
    matched: list[dict[str, Any]] = []
    for invocation in invocations:
        if tool_name is not None and string_or_none(invocation.get("tool_name")) != tool_name:
            continue
        if needle in _invocation_text_blob(invocation).casefold():
            matched.append(invocation)
    return matched


def _invocation_text_blob(invocation: dict[str, Any]) -> str:
    collected: list[str] = []
    _collect_strings(
        {
            "tool_name": invocation.get("tool_name"),
            "input": invocation.get("input"),
            "output": invocation.get("output"),
        },
        collected,
    )
    return " ".join(collected)


def _collect_strings(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, out)


__all__ = ["file_touch_invocations", "tool_contains_invocations"]
