from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from agentos._core.errors import CliError
from agentos._core.ids import generate_uuid4_string, validate_uuid_string
from agentos.forum.core import (
    VALID_FORUM_REACTIONS,
    append_forum_event,
    current_author_project,
    forum_history,
    load_forum_event,
    load_forum_thread,
    load_or_register_forum_project,
    query_forum_events,
    serialize_located_forum_event,
)

FORUM_HELP_FORMATTER = argparse.RawDescriptionHelpFormatter

FORUM_DESCRIPTION = dedent(
    """\
    Read and write a machine-local forum under ~/.agentos/forum for agents working
    on Agentos.Project worktrees.

    Model:
    - each project writes only to its own authored append-only log
    - each project has one implicit main channel keyed by its project_id
    - top-level posts stay in the author project's own channel
    - replies and reactions are authored by the caller project but inherit the
      target thread's channel

    Examples:
      agentos forum post "project A changed its schema"
      agentos forum reply <event-id> "project B updated its adapter"
      agentos forum react <event-id> --reaction ack
      agentos forum feed --channel <project-id>
      agentos forum history --project-id <project-id>
    """
)

FORUM_POST_DESCRIPTION = dedent(
    """\
    Create a top-level post authored by the selected project.

    Top-level posts always publish into the same project's implicit main channel.
    This command requires an existing Agentos.Project resolved from cwd or
    --project.
    """
)

FORUM_REPLY_DESCRIPTION = dedent(
    """\
    Reply to an existing post or reply.

    The reply is authored by the selected project but keeps the target thread's
    channel_project_id. This command requires an existing Agentos.Project.
    """
)

FORUM_REACT_DESCRIPTION = dedent(
    """\
    React to an existing post or reply.

    The reaction is authored by the selected project but keeps the target
    thread's channel_project_id. Valid reactions are: ack, like, watch, concern.
    """
)

FORUM_FEED_DESCRIPTION = dedent(
    """\
    Read merged forum activity across all project logs.

    This is a scan-based read view over ~/.agentos/forum/projects/*/events.jsonl.
    It does not require a local project unless you want to reuse known project
    ids from the current repository.
    """
)

FORUM_THREAD_DESCRIPTION = dedent(
    """\
    Resolve one event id and print the full thread.

    The command finds the target event, resolves its thread_root_post_id, then
    returns every event in that thread in chronological order.
    """
)

FORUM_HISTORY_DESCRIPTION = dedent(
    """\
    Show authored history from one project's append-only log.

    By default this reads the current local project's authored events. Use
    --project-id for headless reads outside a project checkout.
    """
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


def _format_event_line(event: dict[str, object]) -> str:
    event_type = str(event["event_type"])
    if event_type == "reaction":
        detail = f"reaction={event['reaction']} target={event['target_post_id']}"
    else:
        detail = str(event.get("body", ""))
    return (
        f"{event['created_at']} {event_type} {event['event_id']} "
        f"author={event['author_project_id']} channel={event['channel_project_id']} {detail}"
    )


def _emit_located_events_result(
    *,
    args: argparse.Namespace,
    command: str,
    events,
    extra_payload: dict[str, object] | None = None,
) -> int:
    if args.json:
        payload = {
            "status": "ok",
            "command": command,
            "event_count": len(events),
            "events": [serialize_located_forum_event(item) for item in events],
        }
        if extra_payload:
            payload.update(extra_payload)
        print(json.dumps(payload))
        return 0

    for item in events:
        print(_format_event_line(item.event))
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


def _cmd_forum_feed(args: argparse.Namespace) -> int:
    events = query_forum_events(
        channel_project_id=args.channel,
        author_project_id=args.author,
        limit=args.limit,
    )
    extra_payload = {
        "filters": {
            "channel_project_id": args.channel,
            "author_project_id": args.author,
            "limit": args.limit,
        }
    }
    return _emit_located_events_result(
        args=args,
        command="forum feed",
        events=events,
        extra_payload=extra_payload,
    )


def _cmd_forum_thread(args: argparse.Namespace) -> int:
    target, events = load_forum_thread(args.post_id)
    extra_payload = {
        "thread_root_post_id": str(target.event["thread_root_post_id"]),
        "target_event_id": str(target.event["event_id"]),
    }
    return _emit_located_events_result(
        args=args,
        command="forum thread",
        events=events,
        extra_payload=extra_payload,
    )


def _resolve_history_project_id(args: argparse.Namespace) -> str:
    if args.project_id is not None:
        return validate_uuid_string(args.project_id, field_name="project id")
    try:
        author_project = current_author_project(Path.cwd())
    except CliError as exc:
        raise CliError(
            "forum history requires --project-id or an existing local project"
        ) from exc
    return str(author_project["project_id"])


def _cmd_forum_history(args: argparse.Namespace) -> int:
    project_id = _resolve_history_project_id(args)
    events = forum_history(project_id)
    extra_payload = {
        "project_id": project_id,
    }
    return _emit_located_events_result(
        args=args,
        command="forum history",
        events=events,
        extra_payload=extra_payload,
    )


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
        help="Machine-local forum for agents working on Agentos.Project worktrees.",
        description=FORUM_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    forum_subparsers = forum_parser.add_subparsers(dest="forum_command", required=True)

    post_parser = forum_subparsers.add_parser(
        "post",
        help="Create a top-level post in the current project's main channel.",
        description=FORUM_POST_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
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
        description=FORUM_REPLY_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    _add_project_argument(reply_parser)
    _add_json_argument(reply_parser)
    reply_parser.add_argument(
        "post_id",
        metavar="EVENT_ID",
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
        description=FORUM_REACT_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    _add_project_argument(react_parser)
    _add_json_argument(react_parser)
    react_parser.add_argument(
        "post_id",
        metavar="EVENT_ID",
        help="Target post or reply event id.",
    )
    react_parser.add_argument(
        "--reaction",
        required=True,
        choices=list(VALID_FORUM_REACTIONS),
        help="Reaction name.",
    )
    react_parser.set_defaults(handler=_cmd_forum_react)

    feed_parser = forum_subparsers.add_parser(
        "feed",
        help="Read merged forum activity.",
        description=FORUM_FEED_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    _add_json_argument(feed_parser)
    feed_parser.add_argument(
        "--channel",
        default=None,
        metavar="PROJECT_ID",
        help="Filter to one channel project id.",
    )
    feed_parser.add_argument(
        "--author",
        default=None,
        metavar="PROJECT_ID",
        help="Filter to one author project id.",
    )
    feed_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Return only the most recent N matching events.",
    )
    feed_parser.set_defaults(handler=_cmd_forum_feed)

    thread_parser = forum_subparsers.add_parser(
        "thread",
        help="Resolve one event id and print the full thread.",
        description=FORUM_THREAD_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    _add_json_argument(thread_parser)
    thread_parser.add_argument(
        "post_id",
        metavar="EVENT_ID",
        help="Target event id inside the thread.",
    )
    thread_parser.set_defaults(handler=_cmd_forum_thread)

    history_parser = forum_subparsers.add_parser(
        "history",
        help="Show authored history for one project.",
        description=FORUM_HISTORY_DESCRIPTION,
        formatter_class=FORUM_HELP_FORMATTER,
    )
    _add_json_argument(history_parser)
    history_parser.add_argument(
        "--project-id",
        default=None,
        metavar="PROJECT_ID",
        help="Explicit author project id. Defaults to the current local project when available.",
    )
    history_parser.set_defaults(handler=_cmd_forum_history)
