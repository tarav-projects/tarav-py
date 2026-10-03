"""CLI adapter for the Workspaces library."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from tarav.l0._core.errors import CliError

from .depot import WorkspaceDepot, WorkspaceError
from .model import WorkspaceManifest


def _depot(args) -> WorkspaceDepot:
    return WorkspaceDepot(args.root)


def _output(value) -> int:
    print(json.dumps(value, indent=2))
    return 0


def _cmd_create(args) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = WorkspaceManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8"), strict=True
    )
    workspace = _depot(args).create(manifest, seed_root=manifest_path.parent / "seeds")
    return _output({"status": "ok", "id": str(workspace.id), "root": str(workspace.root)})


def _cmd_list(args) -> int:
    workspaces = _depot(args).list(project_id=args.project_id, status=args.status)
    return _output({"status": "ok", "workspaces": [
        {"id": str(item.id), "label": item.manifest.label,
         "state": item.manifest.status, "root": str(item.root)} for item in workspaces
    ]})


def _cmd_show(args) -> int:
    workspace = _depot(args).open(args.id)
    return _output({"status": "ok", "root": str(workspace.root),
                    "manifest": workspace.to_record(),
                    "setup": _depot(args).setup_record(workspace).model_dump(mode="json")})


def _cmd_check(args) -> int:
    workspace = _depot(args).open(args.id)
    findings = [poi.as_dict(detail=True) for check in workspace.checks
                for poi in check.run().pois()]
    return _output({"status": "ok", "pois": findings})


def _cmd_reset(args) -> int:
    depot = _depot(args)
    workspace = depot.open(args.id)
    try:
        setup = depot.reset(workspace)
    except WorkspaceError as error:
        if error.pois:
            _output({"status": "refused", "pois": [poi.as_dict(detail=True)
                                                    for poi in error.pois]})
            return 1
        raise CliError(str(error)) from error
    return _output({"status": "ok", "setup": setup.model_dump(mode="json")})


def _cmd_clone(args) -> int:
    depot = _depot(args)
    clone = depot.clone(depot.open(args.id), label=args.label)
    return _output({"status": "ok", "id": str(clone.id), "root": str(clone.root)})


def _cmd_status(args) -> int:
    depot = _depot(args)
    workspace = depot.set_status(depot.open(args.id), args.state,
                                 extracted=args.extracted)
    return _output({"status": "ok", "id": str(workspace.id),
                    "state": workspace.manifest.status})


def _cmd_remove(args) -> int:
    depot = _depot(args)
    workspace = depot.open(args.id)
    try:
        depot.remove(workspace)
    except WorkspaceError as error:
        if error.pois:
            _output({"status": "refused", "pois": [poi.as_dict(detail=True)
                                                    for poi in error.pois]})
            return 1
        raise CliError(str(error)) from error
    return _output({"status": "ok", "removed": str(workspace.id)})


def _cmd_sweep(args) -> int:
    """Only completed workspaces are eligible; active work is never aged out."""
    if args.days < 0:
        raise CliError("--days must be nonnegative")
    depot = _depot(args)
    threshold = datetime.now(timezone.utc) - timedelta(days=args.days)
    candidates = [workspace for workspace in depot.list()
                  if workspace.manifest.status in {"harvested", "abandoned"}
                  and datetime.fromtimestamp(workspace.root.stat().st_mtime,
                                             tz=timezone.utc) < threshold]
    if args.apply:
        for workspace in candidates:
            depot.remove(workspace)
    return _output({"status": "ok", "applied": args.apply,
                    "ids": [str(workspace.id) for workspace in candidates]})


def _cli(handler):
    def run(args):
        try:
            return handler(args)
        except (OSError, ValueError) as error:
            raise CliError(str(error)) from error
    return run


# tarav.breadcrumb 54bd6029de76f231667e75b7325a4b2a30fd9c4421a118f1d64f60839ae95e9f
def register_workspace_commands(subparsers) -> None:
    parser = subparsers.add_parser("workspace", help="Manage manifest-backed workspaces.")
    commands = parser.add_subparsers(dest="workspace_command", required=True)
    for name, handler, help_text in (
        ("create", _cmd_create, "Create from a workspace manifest JSON file."),
        ("list", _cmd_list, "List workspaces."),
        ("show", _cmd_show, "Show a manifest and its last setup."),
        ("check", _cmd_check, "Run workspace checks and report POIs."),
        ("reset", _cmd_reset, "Recreate the initial state if no work would be lost."),
        ("clone", _cmd_clone, "Create another workspace from retained seeds."),
        ("status", _cmd_status, "Change a workspace lifecycle state."),
        ("remove", _cmd_remove, "Remove a completed workspace through Git."),
        ("sweep", _cmd_sweep, "Find or remove aged completed workspaces."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--root", type=Path, help="Workspaces depot root.")
        if name == "create":
            command.add_argument("--manifest", required=True, type=Path)
        elif name == "list":
            command.add_argument("--project-id")
            command.add_argument("--status", choices=("open", "harvested", "abandoned"))
        elif name != "sweep":
            command.add_argument("--id", required=True, help="Workspace UUID.")
        if name == "clone":
            command.add_argument("--label", required=True)
        elif name == "status":
            command.add_argument("--state", required=True,
                                 choices=("open", "harvested", "abandoned"))
            command.add_argument("--extracted")
        elif name == "sweep":
            command.add_argument("--days", type=int, default=14)
            command.add_argument("--apply", action="store_true")
        command.set_defaults(handler=_cli(handler))


__all__ = ["register_workspace_commands"]
