from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Sequence

from .core import (
    DEFAULT_MARKDOWN_EXCLUDES,
    MarkdownScanConfig,
    collect_block_links,
    find_markdown_blocks,
    lint_markdown_blocks,
    scan_markdown_blocks,
)


def _resolve_scan_targets(root: Path, raw_targets: Sequence[str]) -> tuple[Path, ...]:
    if not raw_targets:
        raw_targets = ["."]

    resolved_targets: list[Path] = []
    for raw_target in raw_targets:
        candidate = Path(raw_target).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (root / candidate).resolve()
        if not resolved.exists():
            raise SystemExit(f"error: target path does not exist: {raw_target}")
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"error: target path escapes --root: {raw_target}") from exc
        resolved_targets.append(resolved)

    return tuple(resolved_targets)


def _build_markdown_scan_config(args: argparse.Namespace) -> MarkdownScanConfig:
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"error: root path does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"error: root path is not a directory: {root}")
    if args.min_level < 1 or args.min_level > 6:
        raise SystemExit("error: --min-level must be between 1 and 6")
    if args.max_level < 1 or args.max_level > 6:
        raise SystemExit("error: --max-level must be between 1 and 6")
    if args.min_level > args.max_level:
        raise SystemExit("error: --min-level cannot be greater than --max-level")

    targets = _resolve_scan_targets(root, args.targets)
    excludes: tuple[str, ...]
    if args.no_default_excludes:
        excludes = tuple(args.exclude)
    else:
        excludes = tuple(DEFAULT_MARKDOWN_EXCLUDES) + tuple(args.exclude)

    return MarkdownScanConfig(
        root=root,
        targets=targets,
        excludes=excludes,
        min_level=args.min_level,
        max_level=args.max_level,
        recursive=not args.no_recursive,
        include_content=args.with_content,
    )


