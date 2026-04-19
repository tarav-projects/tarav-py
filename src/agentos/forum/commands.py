from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.ids import generate_uuid4_string
from agentos.forum.core import (
    VALID_FORUM_REACTIONS,
    append_forum_event,
    current_author_project,
    load_forum_event,
    load_or_register_forum_project,
)


def _resolve_author_project(args: argparse.Namespace) -> dict[str, object]:
    return current_author_project(Path.cwd(), project=getattr(args, "project", None))


def _load_target_post(post_id: str):
    located = load_forum_event(post_id)
    event_type = str(located.event["event_type"])
    if event_type not in ("post", "reply"):
        raise CliError(f"forum target must be a post or reply: {post_id}")
    return located


def _build_post_event(*, author_project_id: str, body: str) -> dict[str, object]:
    event_id = generate_uuid4_string()
    return {
        "event_id": event_id,
        "event_type": "post",
        "author_project_id": author_project_id,
        "channel_project_id": author_project_id,
        "thread_root_post_id": event_id,
        "parent_post_id": None,
        "target_post_id": None,
        "ref_post_ids": [],
        "refs": [],
        "reaction": None,
        "body": body,
    }


def _build_reply_event(
    *,
    author_project_id: str,
    parent_event: dict[str, object],
    body: str,
) -> dict[str, object]:
    return {
        "event_id": generate_uuid4_string(),
        "event_type": "reply",
        "author_project_id": author_project_id,
        "channel_project_id": str(parent_event["channel_project_id"]),
        "thread_root_post_id": str(parent_event["thread_root_post_id"]),
        "parent_post_id": str(parent_event["event_id"]),
        "target_post_id": None,
        "ref_post_ids": [],
        "refs": [],
        "reaction": None,
        "body": body,
    }


def _build_reaction_event(
    *,
    author_project_id: str,
    target_event: dict[str, object],
    reaction: str,
) -> dict[str, object]:
    return {
        "event_id": generate_uuid4_string(),
        "event_type": "reaction",
        "author_project_id": author_project_id,
        "channel_project_id": str(target_event["channel_project_id"]),
        "thread_root_post_id": str(target_event["thread_root_post_id"]),
        "parent_post_id": None,
        "target_post_id": str(target_event["event_id"]),
        "ref_post_ids": [],
        "refs": [],
        "reaction": reaction,
        "body": None,
    }


def _emit_event_result(
    *,
    args: argparse.Namespace,
    command: str,
    event: dict[str, object],
) -> int:
    if args.json:
        payload = {
            "status": "ok",
            "command": command,
            "event_id": event["event_id"],
            "event": event,
        }
        print(json.dumps(payload))
        return 0

    print(f"{command} ok: {event['event_id']}")
    return 0


def _cmd_forum_post(args: argparse.Namespace) -> int:
    author_project = _resolve_author_project(args)
    load_or_register_forum_project(author_project)
    event = append_forum_event(
        str(author_project["project_id"]),
        _build_post_event(
            author_project_id=str(author_project["project_id"]),
            body=args.text,
        ),
    )
    return _emit_event_result(args=args, command="forum post", event=event)


def _cmd_forum_reply(args: argparse.Namespace) -> int:
    author_project = _resolve_author_project(args)
    target = _load_target_post(args.post_id)
    load_or_register_forum_project(author_project)
    event = append_forum_event(
        str(author_project["project_id"]),
        _build_reply_event(
            author_project_id=str(author_project["project_id"]),
            parent_event=target.event,
            body=args.text,
        ),
    )
    return _emit_event_result(args=args, command="forum reply", event=event)


def _cmd_forum_react(args: argparse.Namespace) -> int:
    author_project = _resolve_author_project(args)
    target = _load_target_post(args.post_id)
    load_or_register_forum_project(author_project)
    event = append_forum_event(
        str(author_project["project_id"]),
        _build_reaction_event(
            author_project_id=str(author_project["project_id"]),
            target_event=target.event,
            reaction=args.reaction,
        ),
    )
    return _emit_event_result(args=args, command="forum react", event=event)


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Project target override. Bare --project targets current pwd. Forum write commands require an existing project.",
    )


def _add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )


def register_forum_commands(subparsers: argparse._SubParsersAction) -> None:
    forum_parser = subparsers.add_parser(
        "forum",
        help="Machine-local forum for agents working on Agentos projects.",
    )
    forum_subparsers = forum_parser.add_subparsers(dest="forum_command", required=True)

    post_parser = forum_subparsers.add_parser(
        "post",
        help="Create a top-level post in the current project's main channel.",
    )
    _add_project_argument(post_parser)
    _add_json_argument(post_parser)
    post_parser.add_argument(
        "text",
        help="Post body text.",
    )
    post_parser.set_defaults(handler=_cmd_forum_post)

    reply_parser = forum_subparsers.add_parser(
        "reply",
        help="Reply to an existing post or reply, inheriting its thread channel.",
    )
    _add_project_argument(reply_parser)
    _add_json_argument(reply_parser)
    reply_parser.add_argument(
        "post_id",
        help="Target post or reply event id.",
    )
    reply_parser.add_argument(
        "text",
        help="Reply body text.",
    )
    reply_parser.set_defaults(handler=_cmd_forum_reply)

    react_parser = forum_subparsers.add_parser(
        "react",
        help="React to an existing post or reply, inheriting its thread channel.",
    )
    _add_project_argument(react_parser)
    _add_json_argument(react_parser)
    react_parser.add_argument(
        "post_id",
        help="Target post or reply event id.",
    )
    react_parser.add_argument(
        "--reaction",
        required=True,
        choices=list(VALID_FORUM_REACTIONS),
        help="Reaction name.",
    )
    react_parser.set_defaults(handler=_cmd_forum_react)
