"""Unsorted CLI composition for durable Diagram.Draft writing workspaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.project import require_agentos_project

from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.storage import DiagramConfiguration
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.unsorted.drafts import DiagramDraft, DiagramDraftRepository, read_draft_delta


def _configuration(args: argparse.Namespace) -> DiagramConfiguration:
    path = (
        Path(args.diagram_config).expanduser().resolve()
        if args.diagram_config is not None
        else None
    )
    return DiagramConfiguration.load(path)


def _repository(
    args: argparse.Namespace, *, create: bool = False
) -> DiagramDraftRepository:
    root = (
        Path(args.drafts_root).expanduser().resolve()
        if args.drafts_root is not None
        else None
    )
    return DiagramDraftRepository.open(root, create=create)


def _evidence(args: argparse.Namespace) -> ChatlasEvidence:
    root = (
        Path(args.chatlas_root).expanduser().resolve()
        if getattr(args, "chatlas_root", None) is not None
        else None
    )
    return ChatlasEvidence(chatlas_root=root)


def _emit(args: argparse.Namespace, payload: dict[str, object]) -> int:
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"status: {payload['status']}")
        draft = payload.get("draft")
        if isinstance(draft, dict):
            print(f"draft: {draft.get('id')}")
            print(f"draft status: {draft.get('status')}")
            if draft.get("path") is not None:
                print(f"path: {draft['path']}")
        drafts = payload.get("drafts")
        if isinstance(drafts, list):
            for item in drafts:
                if isinstance(item, dict):
                    print(f"{item.get('id')}  {item.get('status')}  {item.get('path')}")
        receipt = payload.get("receipt")
        if isinstance(receipt, dict) and receipt.get("commit") is not None:
            print(f"commit: {receipt['commit']}")
        findings = payload.get("findings")
        if isinstance(findings, list):
            print(f"findings: {len(findings)}")
    return 0


def _draft_summary(draft: DiagramDraft) -> dict[str, object]:
    return {
        "id": draft.id,
        "path": str(draft.path),
        "model_ship": draft.model_ship,
        "status": draft.status,
        "ship_count": len(draft.ship_drafts),
        "annotation_count": len(draft.annotations),
        "receipt": draft.receipt,
    }


def _cmd_create(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        if args.project is not None:
            project = require_agentos_project(project=args.project)
            model = diagram.project_model(project.root)
        else:
            model = diagram.model(args.model_ship)
        draft = _repository(args, create=True).create(
            model.ship, draft_id=args.draft_id
        )
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram draft create",
            "draft": _draft_summary(draft),
        },
    )


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        drafts = _repository(args).drafts()
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram draft list",
            "drafts": [_draft_summary(item) for item in drafts],
        },
    )


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        draft = _repository(args).draft(args.draft)
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram draft show",
            "draft": draft.records.to_record(),
            "path": str(draft.path),
        },
    )


def _cmd_update(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        draft = repository.draft(args.draft)
        ships, annotations = read_draft_delta(Path(args.input))
        updated = repository.reconcile(
            draft,
            ships=ships,
            annotations=annotations,
            remove_ships=args.remove_ship or (),
            remove_annotations=args.remove_annotation or (),
        )
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram draft update",
            "draft": _draft_summary(updated),
        },
    )


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        draft = _repository(args).draft(args.draft)
        findings = draft.check(_configuration(args).diagram(), evidence=_evidence(args))
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "poi" if findings else "ok",
            "command": "tarav diagram draft check",
            "draft": _draft_summary(draft),
            "findings": [item.to_dict() for item in findings],
        },
    )


def _cmd_apply(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        draft = repository.draft(args.draft)
        receipt = repository.apply(
            draft,
            _configuration(args).diagram(),
            evidence=_evidence(args),
            commit=not args.no_commit,
        )
        applied = repository.draft(draft.id)
    except (DiagramError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "poi" if receipt.findings else "ok",
            "command": "tarav diagram draft apply",
            "draft": _draft_summary(applied),
            "receipt": receipt.records.to_record(),
        },
    )


def _add_repository_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--drafts-root")
    parser.add_argument("--diagram-config")
    parser.add_argument("--json", action="store_true")


def _add_draft_selector(
    parser: argparse.ArgumentParser, *, required: bool = True
) -> None:
    parser.add_argument("--draft", required=required)
    parser.add_argument("--drafts-root")
    parser.add_argument("--json", action="store_true")


def register_draft_commands(subparsers: argparse._SubParsersAction) -> None:
    command = subparsers.add_parser(
        "draft", help="Create, reconcile, check, and apply Diagram.Drafts."
    )
    commands = command.add_subparsers(dest="diagram_draft_command", required=True)

    create = commands.add_parser("create", help="Create one durable Diagram.Draft.")
    target = create.add_mutually_exclusive_group(required=True)
    target.add_argument("--model-ship")
    target.add_argument("--project", nargs="?", const=".")
    create.add_argument("--draft-id")
    _add_repository_options(create)
    create.set_defaults(handler=_cmd_create)

    listing = commands.add_parser("list", help="List retained Diagram.Drafts.")
    listing.add_argument("--drafts-root")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=_cmd_list)

    show = commands.add_parser("show", help="Show one Diagram.Draft.")
    _add_draft_selector(show)
    show.set_defaults(handler=_cmd_show)

    update = commands.add_parser("update", help="Reconcile one Draft delta.")
    _add_draft_selector(update)
    update.add_argument("--input", required=True)
    update.add_argument("--remove-ship", action="append")
    update.add_argument("--remove-annotation", action="append")
    update.set_defaults(handler=_cmd_update)

    check = commands.add_parser("check", help="Check one Draft as a Model overlay.")
    _add_draft_selector(check)
    check.add_argument("--diagram-config")
    check.add_argument("--chatlas-root")
    check.set_defaults(handler=_cmd_check)

    apply = commands.add_parser("apply", help="Apply one settled Diagram.Draft.")
    _add_draft_selector(apply)
    apply.add_argument("--diagram-config")
    apply.add_argument("--chatlas-root")
    apply.add_argument("--no-commit", action="store_true")
    apply.set_defaults(handler=_cmd_apply)


__all__ = ["register_draft_commands"]
