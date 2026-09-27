# $kw: --from Usage.Surface --from Agentos.Project
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.forum.core import ForumDepot, Post, current_post_source, mark_read, read_cursor


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _post_payload(post: Post) -> dict[str, object]:
    return {
        "path": str(post.path),
        "timestamp": post.timestamp,
        "title": post.title,
        "body": post.body,
        "from": post.source,
    }


def _read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _cmd_forum_post(args: argparse.Namespace) -> int:
    try:
        ref = ForumDepot().post(
            args.title,
            _read_body(args),
            current_post_source(Path.cwd(), override=args.source),
        )
    except (OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "tarav forum post",
        "status": "ok",
        "post": {
            "path": str(ref.path),
            "timestamp": ref.timestamp,
            "title": ref.title,
        },
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"posted: {ref.title} ({ref.timestamp})")
    return 0


def _cmd_forum_check(args: argparse.Namespace) -> int:
    posts = ForumDepot().posts_since(read_cursor().get("last_read"))
    payload = {
        "command": "tarav forum check",
        "unread_count": len(posts),
        "posts": [_post_payload(post) for post in posts],
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"tarav forum: {len(posts)} unread post(s)")
        for post in posts:
            print(f"- {post.timestamp} — {post.title}")
    return 0


def _cmd_forum_read(args: argparse.Namespace) -> int:
    if args.date and args.all:
        raise CliError("choose at most one of --date or --all")
    depot = ForumDepot()
    if args.date:
        posts = depot.read_date(args.date)
        advances_cursor = False
    elif args.all:
        posts = depot.read_all()
        advances_cursor = False
    else:
        posts = depot.posts_since(read_cursor().get("last_read"))
        advances_cursor = True
    payload = {
        "command": "tarav forum read",
        "count": len(posts),
        "cursor_advanced": advances_cursor,
        "posts": [_post_payload(post) for post in posts],
    }
    if advances_cursor:
        mark_read(posts)
    if args.json:
        _print_json(payload)
    else:
        for post in posts:
            print(f"## {post.timestamp} — {post.title}")
            if post.body:
                print(post.body)
            print(f"- from: {post.source}")
            print()
    return 0


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit JSON.")


def register_forum_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "forum",
        help="Cross-project Tarav news board.",
        description="Post and read the machine-local Tarav forum.",
    )
    forum_subparsers = parser.add_subparsers(dest="forum_command", required=True)

    post = forum_subparsers.add_parser("post", help="Append a forum post.")
    _add_json(post)
    post.add_argument("--title", required=True, help="Post title.")
    post.add_argument("--body", help="Post body. If omitted, piped stdin is used.")
    post.add_argument("--from", dest="source", help="Override the source project label.")
    post.set_defaults(handler=_cmd_forum_post)

    check = forum_subparsers.add_parser("check", help="Show unread forum summary.")
    _add_json(check)
    check.set_defaults(handler=_cmd_forum_check)

    read = forum_subparsers.add_parser("read", help="Read forum posts.")
    _add_json(read)
    read.add_argument("--date", help="Read one UTC date file, YYYY-MM-DD.")
    read.add_argument("--all", action="store_true", help="Read every post without moving the cursor.")
    read.set_defaults(handler=_cmd_forum_read)


__all__ = ["register_forum_commands"]
