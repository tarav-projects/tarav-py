"""CLI adapter for Tarav.Archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError

from . import Archive, ArchiveError, RegisteredArtifact, default_archive_root


def _archive_root(value: str | None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    return default_archive_root()


def _artifact_payload(artifact: RegisteredArtifact) -> dict[str, object]:
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "name": artifact.name,
        "recorded_at": artifact.recorded_at,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _emit(
    args: argparse.Namespace, payload: dict[str, object], lines: tuple[str, ...]
) -> int:
    if args.json:
        _print_json(payload)
    else:
        for line in lines:
            print(line)
    return 0


def _cmd_archive_init(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.create(root)
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive init",
            "archive": str(archive.root),
        },
        (f"archive: {archive.root}",),
    )


def _cmd_artifact_register(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.create(root)
        artifact = archive.register_artifact(
            locator=args.locator,
            name=args.name,
            kind=args.kind,
        )
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive artifact register",
            "archive": str(archive.root),
            "artifact": _artifact_payload(artifact),
        },
        (
            f"artifact: {artifact.name or artifact.kind} {artifact.id}",
            f"archive: {archive.root}",
        ),
    )


def _cmd_artifact_show(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.open(root)
        dossier = archive.dossier(args.artifact)
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    artifact = dossier.artifact
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive artifact show",
            "archive": str(archive.root),
            "artifact": _artifact_payload(artifact),
            "records": dossier.records,
        },
        (
            f"artifact: {artifact.name or artifact.kind} {artifact.id}",
            f"kind: {artifact.kind}",
            f"records: {', '.join(dossier.records)}",
            f"archive: {archive.root}",
        ),
    )


def _cmd_artifact_locator_add(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.open(root)
        artifact = archive.resolve_artifact(args.artifact)
        created = archive.add_locator(args.artifact, locator=args.locator)
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive artifact locator add",
            "archive": str(archive.root),
            "artifact": _artifact_payload(artifact),
            "created": created,
        },
        (
            f"artifact: {artifact.name or artifact.kind} {artifact.id}",
            f"locator added: {'yes' if created else 'already present'}",
        ),
    )


def _cmd_descriptor_add(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.open(root)
        registration = archive.register_external_descriptor(
            args.artifact,
            args.descriptor,
            attribution=args.attribution,
        )
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive artifact descriptor add",
            "archive": str(archive.root),
            "artifact": _artifact_payload(registration.target),
            "descriptor": _artifact_payload(registration.descriptor),
            "attribution": registration.attribution,
            "recorded_at": registration.recorded_at,
            "created": registration.created,
        },
        (
            f"artifact: {registration.target.id}",
            f"external descriptor: {registration.descriptor.id}",
            f"registered: {'yes' if registration.created else 'already present'}",
        ),
    )


def _cmd_repository_register(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    location = Path(args.location).expanduser().resolve()
    try:
        archive = Archive.create(root)
        repository = archive.register_repository(
            location,
            name=args.name,
            branch=args.branch,
        )
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive repository register",
            "archive": str(archive.root),
            "location": str(location),
            "branch": args.branch,
            "artifact": _artifact_payload(repository),
        },
        (
            f"repository: {repository.name} {repository.id}",
            f"archive: {archive.root}",
            f"location: {location}",
        ),
    )


def _cmd_repository_materialize(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        archive = Archive.open(root)
        artifact = archive.materialize_git_artifact(
            args.repository,
            commit=args.commit,
            path=args.path,
        )
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav archive repository materialize",
            "archive": str(archive.root),
            "artifact": _artifact_payload(artifact),
        },
        (
            f"artifact: {artifact.kind} {artifact.id}",
            f"archive: {archive.root}",
        ),
    )


def _cmd_reference_repository(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        reference = Archive.open(root).reference_repository(args.locator)
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(reference)
    return 0


def _cmd_reference_git_file(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        reference = Archive.open(root).reference_git_file(
            args.repository,
            commit=args.commit,
            locator=args.locator,
        )
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(reference)
    return 0


def _cmd_reference_file(args: argparse.Namespace) -> int:
    root = _archive_root(args.archive)
    try:
        reference = Archive.create(root).reference_file(args.locator)
    except (ArchiveError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(reference)
    return 0


def _add_archive_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--archive",
        help="Archive root; defaults to ~/Documents/tarav/archive.",
    )


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )


def _add_common_output_options(parser: argparse.ArgumentParser) -> None:
    _add_archive_option(parser)
    _add_json_option(parser)


def register_archive_commands(subparsers: argparse._SubParsersAction) -> None:
    archive = subparsers.add_parser(
        "archive",
        help="Register Artifacts and retain flat Records about them.",
    )
    archive_commands = archive.add_subparsers(dest="archive_command", required=True)

    initialize = archive_commands.add_parser("init", help="Initialize an Archive root.")
    _add_common_output_options(initialize)
    initialize.set_defaults(handler=_cmd_archive_init)

    artifact = archive_commands.add_parser(
        "artifact",
        help="Register and inspect Archive.Artifacts.",
    )
    artifact_commands = artifact.add_subparsers(
        dest="archive_artifact_command",
        required=True,
    )

    artifact_register = artifact_commands.add_parser(
        "register",
        help="Register a root or repoless Artifact.",
    )
    artifact_register.add_argument("--locator", required=True, help="Path or URI hint.")
    artifact_register.add_argument("--name", help="Unique public Artifact name.")
    artifact_register.add_argument(
        "--kind", default="Artifact", help="Artifact kind claim."
    )
    _add_common_output_options(artifact_register)
    artifact_register.set_defaults(handler=_cmd_artifact_register)

    artifact_show = artifact_commands.add_parser(
        "show",
        help="Show an Artifact and all of its retained Records.",
    )
    artifact_show.add_argument(
        "--artifact",
        required=True,
        help="Artifact name, ID, or unambiguous ID prefix.",
    )
    _add_common_output_options(artifact_show)
    artifact_show.set_defaults(handler=_cmd_artifact_show)

    locator = artifact_commands.add_parser("locator", help="Manage Artifact locators.")
    locator_commands = locator.add_subparsers(
        dest="archive_artifact_locator_command",
        required=True,
    )
    locator_add = locator_commands.add_parser("add", help="Add a locator hint.")
    locator_add.add_argument("--artifact", required=True, help="Artifact selector.")
    locator_add.add_argument("--locator", required=True, help="Path or URI hint.")
    _add_common_output_options(locator_add)
    locator_add.set_defaults(handler=_cmd_artifact_locator_add)

    descriptor = artifact_commands.add_parser(
        "descriptor",
        help="Manage attributed External.Descriptor Records.",
    )
    descriptor_commands = descriptor.add_subparsers(
        dest="archive_artifact_descriptor_command",
        required=True,
    )
    descriptor_add = descriptor_commands.add_parser(
        "add",
        help="Register one Artifact as an External.Descriptor of another.",
    )
    descriptor_add.add_argument(
        "--artifact", required=True, help="Target Artifact selector."
    )
    descriptor_add.add_argument(
        "--descriptor",
        required=True,
        help="Descriptor Artifact selector.",
    )
    descriptor_add.add_argument(
        "--attribution",
        required=True,
        help="Caller or source responsible for the declaration.",
    )
    _add_common_output_options(descriptor_add)
    descriptor_add.set_defaults(handler=_cmd_descriptor_add)

    reference = archive_commands.add_parser(
        "reference",
        help="Produce portable flat JSON Archive.References.",
    )
    reference_commands = reference.add_subparsers(
        dest="archive_reference_command",
        required=True,
    )
    reference_repository = reference_commands.add_parser(
        "repository",
        help="Reference a registered Git Repository by a known locator.",
    )
    reference_repository.add_argument(
        "--locator",
        required=True,
        help="Consumer-supplied Repository path or locator.",
    )
    _add_archive_option(reference_repository)
    reference_repository.set_defaults(handler=_cmd_reference_repository)

    reference_git_file = reference_commands.add_parser(
        "git-file",
        help="Reference one exact file version in a registered Git Repository.",
    )
    reference_git_file.add_argument(
        "--repository",
        required=True,
        help="Repository name, ID, or unambiguous ID prefix.",
    )
    reference_git_file.add_argument(
        "--commit",
        required=True,
        help="Exact commit or revision containing the file version.",
    )
    reference_git_file.add_argument(
        "--locator",
        required=True,
        help="File path relative to the Repository.",
    )
    _add_archive_option(reference_git_file)
    reference_git_file.set_defaults(handler=_cmd_reference_git_file)

    reference_file = reference_commands.add_parser(
        "file",
        help="Reference one exact repoless local file version.",
    )
    reference_file.add_argument(
        "--locator",
        required=True,
        help="Consumer-supplied local file path.",
    )
    _add_archive_option(reference_file)
    reference_file.set_defaults(handler=_cmd_reference_file)

    repository = archive_commands.add_parser(
        "repository",
        help="Register Git Repository Artifacts and address their committed contents.",
    )
    repository_commands = repository.add_subparsers(
        dest="archive_repository_command",
        required=True,
    )
    repository_register = repository_commands.add_parser(
        "register",
        help="Register an external Git repository.",
    )
    repository_register.add_argument(
        "--location",
        required=True,
        help="Path inside the Git repository.",
    )
    repository_register.add_argument(
        "--name",
        required=True,
        help="Unique public Repository name.",
    )
    repository_register.add_argument(
        "--branch",
        default="main",
        help="Local branch sampled for the Repository Git Hint; defaults to main.",
    )
    _add_common_output_options(repository_register)
    repository_register.set_defaults(handler=_cmd_repository_register)

    materialize = repository_commands.add_parser(
        "materialize",
        help="Retain Records for one exact committed file or folder.",
    )
    materialize.add_argument("--repository", required=True, help="Repository selector.")
    materialize.add_argument("--commit", required=True, help="Git commit or revision.")
    materialize.add_argument(
        "--path", required=True, help="Committed relative subpath."
    )
    _add_common_output_options(materialize)
    materialize.set_defaults(handler=_cmd_repository_materialize)


__all__ = ["register_archive_commands"]
