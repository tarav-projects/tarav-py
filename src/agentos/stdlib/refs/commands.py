# $kw: ^agentos-stdlib-refs-commands --from Agent.Navigable.Codebase --note [DF] reusable refs behavior lives beneath the Python stdlib namespace matching its CLI --supp ^c20260811-62u
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.git_ops import (
    resolve_repo_file as _resolve_repo_file,
    resolve_repo_relative_path as _resolve_repo_relative_path,
    resolve_repo_root as _resolve_repo_root,
    run_git as _run_git,
)
from agentos._core.json_input import load_json_input as _load_json_input
from agentos._core.text_span import (
    build_line_starts as _build_line_starts,
    extract_text_from_span as _extract_text_from_span,
    find_all_fragment_spans as _find_all_fragment_spans,
    find_fragment_span as _find_fragment_span,
    offset_to_line_column as _offset_to_line_column,
    validate_span as _validate_span,
)
from .ref_path import build_ref_path_uri, parse_ref_path_uri


def _collect_batch_entries(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "references" in payload:
            entries = payload["references"]
        elif "matches" in payload:
            entries = payload["matches"]
        elif "items" in payload:
            entries = payload["items"]
        else:
            return [payload]
        if not isinstance(entries, list):
            raise CliError("batch input field must be a JSON array")
        return entries
    raise CliError("batch input must be a JSON array or object")


def _extract_reference_from_entry(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise CliError("batch entry must be a JSON object")
    raw_reference: object = entry["reference"] if "reference" in entry else entry
    if not isinstance(raw_reference, dict):
        raise CliError("reference must be a JSON object")
    return raw_reference


def _normalize_git_line_span_reference(raw_reference: dict[str, object]) -> dict[str, object]:
    try:
        ref_class = str(raw_reference["class"])
        if ref_class != "git_line_span":
            raise CliError(f"unsupported reference class: {ref_class}")

        path = str(raw_reference["path"])
        if not path:
            raise CliError("reference path must not be empty")

        commit = str(raw_reference.get("commit", "")).strip()

        start = raw_reference["start"]
        end = raw_reference["end"]
        if not isinstance(start, dict) or not isinstance(end, dict):
            raise CliError("reference start/end must be objects")

        start_line = int(start["line"])
        start_column = int(start["column"])
        end_line = int(end["line"])
        end_column = int(end["column"])
    except KeyError as exc:
        raise CliError(f"missing required reference field: {exc}") from exc
    except ValueError as exc:
        raise CliError(f"reference line/column values must be integers: {exc}") from exc
    except TypeError as exc:
        raise CliError(f"invalid reference field type: {exc}") from exc

    return {
        "class": "git_line_span",
        "path": path,
        "commit": commit,
        "start": {"line": start_line, "column": start_column},
        "end": {"line": end_line, "column": end_column},
    }


def _resolve_normalized_reference(
    repo_root: Path,
    normalized_reference: dict[str, object],
    *,
    resolve_commit: str | None = None,
) -> tuple[dict[str, object], str]:
    reference_path = str(normalized_reference["path"])
    if resolve_commit is None:
        target_file = _resolve_repo_file(repo_root, reference_path)
        lines = target_file.read_text(encoding="utf-8").splitlines()
        relative_path = str(target_file.relative_to(repo_root).as_posix())
    else:
        relative_path = _resolve_repo_relative_path(repo_root, reference_path)
        try:
            lines = _run_git(repo_root, "show", f"{resolve_commit}:{relative_path}").splitlines()
        except CliError as exc:
            raise CliError(f"file not found at commit {resolve_commit}: {relative_path}") from exc
    if not lines:
        raise CliError("target file is empty")

    start = normalized_reference["start"]
    end = normalized_reference["end"]
    if not isinstance(start, dict) or not isinstance(end, dict):
        raise CliError("normalized reference start/end must be objects")

    start_line = int(start["line"])
    start_column = int(start["column"])
    end_line = int(end["line"])
    end_column = int(end["column"])
    _validate_span(lines, start_line, end_line, start_column, end_column)

    extracted_text = _extract_text_from_span(lines, start_line, end_line, start_column, end_column)
    return {
        "class": "git_line_span",
        "repo_root": str(repo_root),
        "commit": str(normalized_reference["commit"]),
        "path": relative_path,
        "start": {"line": start_line, "column": start_column},
        "end": {"line": end_line, "column": end_column},
    }, extracted_text


def _resolve_repo_hash(repo_root: Path) -> str:
    try:
        roots_raw = _run_git(repo_root, "rev-list", "--max-parents=0", "HEAD", "--reverse")
    except CliError as exc:
        raise CliError(f"cannot compute repo hash for repository: {repo_root} ({exc})") from exc

    roots = [line.strip() for line in roots_raw.splitlines() if line.strip()]
    if not roots:
        raise CliError(f"cannot compute repo hash for repository: {repo_root} (no root commit found)")
    return roots[0]


def _emit_single_reference_output(
    args: argparse.Namespace,
    payload: dict[str, object],
    *,
    repo_root: Path,
) -> int:
    reference = payload.get("reference")
    if not isinstance(reference, dict):
        raise CliError("internal error: payload reference must be a JSON object")

    repo_hash = _resolve_repo_hash(repo_root)
    ref_path = build_ref_path_uri(repo_hash, reference)
    if bool(args.output_ref_path):
        print(ref_path)
        return 0

    payload["repo_hash"] = repo_hash
    payload["ref_path"] = ref_path
    print(json.dumps(payload))
    return 0


def _emit_match_list_output(
    args: argparse.Namespace,
    payload: dict[str, object],
    *,
    repo_root: Path,
) -> int:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise CliError("internal error: payload matches must be a JSON array")

    repo_hash = _resolve_repo_hash(repo_root)
    ref_paths: list[str] = []
    for match in matches:
        if not isinstance(match, dict):
            raise CliError("internal error: match entry must be a JSON object")
        reference = match.get("reference")
        if not isinstance(reference, dict):
            raise CliError("internal error: match reference must be a JSON object")
        ref_path = build_ref_path_uri(repo_hash, reference)
        match["ref_path"] = ref_path
        ref_paths.append(ref_path)

    if bool(args.output_ref_path):
        if ref_paths:
            print("\n".join(ref_paths))
        return 0

    payload["repo_hash"] = repo_hash
    print(json.dumps(payload))
    return 0


def _add_ref_output_arguments(parser: argparse.ArgumentParser) -> None:
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output-json",
        action="store_true",
        help="Emit structured JSON output (default).",
    )
    output_group.add_argument(
        "--output-ref-path",
        action="store_true",
        help="Emit git-ref URI output. For ref-list-text-matches, prints one URI per line.",
    )


def _git_path_is_dirty(repo_root: Path, relative_path: str) -> bool:
    porcelain = _run_git(repo_root, "status", "--porcelain", "--", relative_path)
    return bool(porcelain.strip())


def _resolve_reference_commit(
    repo_root: Path,
    relative_path: str,
    *,
    allow_commit: bool,
) -> tuple[str, bool, bool]:
    dirty_before = _git_path_is_dirty(repo_root, relative_path)
    if not dirty_before:
        return _run_git(repo_root, "rev-parse", "HEAD"), False, False

    if not allow_commit:
        raise CliError(
            "target file has uncommitted changes: "
            f"{relative_path} (pass --commit to add/commit this file and produce an updated reference)"
        )

    try:
        _run_git(repo_root, "add", "--", relative_path)
        _run_git(
            repo_root,
            "commit",
            "-m",
            f"chore(agentos): update {relative_path} for git-refs",
            "--",
            relative_path,
        )
    except CliError as exc:
        raise CliError(f"failed to commit dirty target file {relative_path}: {exc}") from exc

    return _run_git(repo_root, "rev-parse", "HEAD"), True, True


def _cmd_refs_from_span(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    target_file = _resolve_repo_file(repo_root, args.file_path)
    relative_path = str(target_file.relative_to(repo_root).as_posix())
    commit, auto_committed, dirty_before = _resolve_reference_commit(
        repo_root,
        relative_path,
        allow_commit=bool(args.commit),
    )

    lines = target_file.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise CliError("target file is empty")

    start_line = args.start_line
    end_line = args.end_line if args.end_line is not None else start_line
    if start_line < 1:
        raise CliError("start line must be >= 1")
    if end_line < start_line:
        raise CliError("end line must be >= start line")
    if end_line > len(lines):
        raise CliError(f"end line {end_line} exceeds file length {len(lines)}")

    start_column = args.start_column
    end_column = args.end_column
    if end_column is None:
        end_column = len(lines[end_line - 1]) + 1

    _validate_span(lines, start_line, end_line, start_column, end_column)
    extracted_text = _extract_text_from_span(lines, start_line, end_line, start_column, end_column)

    payload = {
        "status": "ok",
        "command": "git-refs ref-from-span",
        "reference": {
            "class": "git_line_span",
            "repo_root": str(repo_root),
            "commit": commit,
            "path": relative_path,
            "start": {"line": start_line, "column": start_column},
            "end": {"line": end_line, "column": end_column},
        },
        "extracted_text": extracted_text,
        "auto_committed": auto_committed,
        "dirty_before": dirty_before,
    }
    return _emit_single_reference_output(args, payload, repo_root=repo_root)


def _cmd_refs_from_text(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    target_file = _resolve_repo_file(repo_root, args.file_path)
    relative_path = str(target_file.relative_to(repo_root).as_posix())
    commit, auto_committed, dirty_before = _resolve_reference_commit(
        repo_root,
        relative_path,
        allow_commit=bool(args.commit),
    )

    full_text = target_file.read_text(encoding="utf-8")
    if not full_text:
        raise CliError("target file is empty")

    start_offset, end_offset = _find_fragment_span(full_text, args.fragment, args.occurrence)
    line_starts = _build_line_starts(full_text)
    start_line, start_column = _offset_to_line_column(line_starts, start_offset)
    end_line, end_column = _offset_to_line_column(line_starts, end_offset)

    payload = {
        "status": "ok",
        "command": "git-refs ref-from-text",
        "reference": {
            "class": "git_line_span",
            "repo_root": str(repo_root),
            "commit": commit,
            "path": relative_path,
            "start": {"line": start_line, "column": start_column},
            "end": {"line": end_line, "column": end_column},
        },
        "extracted_text": full_text[start_offset:end_offset],
        "match": {"occurrence": args.occurrence},
        "auto_committed": auto_committed,
        "dirty_before": dirty_before,
    }
    return _emit_single_reference_output(args, payload, repo_root=repo_root)


def _cmd_refs_list_text_matches(args: argparse.Namespace) -> int:
    if args.max_matches < 1:
        raise CliError("max matches must be >= 1")

    repo_root = _resolve_repo_root(args.repo)
    target_file = _resolve_repo_file(repo_root, args.file_path)
    relative_path = str(target_file.relative_to(repo_root).as_posix())
    commit, auto_committed, dirty_before = _resolve_reference_commit(
        repo_root,
        relative_path,
        allow_commit=bool(args.commit),
    )

    full_text = target_file.read_text(encoding="utf-8")
    if not full_text:
        raise CliError("target file is empty")

    all_matches = _find_all_fragment_spans(full_text, args.fragment)
    limited_matches = all_matches[: args.max_matches]
    line_starts = _build_line_starts(full_text)

    match_payloads = []
    for idx, (start_offset, end_offset) in enumerate(limited_matches, start=1):
        start_line, start_column = _offset_to_line_column(line_starts, start_offset)
        end_line, end_column = _offset_to_line_column(line_starts, end_offset)
        match_payloads.append(
            {
                "occurrence": idx,
                "reference": {
                    "class": "git_line_span",
                    "repo_root": str(repo_root),
                    "commit": commit,
                    "path": relative_path,
                    "start": {"line": start_line, "column": start_column},
                    "end": {"line": end_line, "column": end_column},
                },
                "extracted_text": full_text[start_offset:end_offset],
            }
        )

    payload = {
        "status": "ok",
        "command": "git-refs ref-list-text-matches",
        "query": {
            "text": args.fragment,
            "max_matches": args.max_matches,
        },
        "total_matches": len(all_matches),
        "returned_matches": len(match_payloads),
        "truncated": len(all_matches) > len(match_payloads),
        "matches": match_payloads,
        "auto_committed": auto_committed,
        "dirty_before": dirty_before,
    }
    return _emit_match_list_output(args, payload, repo_root=repo_root)


def _cmd_refs_resolve_batch(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    head_commit = _run_git(repo_root, "rev-parse", "HEAD")
    resolve_commit = head_commit
    if args.resolve_at_commit is not None:
        try:
            resolve_commit = _run_git(repo_root, "rev-parse", "--verify", args.resolve_at_commit)
        except CliError as exc:
            raise CliError(f"invalid resolve-at-commit value: {args.resolve_at_commit} ({exc})") from exc

    payload = _load_json_input(args.input_path)
    entries = _collect_batch_entries(payload)

    results: list[dict[str, object]] = []
    for idx, entry in enumerate(entries, start=1):
        result: dict[str, object]
        try:
            raw_reference = _extract_reference_from_entry(entry)
            normalized_reference = _normalize_git_line_span_reference(raw_reference)

            reference_commit = str(normalized_reference["commit"]).strip()
            commit_matches_resolve = (
                None if not reference_commit else reference_commit == resolve_commit
            )
            commit_matches_head = None if not reference_commit else reference_commit == head_commit
            if args.require_commit_match and commit_matches_resolve is False:
                raise CliError(
                    f"reference commit mismatch (reference={reference_commit}, resolve={resolve_commit})"
                )
            if not reference_commit:
                normalized_reference["commit"] = resolve_commit

            resolved_reference, extracted_text = _resolve_normalized_reference(
                repo_root,
                normalized_reference,
                resolve_commit=resolve_commit,
            )

            result = {
                "index": idx,
                "status": "ok",
                "reference": resolved_reference,
                "reference_commit_matches_resolve_commit": commit_matches_resolve,
                "reference_commit_matches_head": commit_matches_head,
                "extracted_text": extracted_text,
            }
        except CliError as exc:
            result = {"index": idx, "status": "error", "error": str(exc)}
        results.append(result)

    failed_count = sum(1 for item in results if item.get("status") == "error")
    resolved_count = len(results) - failed_count

    output = {
        "status": "ok",
        "command": "git-refs deref-batch",
        "repo_root": str(repo_root),
        "head_commit": head_commit,
        "resolve_commit": resolve_commit,
        "input_count": len(entries),
        "resolved_count": resolved_count,
        "failed_count": failed_count,
        "strict": bool(args.strict),
        "resolve_at_commit_specified": args.resolve_at_commit is not None,
        "require_commit_match": bool(args.require_commit_match),
        "results": results,
    }
    print(json.dumps(output))

    if args.strict and failed_count > 0:
        return 1
    return 0


def _cmd_refs_from_markers(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    target_file = _resolve_repo_file(repo_root, args.file_path)
    relative_path = str(target_file.relative_to(repo_root).as_posix())
    commit, auto_committed, dirty_before = _resolve_reference_commit(
        repo_root,
        relative_path,
        allow_commit=bool(args.commit),
    )

    full_text = target_file.read_text(encoding="utf-8")
    if not full_text:
        raise CliError("target file is empty")

    start_offset, start_end_offset = _find_fragment_span(
        full_text,
        args.start_fragment,
        args.start_occurrence,
    )
    try:
        end_offset, end_end_offset = _find_fragment_span(
            full_text,
            args.end_fragment,
            args.end_occurrence,
            search_start=start_end_offset,
        )
    except CliError as exc:
        raise CliError(
            "end marker not found after selected start marker "
            f"(start occurrence {args.start_occurrence}, requested end occurrence {args.end_occurrence})"
        ) from exc

    line_starts = _build_line_starts(full_text)
    start_line, start_column = _offset_to_line_column(line_starts, start_offset)
    end_line, end_column = _offset_to_line_column(line_starts, end_end_offset)

    payload = {
        "status": "ok",
        "command": "git-refs ref-from-markers",
        "reference": {
            "class": "git_line_span",
            "repo_root": str(repo_root),
            "commit": commit,
            "path": relative_path,
            "start": {"line": start_line, "column": start_column},
            "end": {"line": end_line, "column": end_column},
        },
        "extracted_text": full_text[start_offset:end_end_offset],
        "auto_committed": auto_committed,
        "dirty_before": dirty_before,
        "match": {
            "start_text": args.start_fragment,
            "start_occurrence": args.start_occurrence,
            "end_text": args.end_fragment,
            "end_occurrence": args.end_occurrence,
            "end_match_start_offset": end_offset,
        },
    }
    return _emit_single_reference_output(args, payload, repo_root=repo_root)


def _cmd_refs_repo_hash(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    repo_hash = _resolve_repo_hash(repo_root)
    if args.output_json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "command": "git-refs repo-hash",
                    "repo_root": str(repo_root),
                    "repo_hash": repo_hash,
                }
            )
        )
        return 0

    print(repo_hash)
    return 0


def _cmd_refs_deref_ref_path(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    expected_repo_hash = _resolve_repo_hash(repo_root)
    parsed_ref = parse_ref_path_uri(args.ref_path)
    uri_repo_hash = str(parsed_ref["repo_hash"])
    repo_hash_match = uri_repo_hash == expected_repo_hash
    if not repo_hash_match and not args.allow_repo_hash_mismatch:
        raise CliError(
            "ref-path repo hash does not match target repository "
            f"(uri={uri_repo_hash}, repo={expected_repo_hash})"
        )

    normalized_reference = {
        "class": "git_line_span",
        "path": str(parsed_ref["path"]),
        "commit": str(parsed_ref["commit"]),
        "start": parsed_ref["start"],
        "end": parsed_ref["end"],
    }
    resolved_reference, extracted_text = _resolve_normalized_reference(
        repo_root,
        normalized_reference,
        resolve_commit=str(parsed_ref["commit"]),
    )

    output = {
        "status": "ok",
        "command": "git-refs deref-ref-path",
        "repo_root": str(repo_root),
        "ref_path": args.ref_path,
        "repo_hash": expected_repo_hash,
        "uri_repo_hash": uri_repo_hash,
        "repo_hash_match": repo_hash_match,
        "reference": resolved_reference,
        "extracted_text": extracted_text,
    }
    print(json.dumps(output))
    return 0


def register_refs_commands(subparsers: argparse._SubParsersAction) -> None:
    refs_parser = subparsers.add_parser(
        "git-refs",
        help="Git-grounded line-span reference utilities.",
    )
    refs_subparsers = refs_parser.add_subparsers(dest="git_refs_command", required=True)

    repo_hash_parser = refs_subparsers.add_parser(
        "repo-hash",
        help="Print stable repository identifier (first/root commit hash).",
    )
    repo_hash_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    repo_hash_parser.add_argument(
        "--output-json",
        action="store_true",
        help="Emit JSON output with repo_root and repo_hash.",
    )
    repo_hash_parser.set_defaults(handler=_cmd_refs_repo_hash)

    deref_ref_path_parser = refs_subparsers.add_parser(
        "deref-ref-path",
        help="Resolve extracted text from one git-ref URI.",
    )
    deref_ref_path_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    deref_ref_path_parser.add_argument(
        "--ref-path",
        required=True,
        dest="ref_path",
        help=(
            "git-ref URI to resolve "
            "(format: git-ref://<repo-hash>/blob/<commit>/<path>#LxCy-LzCw)."
        ),
    )
    deref_ref_path_parser.add_argument(
        "--allow-repo-hash-mismatch",
        action="store_true",
        help="Resolve even when URI repo hash differs from the target repository hash.",
    )
    deref_ref_path_parser.set_defaults(handler=_cmd_refs_deref_ref_path)

    from_span_parser = refs_subparsers.add_parser(
        "ref-from-span",
        help="Create one formal reference JSON from a file line span.",
    )
    from_span_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    from_span_parser.add_argument(
        "--file",
        required=True,
        dest="file_path",
        help="Target file path (absolute or repository-relative).",
    )
    _add_ref_output_arguments(from_span_parser)
    from_span_parser.add_argument(
        "--commit",
        action="store_true",
        help="If target file is dirty, git add/commit it before creating the reference.",
    )
    from_span_parser.add_argument(
        "--start-line",
        required=True,
        type=int,
        dest="start_line",
        help="1-based start line.",
    )
    from_span_parser.add_argument(
        "--end-line",
        type=int,
        dest="end_line",
        help="1-based end line (defaults to start line).",
    )
    from_span_parser.add_argument(
        "--start-column",
        type=int,
        default=1,
        dest="start_column",
        help="1-based start column (default: 1).",
    )
    from_span_parser.add_argument(
        "--end-column",
        type=int,
        dest="end_column",
        help="1-based exclusive end column (defaults to end line length + 1).",
    )
    from_span_parser.set_defaults(handler=_cmd_refs_from_span)

    from_text_parser = refs_subparsers.add_parser(
        "ref-from-text",
        help="Create one formal reference JSON from a text fragment in a file.",
    )
    from_text_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    from_text_parser.add_argument(
        "--file",
        required=True,
        dest="file_path",
        help="Target file path (absolute or repository-relative).",
    )
    _add_ref_output_arguments(from_text_parser)
    from_text_parser.add_argument(
        "--commit",
        action="store_true",
        help="If target file is dirty, git add/commit it before creating the reference.",
    )
    from_text_parser.add_argument(
        "--text",
        required=True,
        dest="fragment",
        help="Text fragment to search in the file.",
    )
    from_text_parser.add_argument(
        "--occurrence",
        type=int,
        default=1,
        dest="occurrence",
        help="1-based occurrence index when multiple matches exist (default: 1).",
    )
    from_text_parser.set_defaults(handler=_cmd_refs_from_text)

    list_matches_parser = refs_subparsers.add_parser(
        "ref-list-text-matches",
        help="Create references for all matches of a text fragment in a file.",
    )
    list_matches_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    list_matches_parser.add_argument(
        "--file",
        required=True,
        dest="file_path",
        help="Target file path (absolute or repository-relative).",
    )
    _add_ref_output_arguments(list_matches_parser)
    list_matches_parser.add_argument(
        "--commit",
        action="store_true",
        help="If target file is dirty, git add/commit it before creating references.",
    )
    list_matches_parser.add_argument(
        "--text",
        required=True,
        dest="fragment",
        help="Text fragment to search in the file.",
    )
    list_matches_parser.add_argument(
        "--max-matches",
        type=int,
        default=100,
        dest="max_matches",
        help="Maximum number of matches returned (default: 100).",
    )
    list_matches_parser.set_defaults(handler=_cmd_refs_list_text_matches)

    resolve_batch_parser = refs_subparsers.add_parser(
        "deref-batch",
        help="Resolve a batch of git_line_span references into extracted text.",
    )
    resolve_batch_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    resolve_batch_parser.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="Path to input JSON (use '-' to read from stdin).",
    )
    resolve_batch_parser.add_argument(
        "--strict",
        action="store_true",
        dest="strict",
        help="Return exit code 1 if any reference fails to resolve.",
    )
    resolve_batch_parser.add_argument(
        "--resolve-at-commit",
        dest="resolve_at_commit",
        help="Commit-ish to resolve file content from (default: HEAD).",
    )
    resolve_batch_parser.add_argument(
        "--require-commit-match",
        action="store_true",
        dest="require_commit_match",
        help="Treat commit mismatch between reference and resolution commit as an error.",
    )
    resolve_batch_parser.set_defaults(handler=_cmd_refs_resolve_batch)

    from_markers_parser = refs_subparsers.add_parser(
        "ref-from-markers",
        help="Create one reference from start/end marker text delimiting a block.",
    )
    from_markers_parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository (default: current directory).",
    )
    from_markers_parser.add_argument(
        "--file",
        required=True,
        dest="file_path",
        help="Target file path (absolute or repository-relative).",
    )
    _add_ref_output_arguments(from_markers_parser)
    from_markers_parser.add_argument(
        "--commit",
        action="store_true",
        help="If target file is dirty, git add/commit it before creating the reference.",
    )
    from_markers_parser.add_argument(
        "--start-text",
        required=True,
        dest="start_fragment",
        help="Text fragment that marks the block start (inclusive).",
    )
    from_markers_parser.add_argument(
        "--end-text",
        required=True,
        dest="end_fragment",
        help="Text fragment that marks the block end (inclusive).",
    )
    from_markers_parser.add_argument(
        "--start-occurrence",
        type=int,
        default=1,
        dest="start_occurrence",
        help="1-based start marker occurrence in file (default: 1).",
    )
    from_markers_parser.add_argument(
        "--end-occurrence",
        type=int,
        default=1,
        dest="end_occurrence",
        help="1-based end marker occurrence after the chosen start marker (default: 1).",
    )
    from_markers_parser.set_defaults(handler=_cmd_refs_from_markers)
