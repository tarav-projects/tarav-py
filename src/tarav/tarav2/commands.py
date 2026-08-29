"""Umbrella CLI adapter for the isolated Tarav redesign namespace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.data_root import default_tarav_data_root
from tarav._core.persistence import atomic_write_json
from tarav._core.project import require_agentos_project
from tarav.chatlas.normal_model import provide_normal_model

from .archive import Archive, ArchiveError, RegisteredArtifact
from .diagram import (
    CaptureManifest,
    ChatlasEvidence,
    ChatlasTurnReference,
    DIAGRAM_ATTIC,
    DiagramConfiguration,
    DiagramError,
    DiagramModelError,
    DiagramNamespace,
    USER_TOUCHED_CHATLAS_INDEX,
)
from .diagram_rendering import (
    DiagramRenderError,
    annotation_render_target,
    block_render_target,
    line_render_target,
    model_render_target,
    renderer,
    renderers,
)


def _archive_root(value: str | None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    return default_tarav_data_root() / "archive"


def _diagram_configuration(
    value: str | None, *, create: bool = False
) -> DiagramConfiguration:
    path = Path(value).expanduser().resolve() if value is not None else None
    return DiagramConfiguration.load(path, create=create)


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
            "command": "tarav2 archive init",
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
            "command": "tarav2 archive artifact register",
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
            "command": "tarav2 archive artifact show",
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
            "command": "tarav2 archive artifact locator add",
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
            "command": "tarav2 archive artifact descriptor add",
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
            "command": "tarav2 archive repository register",
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
            "command": "tarav2 archive repository materialize",
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


def _diagram_evidence(args: argparse.Namespace) -> ChatlasEvidence:
    root = (
        Path(args.chatlas_root).expanduser().resolve()
        if args.chatlas_root is not None
        else None
    )
    return ChatlasEvidence(chatlas_root=root)


def _cmd_diagram_namespace_create(args: argparse.Namespace) -> int:
    try:
        if args.name == USER_TOUCHED_CHATLAS_INDEX:
            namespace = DiagramNamespace.create_user_touched_chatlas_index(
                Path(args.location)
            )
        elif args.name == DIAGRAM_ATTIC:
            namespace = DiagramNamespace.create_diagram_attic(Path(args.location))
        else:
            namespace = DiagramNamespace.create(Path(args.location), name=args.name)
        if args.mount or args.default:
            _diagram_configuration(args.diagram_config, create=True).mount(
                namespace, default=args.default
            )
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram namespace create",
            "namespace": {
                "id": namespace.id,
                "name": namespace.name,
                "location": str(namespace.root),
            },
        },
        (
            f"namespace: {namespace.name}",
            f"id: {namespace.id}",
            f"location: {namespace.root}",
        ),
    )


def _cmd_diagram_namespace_mount(args: argparse.Namespace) -> int:
    try:
        namespace = DiagramNamespace.open(Path(args.location))
        config = _diagram_configuration(args.diagram_config, create=True).mount(
            namespace, default=args.default
        )
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram namespace mount",
            "namespace_id": namespace.id,
            "diagram_config": str(config.path),
        },
        (f"mounted: {namespace.name}", f"config: {config.path}"),
    )


def _cmd_diagram_namespace_list(args: argparse.Namespace) -> int:
    try:
        config = _diagram_configuration(args.diagram_config)
        namespaces = config.diagram().namespaces
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = [
        {
            "id": item.id,
            "name": item.name,
            "location": str(item.root),
            "default": item.id == config.default_namespace_id,
        }
        for item in namespaces
    ]
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram namespace list",
            "namespaces": payload,
        },
        tuple(
            f"{('*' if item['default'] else '-')} {item['name']}  {item['id']}  {item['location']}"
            for item in payload
        ),
    )


def _cmd_diagram_project_set_main_model(args: argparse.Namespace) -> int:
    try:
        project = require_agentos_project(project=args.project)
        diagram = _diagram_configuration(args.diagram_config).diagram()
        model = diagram.set_project_main_model(project.root, args.model_ship)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram project set-main-model",
            "project": str(project.root),
            "main_model": model.ship,
            "namespace_id": model.namespace.id,
        },
        (
            f"project: {project.root}",
            f"main model: {model.ship}",
            f"namespace: {model.namespace.id}",
        ),
    )


def _read_model(args: argparse.Namespace):
    diagram = _diagram_configuration(args.diagram_config).diagram()
    if args.model_ship:
        return diagram.model(args.model_ship)
    project = require_agentos_project(project=args.project)
    return diagram.project_model(project.root)


def _model_payload(model) -> dict[str, object]:
    return {
        "ship": model.ship,
        "namespace_id": model.namespace.id,
        "namespace_name": model.namespace.name,
        "root_annotation_id": model.root_annotation_id,
        "annotations": [
            _annotation_payload(annotation) for annotation in model.annotations()
        ],
    }


def _cmd_diagram_model_show(args: argparse.Namespace) -> int:
    try:
        model = _read_model(args)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram model show",
            "model": _model_payload(model),
        },
        (
            f"model: {model.ship}",
            f"namespace: {model.namespace.name}",
            f"annotations: {len(model.annotations())}",
        ),
    )


def _cmd_diagram_model_list(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        models = diagram.models(namespace=args.namespace)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = [_model_payload(model) for model in models]
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram model list",
            "models": payload,
        },
        tuple(
            f"{model.ship}  {model.namespace.name}  {len(model.annotations())} annotations"
            for model in models
        ),
    )


def _cmd_diagram_model_create(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        model = diagram.namespace(args.namespace).create_model(label=args.label)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram model create",
            "model": _model_payload(model),
        },
        (
            f"model: {model.ship}",
            f"namespace: {model.namespace.name}",
        ),
    )


def _cmd_diagram_capture_context(args: argparse.Namespace) -> int:
    try:
        if args.turn_limit < 1:
            raise DiagramModelError("--turn-limit must be positive")
        model = _read_model(args)
        chatlas_root = (
            Path(args.chatlas_root).expanduser().resolve()
            if args.chatlas_root
            else None
        )
        normal_model = provide_normal_model(
            session_id=args.session_id,
            identity_hash=args.identity_hash,
            provider=args.provider,
            instance=args.instance,
            chatlas_root=chatlas_root,
            refresh=args.refresh,
        )
        session = normal_model.get("session")
        turns = normal_model.get("turns")
        if not isinstance(session, dict) or not isinstance(turns, list):
            raise DiagramError("Chatlas Normal Model has no valid session or turns")
        identity = session.get("identity_hash")
        if not isinstance(identity, str):
            raise DiagramError("Chatlas Normal Model has no session identity")
        evidence = ChatlasEvidence(model_loader=lambda _: normal_model)
        selected = turns if args.all_turns else turns[-args.turn_limit :]
        turn_payloads = []
        for turn in selected:
            if not isinstance(turn, dict):
                raise DiagramError("Chatlas Normal Model contains an invalid turn")
            reference = ChatlasTurnReference(
                identity,
                str(turn.get("turn_address")),
                str(turn.get("turn_hash")),
            )
            turn_payloads.append(
                {
                    "reference": reference.to_dict(),
                    "side": turn.get("side"),
                    "text": evidence.turn_text(reference),
                }
            )
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram capture context",
            "model": _model_payload(model),
            "chat": {
                "session": session,
                "turn_count": len(turns),
                "turns": turn_payloads,
            },
        },
        (
            f"model: {model.ship}",
            f"session: {session.get('session_id')}",
            f"turns: {len(turn_payloads)} of {len(turns)}",
        ),
    )


def _capture_model(args: argparse.Namespace):
    config = _diagram_configuration(args.diagram_config)
    diagram = config.diagram()
    if args.model_ship:
        return diagram, diagram.model(args.model_ship)
    project = require_agentos_project(project=args.project)
    return diagram, diagram.ensure_project_model(project.root)


def _cmd_diagram_capture_template(args: argparse.Namespace) -> int:
    path = Path(args.manifest).expanduser().resolve()
    if path.exists():
        raise CliError(f"Capture.Manifest already exists: {path}")
    try:
        _, model = _capture_model(args)
        manifest = CaptureManifest.template(model_ship=model.ship)
        atomic_write_json(path, manifest.to_dict(), ensure_ascii=False)
    except (DiagramError, DiagramModelError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram capture template",
            "manifest": str(path),
            "capture": manifest.to_dict(),
        },
        (f"manifest: {path}",),
    )


def _cmd_diagram_capture_check(args: argparse.Namespace) -> int:
    path = Path(args.manifest).expanduser().resolve()
    try:
        manifest = CaptureManifest.read(path)
        model = (
            _diagram_configuration(args.diagram_config)
            .diagram()
            .model(manifest.model_ship)
        )
        findings = manifest.check(model.namespace, evidence=_diagram_evidence(args))
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "status": "poi" if findings else "ok",
        "command": "tarav2 diagram capture check",
        "manifest": str(path),
        "findings": [finding.to_dict() for finding in findings],
    }
    return _emit(
        args,
        payload,
        (
            f"manifest: {path}",
            f"findings: {len(findings)}",
        ),
    )


def _cmd_diagram_capture_apply(args: argparse.Namespace) -> int:
    path = Path(args.manifest).expanduser().resolve()
    try:
        manifest = CaptureManifest.read(path)
        diagram = _diagram_configuration(args.diagram_config).diagram()
        receipt = diagram.apply(
            manifest,
            evidence=_diagram_evidence(args),
            commit=not args.no_commit,
        )
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "status": "poi" if receipt.findings else "ok",
        "command": "tarav2 diagram capture apply",
        "namespace_id": receipt.namespace_id,
        "manifest": str(path),
        "receipt": receipt.to_dict(),
    }
    return _emit(
        args,
        payload,
        (
            f"namespace: {receipt.namespace_id}",
            f"created: {len(receipt.created)}",
            f"existing: {len(receipt.existing)}",
            f"findings: {len(receipt.findings)}",
            f"committed: {'yes' if receipt.committed else 'no'}",
            f"commit: {receipt.commit or '-'}",
        ),
    )


def _annotation_payload(annotation, assessment=None) -> dict[str, object]:
    score_vector = (
        dict(assessment.score_vector)
        if assessment is not None
        else annotation.score_vector()
    )
    return {
        "id": annotation.id,
        **annotation.to_record(),
        "assertions": list(annotation.assertions()),
        "score_vector": score_vector,
        "standing": assessment.standing if assessment is not None else annotation.standing,
    }


def _cmd_diagram_annotation_show(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        annotation = diagram.annotation(args.annotation, namespace=args.namespace)
        assessment = diagram.assertion_engine(
            evidence=_diagram_evidence(args)
        ).assess(annotation)
        payload = {
            "status": "ok",
            "command": "tarav2 diagram annotation show",
            "namespace_id": annotation.namespace.id,
            "annotation": _annotation_payload(annotation, assessment),
        }
        if args.render_support:
            payload["rendered_support"] = annotation.specialize().render_support(
                _diagram_evidence(args)
            )
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        payload,
        (
            f"annotation: {annotation.id}",
            f"type: {annotation.type}",
            f"standing: {annotation.standing}",
        ),
    )


def _cmd_diagram_line_show(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        annotations = diagram.line(args.line_ship, namespace=args.namespace)
        assertions = diagram.assertion_engine(evidence=_diagram_evidence(args))
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "status": "ok",
        "command": "tarav2 diagram line show",
        "line_ship": args.line_ship,
        "annotations": [
            _annotation_payload(
                annotation.annotation, assertions.assess(annotation)
            )
            for annotation in annotations
        ],
    }
    return _emit(
        args,
        payload,
        (
            f"line: {args.line_ship}",
            f"annotations: {len(annotations)}",
        ),
    )


def _cmd_diagram_renderer_list(args: argparse.Namespace) -> int:
    values = renderers(target_kind=args.target)
    payload = {
        "status": "ok",
        "command": "tarav2 diagram renderer list",
        "renderers": [item.to_dict() for item in values],
    }
    return _emit(
        args,
        payload,
        tuple(f"{item.name}  {item.target_kind}  {item.media_type}" for item in values),
    )


def _cmd_diagram_renderer_show(args: argparse.Namespace) -> int:
    try:
        selected = renderer(args.renderer)
    except DiagramRenderError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav2 diagram renderer show",
            "renderer": selected.to_dict(),
        },
        (
            f"renderer: {selected.name}",
            f"target: {selected.target_kind}",
            f"media type: {selected.media_type}",
            f"description: {selected.description}",
        ),
    )


def _cmd_diagram_render(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        if args.annotation:
            target = annotation_render_target(
                diagram, args.annotation, namespace=args.namespace
            )
        elif args.line_ship:
            target = line_render_target(
                diagram, args.line_ship, namespace=args.namespace
            )
        elif args.block_ship:
            target = block_render_target(
                diagram, args.block_ship, namespace=args.namespace
            )
        elif args.model_ship:
            target = model_render_target(diagram.model(args.model_ship))
        else:
            project = require_agentos_project(project=args.project)
            target = model_render_target(diagram.project_model(project.root))
        result = renderer(args.renderer).render(
            target,
            evidence=_diagram_evidence(args),
        )
    except (DiagramError, DiagramModelError, DiagramRenderError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "tarav2 diagram render",
        **result.to_dict(),
    }
    if args.json:
        _print_json(payload)
    else:
        print(result.content)
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


def _add_diagram_config_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--diagram-config",
        help="Machine-local Diagram configuration; defaults to ~/.tarav/diagram.json.",
    )


def _add_chatlas_root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--chatlas-root",
        help="Chatlas root used to resolve producer and support Turn references.",
    )


def _add_diagram_model_selector(parser: argparse.ArgumentParser) -> None:
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--model-ship", help="Existing Model ship UUID.")
    selector.add_argument(
        "--project",
        nargs="?",
        const=".",
        help="Project whose configured main Model should be used.",
    )


def register_tarav2_commands(subparsers: argparse._SubParsersAction) -> None:
    tarav2 = subparsers.add_parser(
        "tarav2", help="Experimental Tarav redesign surfaces."
    )
    tarav2_commands = tarav2.add_subparsers(dest="tarav2_command", required=True)
    archive = tarav2_commands.add_parser(
        "archive",
        help="Register Artifacts and retain flat Records about them.",
    )
    archive_commands = archive.add_subparsers(
        dest="tarav2_archive_command", required=True
    )

    initialize = archive_commands.add_parser("init", help="Initialize an Archive root.")
    _add_common_output_options(initialize)
    initialize.set_defaults(handler=_cmd_archive_init)

    artifact = archive_commands.add_parser(
        "artifact",
        help="Register and inspect Archive.Artifacts.",
    )
    artifact_commands = artifact.add_subparsers(
        dest="tarav2_archive_artifact_command",
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
        dest="tarav2_archive_artifact_locator_command",
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
        dest="tarav2_archive_artifact_descriptor_command",
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
        dest="tarav2_archive_reference_command",
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
        dest="tarav2_archive_repository_command",
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

    diagram = tarav2_commands.add_parser(
        "diagram",
        help="Capture grounded semantic Annotations over Chatlas turns.",
    )
    diagram_commands = diagram.add_subparsers(
        dest="tarav2_diagram_command",
        required=True,
    )

    namespace = diagram_commands.add_parser(
        "namespace", help="Create, mount, and inspect Diagram Namespaces."
    )
    namespace_commands = namespace.add_subparsers(
        dest="tarav2_diagram_namespace_command", required=True
    )
    namespace_create = namespace_commands.add_parser(
        "create", help="Initialize one independent Namespace Git repository."
    )
    namespace_create.add_argument("--location", required=True)
    namespace_create.add_argument("--name", required=True)
    namespace_create.add_argument("--mount", action="store_true")
    namespace_create.add_argument("--default", action="store_true")
    _add_diagram_config_option(namespace_create)
    _add_json_option(namespace_create)
    namespace_create.set_defaults(handler=_cmd_diagram_namespace_create)
    namespace_mount = namespace_commands.add_parser(
        "mount", help="Add an existing Namespace to the machine load path."
    )
    namespace_mount.add_argument("--location", required=True)
    namespace_mount.add_argument("--default", action="store_true")
    _add_diagram_config_option(namespace_mount)
    _add_json_option(namespace_mount)
    namespace_mount.set_defaults(handler=_cmd_diagram_namespace_mount)
    namespace_list = namespace_commands.add_parser(
        "list", help="List mounted Namespaces in load order."
    )
    _add_diagram_config_option(namespace_list)
    _add_json_option(namespace_list)
    namespace_list.set_defaults(handler=_cmd_diagram_namespace_list)

    project = diagram_commands.add_parser(
        "project", help="Associate Projects with Diagram Models."
    )
    project_commands = project.add_subparsers(
        dest="tarav2_diagram_project_command", required=True
    )
    project_set_main_model = project_commands.add_parser(
        "set-main-model",
        help="Point a Project at an existing shared Model.",
    )
    project_set_main_model.add_argument(
        "--project",
        nargs="?",
        const=".",
        required=True,
        help="Project path; a bare option selects the current directory.",
    )
    project_set_main_model.add_argument(
        "--model-ship", required=True, help="Existing Model ship UUID."
    )
    _add_diagram_config_option(project_set_main_model)
    _add_json_option(project_set_main_model)
    project_set_main_model.set_defaults(handler=_cmd_diagram_project_set_main_model)

    model = diagram_commands.add_parser("model", help="Inspect Diagram Models.")
    model_commands = model.add_subparsers(
        dest="tarav2_diagram_model_command", required=True
    )
    model_show = model_commands.add_parser(
        "show", help="Show one Model projection and its Annotations."
    )
    _add_diagram_model_selector(model_show)
    _add_diagram_config_option(model_show)
    _add_json_option(model_show)
    model_show.set_defaults(handler=_cmd_diagram_model_show)
    model_list = model_commands.add_parser(
        "list", help="List Model roots across mounted Namespaces."
    )
    model_list.add_argument("--namespace", help="Namespace id or name.")
    _add_diagram_config_option(model_list)
    _add_json_option(model_list)
    model_list.set_defaults(handler=_cmd_diagram_model_list)
    model_create = model_commands.add_parser(
        "create", help="Create one Model root Annotation."
    )
    model_create.add_argument(
        "--namespace", help="Namespace id or name; defaults to the configured default."
    )
    model_create.add_argument("--label", help="Optional human-facing Model label.")
    _add_diagram_config_option(model_create)
    _add_json_option(model_create)
    model_create.set_defaults(handler=_cmd_diagram_model_create)

    capture = diagram_commands.add_parser(
        "capture",
        help="Develop, check, and apply Capture.Manifests.",
    )
    capture_commands = capture.add_subparsers(
        dest="tarav2_diagram_capture_command",
        required=True,
    )
    capture_context = capture_commands.add_parser(
        "context",
        help="Return one Model and manifest-ready Chatlas Turn references.",
    )
    _add_diagram_model_selector(capture_context)
    chat_selector = capture_context.add_mutually_exclusive_group(required=True)
    chat_selector.add_argument("--identity-hash")
    chat_selector.add_argument("--session-id")
    capture_context.add_argument("--provider")
    capture_context.add_argument("--instance")
    capture_context.add_argument("--refresh", action="store_true")
    capture_context.add_argument(
        "--turn-limit",
        type=int,
        default=30,
        help="Number of trailing turns to include; defaults to 30.",
    )
    capture_context.add_argument(
        "--all-turns", action="store_true", help="Include every Chatlas Turn."
    )
    _add_diagram_config_option(capture_context)
    _add_chatlas_root_option(capture_context)
    _add_json_option(capture_context)
    capture_context.set_defaults(handler=_cmd_diagram_capture_context)

    capture_template = capture_commands.add_parser(
        "template",
        help="Write one post-land Capture.Manifest template.",
    )
    capture_template.add_argument("--manifest", required=True, help="Output JSON path.")
    capture_template.add_argument("--model-ship", help="Existing Model ship UUID.")
    capture_template.add_argument(
        "--project",
        nargs="?",
        const=".",
        help="Project whose main Model should receive the capture.",
    )
    _add_diagram_config_option(capture_template)
    _add_json_option(capture_template)
    capture_template.set_defaults(handler=_cmd_diagram_capture_template)

    capture_check = capture_commands.add_parser(
        "check",
        help="Report mechanical Capture.Manifest POIs.",
    )
    capture_check.add_argument("--manifest", required=True, help="Capture JSON path.")
    _add_diagram_config_option(capture_check)
    _add_chatlas_root_option(capture_check)
    _add_json_option(capture_check)
    capture_check.set_defaults(handler=_cmd_diagram_capture_check)

    capture_apply = capture_commands.add_parser(
        "apply",
        help="Apply all structurally representable Annotations and report POIs.",
    )
    capture_apply.add_argument("--manifest", required=True, help="Capture JSON path.")
    capture_apply.add_argument(
        "--no-commit",
        action="store_true",
        help="Write Annotation records without creating a Namespace Git commit.",
    )
    _add_diagram_config_option(capture_apply)
    _add_chatlas_root_option(capture_apply)
    _add_json_option(capture_apply)
    capture_apply.set_defaults(handler=_cmd_diagram_capture_apply)

    annotation = diagram_commands.add_parser(
        "annotation",
        help="Inspect Diagram Annotations.",
    )
    annotation_commands = annotation.add_subparsers(
        dest="tarav2_diagram_annotation_command",
        required=True,
    )
    annotation_show = annotation_commands.add_parser(
        "show",
        help="Show one Annotation and optionally render its selected support.",
    )
    annotation_show.add_argument("--annotation", required=True, help="Annotation UUID.")
    annotation_show.add_argument(
        "--namespace", help="Namespace id or name; otherwise use load order."
    )
    annotation_show.add_argument(
        "--render-support",
        action="store_true",
        help="Resolve and render the selected Chatlas turns.",
    )
    _add_diagram_config_option(annotation_show)
    _add_chatlas_root_option(annotation_show)
    _add_json_option(annotation_show)
    annotation_show.set_defaults(handler=_cmd_diagram_annotation_show)

    line = diagram_commands.add_parser("line", help="Inspect one semantic Line ship.")
    line_commands = line.add_subparsers(
        dest="tarav2_diagram_line_command",
        required=True,
    )
    line_show = line_commands.add_parser(
        "show",
        help="Show every captured Annotation on one Line ship.",
    )
    line_show.add_argument("--line-ship", required=True, help="Line ship UUID.")
    line_show.add_argument("--namespace", help="Namespace id or name.")
    _add_diagram_config_option(line_show)
    _add_json_option(line_show)
    line_show.set_defaults(handler=_cmd_diagram_line_show)

    renderer_command = diagram_commands.add_parser(
        "renderer", help="Discover named Diagram renderers."
    )
    renderer_commands = renderer_command.add_subparsers(
        dest="tarav2_diagram_renderer_command", required=True
    )
    renderer_list = renderer_commands.add_parser(
        "list", help="List registered Diagram renderers."
    )
    renderer_list.add_argument(
        "--target",
        choices=("annotation", "line", "block", "model"),
        help="Limit renderers to one target kind.",
    )
    _add_json_option(renderer_list)
    renderer_list.set_defaults(handler=_cmd_diagram_renderer_list)
    renderer_show = renderer_commands.add_parser(
        "show", help="Show one named Diagram renderer."
    )
    renderer_show.add_argument(
        "--renderer", required=True, help="Registered Renderer name."
    )
    _add_json_option(renderer_show)
    renderer_show.set_defaults(handler=_cmd_diagram_renderer_show)

    render = diagram_commands.add_parser(
        "render", help="Render one Diagram target through a named Renderer."
    )
    render.add_argument("--renderer", required=True, help="Registered Renderer name.")
    target = render.add_mutually_exclusive_group(required=True)
    target.add_argument("--annotation", help="Annotation UUID.")
    target.add_argument("--line-ship", help="Line ship UUID.")
    target.add_argument("--block-ship", help="Block ship UUID.")
    target.add_argument("--model-ship", help="Model ship UUID.")
    target.add_argument(
        "--project",
        nargs="?",
        const=".",
        help="Project whose configured main Model should be rendered.",
    )
    render.add_argument("--namespace", help="Namespace id or name.")
    _add_diagram_config_option(render)
    _add_chatlas_root_option(render)
    _add_json_option(render)
    render.set_defaults(handler=_cmd_diagram_render)


__all__ = ["register_tarav2_commands"]
