# $kw: ^workspaces-commands --from Run.Workspace --from Poi.Unlock.Token --note [CT] git is initialized inside a workspace and never around one --supp ^c20260809-90u ^<anchor-on-landing>
"""Thin argparse handlers over the workspace operations.

`init` is the only gated one. Its refusal names the guide command and never the
token: a refusal that printed the receipt would hand over exactly what it was
asking the caller to go and read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tarav.l0._core.errors import CliError

from .guide import GuideError, guide_text, guide_token
from .manifest import ManifestError, read_manifest, render_agents_md
from .root import AGENTS_FILENAME, resolve_workspaces_root

UNREADABLE = "unreadable"


DEFAULT_HARVESTED_DAYS = 14
DEFAULT_OPEN_DAYS = 90


def _cmd_guide(args: argparse.Namespace) -> int:
    """Print the surface, token last, so reading it is how you get the receipt."""
    try:
        print(guide_text().rstrip("\n"))
    except GuideError as error:
        raise CliError(str(error)) from error
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        expected = guide_token()
    except GuideError as error:
        raise CliError(str(error)) from error
    if args.unlock != expected:
        raise CliError(
            "creating a workspace requires the current unlock receipt for the "
            "workspaces guide. Run `tarav workspace guide`, read it, and pass "
            "its token as --unlock."
        )

    root = resolve_workspaces_root(args.root)
    _refuse_inside_a_worktree(root)

    created_at = datetime.now(timezone.utc)
    slug = f"{created_at:%Y%m%d}-{args.slug}"
    path = root / slug
    if path.exists():
        raise CliError(f"a workspace named {slug} already exists at {path}")

    path.mkdir(parents=True)
    (path / AGENTS_FILENAME).write_text(
        render_agents_md(
            slug=slug,
            kind=args.kind,
            purpose=args.purpose or "Not yet stated.",
            provenance=args.seed or "Not yet stated.",
            created=created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        encoding="utf-8",
    )
    _git_init(path, slug)
    print(json.dumps({"status": "ok", "slug": slug, "path": str(path)}, indent=2))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = resolve_workspaces_root(args.root)
    rows = [_row(path) for path in _workspace_dirs(root)]
    if args.json:
        print(json.dumps({"status": "ok", "workspaces": rows}, indent=2))
        return 0
    if not rows:
        print(f"no workspaces under {root}")
        return 0
    for row in rows:
        print(
            f"{row['slug']}  {row['status']:<10} {row['kind']:<18} "
            f"{row['age_days']}d  extracted: {row['extracted']}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    root = resolve_workspaces_root(args.root)
    path = root / args.slug
    if not path.is_dir():
        raise CliError(f"no workspace named {args.slug} under {root}")

    agents = path / AGENTS_FILENAME
    text = agents.read_text(encoding="utf-8") if agents.is_file() else ""
    row = _row(path)
    files = sorted(item.name for item in path.iterdir() if item.name != ".git")
    if args.json:
        print(json.dumps({**row, "files": files, "agents_md": text}, indent=2))
        return 0
    print(text.rstrip("\n") or f"{args.slug} has no {AGENTS_FILENAME}")
    print("\nfiles: " + ", ".join(files))
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    """List what is disposable; delete only when explicitly told to.

    A workspace is a `Volatile.Surface` and deleting one is routine by design,
    but "routine" is about the decision, not about doing it unasked.
    """
    root = resolve_workspaces_root(args.root)
    candidates = [
        {**_row(path), "reason": reason}
        for path in _workspace_dirs(root)
        if (reason := _sweep_reason(_row(path), args)) is not None
    ]
    if args.apply:
        for candidate in candidates:
            _remove(root / str(candidate["slug"]))
    payload = {
        "status": "ok",
        "applied": bool(args.apply),
        "candidates": candidates,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    if not candidates:
        print(f"nothing to sweep under {root}")
        return 0
    verb = "deleted" if args.apply else "would delete"
    for candidate in candidates:
        print(f"{verb} {candidate['slug']}  ({candidate['reason']})")
    if not args.apply:
        print("\nre-run with --apply to delete them")
    return 0


def _sweep_reason(row: dict[str, object], args: argparse.Namespace) -> str | None:
    """Why this workspace is disposable, or None.

    Status first, age second: a finished workspace is disposable because its
    work left, not because time passed. An unreadable one is never swept — it is
    exactly the case a person should look at.
    """
    age = int(row["age_days"])
    status = str(row["status"])
    if status == UNREADABLE:
        return None
    if status in {"harvested", "abandoned"} and age >= args.harvested_days:
        return f"{status} and untouched for {age}d"
    if status == "open" and age >= args.open_days:
        return f"idle for {age}d"
    return None


def _workspace_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(item for item in root.iterdir() if item.is_dir())


def _row(path: Path) -> dict[str, object]:
    """One listing row.

    A workspace whose manifest cannot be read is reported as unreadable rather
    than skipped: a disposal listing that quietly drops rows is worse than one
    that admits it does not understand something.
    """
    age_days = max(
        0,
        (
            datetime.now(timezone.utc)
            - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        ).days,
    )
    base: dict[str, object] = {"slug": path.name, "age_days": age_days}
    try:
        manifest = read_manifest(path / AGENTS_FILENAME)
    except ManifestError:
        return {**base, "status": UNREADABLE, "kind": UNREADABLE, "extracted": UNREADABLE}
    return {
        **base,
        "status": manifest.status.value,
        "kind": manifest.kind,
        "extracted": manifest.extracted,
    }


def _refuse_inside_a_worktree(root: Path) -> None:
    """A workspace is its own repository and never nested inside another one."""
    probe = root if root.exists() else root.parent
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=probe if probe.exists() else Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip() == "true":
        raise CliError(
            f"{root} is inside a git worktree; a workspace holds its own git "
            "repository and is never created inside another one"
        )


def _git_init(path: Path, slug: str) -> None:
    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", f"init {slug}"],
    ):
        result = subprocess.run(argv, cwd=path, capture_output=True, text=True)
        if result.returncode != 0:


            _remove(path)
            raise CliError(
                f"could not initialize the workspace repository: "
                f"{result.stderr.strip() or ' '.join(argv)}"
            )


def _remove(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        help="Workspaces root (default ~/.tarav/workspaces, TARAV_WORKSPACES_ROOT).",
    )


def register_workspace_commands(subparsers) -> None:  # noqa: ANN001
    parser = subparsers.add_parser(
        "workspace", help="One-run agentic workspaces, deletable whole."
    )
    commands = parser.add_subparsers(dest="workspace_command", required=True)

    guide_parser = commands.add_parser(
        "guide", help="Print the workspaces guide and its unlock token."
    )
    guide_parser.set_defaults(handler=_cmd_guide)

    init_parser = commands.add_parser("init", help="Create one workspace.")
    _add_root_argument(init_parser)
    init_parser.add_argument("--slug", required=True, help="Short name for the run.")
    init_parser.add_argument(
        "--kind", required=True, help="Which workflow this workspace serves."
    )
    init_parser.add_argument(
        "--unlock",
        help="Unlock receipt from `tarav workspace guide`.",
    )
    init_parser.add_argument("--purpose", help="One line: what this exists to answer.")
    init_parser.add_argument(
        "--seed", help="What this was seeded from, and at what version."
    )
    init_parser.set_defaults(handler=_cmd_init)

    list_parser = commands.add_parser("list", help="List every workspace and its state.")
    _add_root_argument(list_parser)
    list_parser.add_argument("--json", action="store_true", help="Emit structured rows.")
    list_parser.set_defaults(handler=_cmd_list)

    show_parser = commands.add_parser("show", help="Show one workspace.")
    _add_root_argument(show_parser)
    show_parser.add_argument("--slug", required=True, help="Workspace directory name.")
    show_parser.add_argument("--json", action="store_true", help="Emit the full record.")
    show_parser.set_defaults(handler=_cmd_show)

    sweep_parser = commands.add_parser(
        "sweep", help="List disposable workspaces; --apply deletes them."
    )
    _add_root_argument(sweep_parser)
    sweep_parser.add_argument(
        "--harvested-days",
        type=int,
        default=DEFAULT_HARVESTED_DAYS,
        help=f"Age for a harvested or abandoned workspace (default {DEFAULT_HARVESTED_DAYS}).",
    )
    sweep_parser.add_argument(
        "--open-days",
        type=int,
        default=DEFAULT_OPEN_DAYS,
        help=f"Age for an untouched open workspace (default {DEFAULT_OPEN_DAYS}).",
    )
    sweep_parser.add_argument(
        "--apply", action="store_true", help="Delete the listed workspaces."
    )
    sweep_parser.add_argument("--json", action="store_true", help="Emit structured rows.")
    sweep_parser.set_defaults(handler=_cmd_sweep)