def _cmd_md_blocks(args: argparse.Namespace) -> int:
    config = _build_markdown_scan_config(args)
    files = scan_markdown_blocks(config)

    summary = {
        "root": str(config.root),
        "targets": [str(path.relative_to(config.root)) for path in config.targets],
        "recursive": config.recursive,
        "min_level": config.min_level,
        "max_level": config.max_level,
        "excludes": list(config.excludes),
        "file_count": len(files),
        "block_count": sum(file_data["block_count"] for file_data in files),
    }

    if args.output_mode == "split-temp":
        output_root = Path(tempfile.mkdtemp(prefix="agentos-md-blocks-"))
        files_root = output_root / "files"
        file_entries: list[dict[str, object]] = []

        for file_data in files:
            rel_md_path = Path(file_data["path"])
            output_file = files_root / rel_md_path.parent / f"{rel_md_path.name}.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json.dumps(file_data, indent=2), encoding="utf-8")

            file_entries.append(
                {
                    "path": file_data["path"],
                    "block_count": file_data["block_count"],
                    "json_file": output_file.relative_to(output_root).as_posix(),
                }
            )

        manifest = {
            **summary,
            "output_mode": "split-temp",
            "files": file_entries,
        }
        manifest_path = output_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        payload = {
            **summary,
            "output_mode": "split-temp",
            "output_dir": str(output_root),
            "manifest_path": str(manifest_path),
            "manifest_file_count": len(file_entries),
        }

        if args.json:
            print(json.dumps(payload, indent=2))
            return 0

        print(manifest_path)
        return 0

    payload = {
        **summary,
        "files": files,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if not files:
        print("No markdown files found.")
        return 0

    for file_data in files:
        print(f"{file_data['path']} ({file_data['block_count']} blocks)")
        for block in file_data["blocks"]:
            print(f"  {block['link']} [h{block['level']}] {block['title']}")
    return 0


def _cmd_md_links(args: argparse.Namespace) -> int:
    config = _build_markdown_scan_config(args)
    files = scan_markdown_blocks(config)
    links = collect_block_links(files)
    payload = {
        "root": str(config.root),
        "targets": [str(path.relative_to(config.root)) for path in config.targets],
        "link_count": len(links),
        "links": links,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if not links:
        print("No block links found.")
        return 0

    for link in links:
        print(f"{link['link']}\t{link['title']}")
    return 0


def _cmd_md_lint(args: argparse.Namespace) -> int:
    if args.max_block_lines < 1:
        raise SystemExit("error: --max-block-lines must be >= 1")

    config = _build_markdown_scan_config(args)
    lint_payload = lint_markdown_blocks(
        config=config,
        max_block_lines=args.max_block_lines,
    )
    payload = {
        "root": str(config.root),
        "targets": [str(path.relative_to(config.root)) for path in config.targets],
        "recursive": config.recursive,
        "excludes": list(config.excludes),
        **lint_payload,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if payload["issue_count"] == 0:
            print(
                f"No markdown lint issues found across {payload['file_count']} file(s)."
            )
        else:
            print(
                f"Scanned {payload['file_count']} file(s): "
                f"{payload['error_count']} error(s), {payload['warning_count']} warning(s)"
            )
            for file_report in payload["files"]:
                if file_report["issue_count"] == 0:
                    continue
                print(f"{file_report['path']}:")
                for issue in file_report["issues"]:
                    location = issue.get("path_line", issue["path"])
                    print(
                        f"  [{issue['severity'].upper()}] {issue['code']} "
                        f"@ {location} - {issue['message']}"
                    )

    if args.fail_on == "warning" and payload["issue_count"] > 0:
        return 1
    if args.fail_on == "error" and payload["error_count"] > 0:
        return 1
    return 0


def _cmd_md_find(args: argparse.Namespace) -> int:
    config = _build_markdown_scan_config(args)
    if args.top_k < 1:
        raise SystemExit("error: --top-k must be >= 1")

    try:
        find_payload = find_markdown_blocks(
            config=config,
            query=args.query,
            top_k=args.top_k,
            use_regex=args.regex,
            case_sensitive=args.case_sensitive,
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    payload = {
        "root": str(config.root),
        "targets": [str(path.relative_to(config.root)) for path in config.targets],
        "recursive": config.recursive,
        "min_level": config.min_level,
        "max_level": config.max_level,
        "excludes": list(config.excludes),
        **find_payload,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if payload["match_count"] == 0:
        print("No matching blocks found.")
        return 0

    print(
        f"Found {payload['match_count']} matching block(s); showing top {len(payload['matches'])}."
    )
    for index, match in enumerate(payload["matches"], start=1):
        print(
            f"{index}. {match['link']} [score={match['score']}] "
            f"[h{match['level']}] {match['title']}"
        )
    return 0


def _add_md_scan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "targets",
        nargs="*",
        default=["."],
        help="File(s) or folder(s) to scan (default: current directory).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root used for path normalization.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory or path pattern to exclude (repeatable).",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in excludes (.git, .venv, __pycache__, ...).",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into subdirectories for folder targets.",
    )
    parser.add_argument(
        "--min-level",
        type=int,
        default=1,
        help="Minimum heading level to include in scan (1-6).",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=6,
        help="Maximum heading level to include in scan (1-6).",
    )


def register_mdblocks_commands(subparsers: argparse._SubParsersAction) -> None:
    md_parser = subparsers.add_parser(
        "mdblocks",
        help="Markdown block utilities for block-oriented workflows.",
    )
    md_subparsers = md_parser.add_subparsers(dest="md_command")

    md_blocks_parser = md_subparsers.add_parser(
        "blocks",
        help="Parse markdown headings into deterministic blocks.",
    )
    _add_md_scan_arguments(md_blocks_parser)
    md_blocks_parser.add_argument(
        "--with-content",
        action="store_true",
        help="Include full block content in JSON output.",
    )
    md_blocks_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    md_blocks_parser.add_argument(
        "--output-mode",
        choices=("inline", "split-temp"),
        default="inline",
        help="`inline` prints one combined payload; `split-temp` writes per-file JSON + manifest to a temp folder.",
    )
    md_blocks_parser.set_defaults(handler=_cmd_md_blocks)

    md_links_parser = md_subparsers.add_parser(
        "links",
        help="Emit companion links for markdown blocks.",
    )
    _add_md_scan_arguments(md_links_parser)
    md_links_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    md_links_parser.set_defaults(handler=_cmd_md_links, with_content=False)

    md_lint_parser = md_subparsers.add_parser(
        "lint",
        help="Scan markdown block structure and report deterministic errors/warnings.",
    )
    _add_md_scan_arguments(md_lint_parser)
    md_lint_parser.add_argument(
        "--max-block-lines",
        type=int,
        default=30,
        help="Warn when a block exceeds this line span.",
    )
    md_lint_parser.add_argument(
        "--fail-on",
        choices=("none", "error", "warning"),
        default="none",
        help="Process exit behavior: none=always 0, error=nonzero on errors, warning=nonzero on any issue.",
    )
    md_lint_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    md_lint_parser.set_defaults(handler=_cmd_md_lint, with_content=False)

    md_find_parser = md_subparsers.add_parser(
        "find",
        help="Find best-matching markdown blocks for a query.",
    )
    _add_md_scan_arguments(md_find_parser)
    md_find_parser.add_argument(
        "--query",
        required=True,
        help="Query text or regex pattern (when --regex is set).",
    )
    md_find_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of matches to return.",
    )
    md_find_parser.add_argument(
        "--regex",
        action="store_true",
        help="Treat --query as a regular expression pattern.",
    )
    md_find_parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use case-sensitive matching.",
    )
    md_find_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    md_find_parser.set_defaults(handler=_cmd_md_find, with_content=False)
