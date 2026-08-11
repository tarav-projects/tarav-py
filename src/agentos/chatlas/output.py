"""Chatlas.Output: one output contract for every Chatlas leaf command.

Commands compute a JSON-like payload internally, render it as human-readable
text by default, and print the raw payload under an explicit `--json`.

Renderer selection is a CLI-layer concern: the handler already knows which
command it is, so it passes its own `text_renderer` rather than having this
module introspect the payload. Commands without a dedicated renderer fall back
to `render_payload_text`, which reads any JSON-like structure.

The output mode is static. Do not infer it from TTY or pipe state -- a command
that changes shape based on how it was invoked is not usable by agents.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from agentos.agent._cli_common import format_json_output
from agentos.chatlas.time_interface import format_local_timestamp
from agentos.chatlas.time_interface import is_timestamp_field


CHATLAS_OUTPUT_JSON = "json"
CHATLAS_OUTPUT_TEXT = "text"

_INDENT = "  "
_NONE = "(none)"
_EMPTY = "(empty)"


def add_chatlas_output_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--json",
        action="store_const",
        const=CHATLAS_OUTPUT_JSON,
        dest="output",
        help="Print the raw JSON payload.",
    )
    group.add_argument(
        "--text",
        action="store_const",
        const=CHATLAS_OUTPUT_TEXT,
        dest="output",
        help="Print human-readable text (default).",
    )
    parser.set_defaults(output=CHATLAS_OUTPUT_TEXT)


def add_chatlas_output_arguments_to_leaves(parser: argparse.ArgumentParser) -> None:
    """Give every runnable subcommand the shared output flags.

    Applied once over the built parser tree so the contract holds uniformly and
    a new command cannot silently ship without it. Parsers that still own an
    `output_mode` enum are skipped until that flag is retired.
    """
    owns_output_mode = any(action.dest == "output_mode" for action in parser._actions)
    if "handler" in parser._defaults and not owns_output_mode:
        add_chatlas_output_arguments(parser)
    subparser_actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    for action in subparser_actions:
        for child in action.choices.values():
            add_chatlas_output_arguments_to_leaves(child)


def print_chatlas_output(
    payload: object,
    *,
    output: str,
    text_renderer: Callable[[Any], str] | None = None,
) -> None:
    if output == CHATLAS_OUTPUT_JSON:
        print(format_json_output(payload))
        return
    if text_renderer is not None:
        print(text_renderer(payload))
        return
    print(render_payload_text(payload))


def render_payload_text(payload: object) -> str:
    return "\n".join(_render(payload, depth=0))


def _render(value: object, *, depth: int) -> list[str]:
    if isinstance(value, dict):
        return _render_mapping(value, depth=depth)
    if isinstance(value, list):
        return _render_sequence(value, depth=depth)
    return [_indent(depth) + _scalar(value)]


def _render_mapping(value: dict[str, Any], *, depth: int) -> list[str]:
    lines: list[str] = []
    for key in sorted(value):
        lines.extend(_render_field(key, value[key], depth=depth))
    return lines


def _render_sequence(value: list[Any], *, depth: int) -> list[str]:
    lines: list[str] = []
    for item in value:
        block = _render(item, depth=depth + 1)
        # hoist the first line onto the bullet so items read as one unit
        lines.append(_indent(depth) + "- " + block[0].lstrip())
        lines.extend(block[1:])
    return lines


def _render_field(key: str, value: object, *, depth: int) -> list[str]:
    prefix = _indent(depth) + f"{key}:"
    if isinstance(value, dict):
        if not value:
            return [f"{prefix} {_EMPTY}"]
        return [prefix, *_render_mapping(value, depth=depth + 1)]
    if isinstance(value, list):
        if not value:
            return [f"{prefix} {_NONE}"]
        if all(_is_scalar(item) for item in value):
            return [
                prefix
                + " "
                + ", ".join(_field_scalar(key, item) for item in value)
            ]
        return [prefix, *_render_sequence(value, depth=depth + 1)]
    text = _field_scalar(key, value)
    if "\n" in text:
        block = [_indent(depth + 1) + line for line in text.splitlines()]
        return [prefix, *block]
    return [f"{prefix} {text}"]


def _is_scalar(value: object) -> bool:
    return not isinstance(value, (dict, list))


def _scalar(value: object) -> str:
    if value is None:
        return _NONE
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _field_scalar(key: str, value: object) -> str:
    if isinstance(value, str) and is_timestamp_field(key):
        return format_local_timestamp(value)
    return _scalar(value)


def _indent(depth: int) -> str:
    return _INDENT * depth


__all__ = [
    "CHATLAS_OUTPUT_JSON",
    "CHATLAS_OUTPUT_TEXT",
    "add_chatlas_output_arguments",
    "print_chatlas_output",
    "render_payload_text",
]
