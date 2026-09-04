"""CLI adapter for Tarav.Diagram."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav._core.project import require_agentos_project
from tarav.chatlas.normal_model import provide_normal_model

from . import (
    CaptureManifest,
    ChatlasEvidence,
    ChatlasTurnReference,
    DIAGRAM_ATTIC,
    DiagramConfiguration,
    DiagramBlock,
    DiagramError,
    DiagramLineShip,
    DiagramModelError,
    DiagramNamespace,
    LINE_EDITION_TYPE,
    USER_TOUCHED_CHATLAS_INDEX,
)
from .rendering import (
    DiagramRenderError,
    annotation_render_target,
    block_render_target,
    line_render_target,
    model_render_target,
    renderer,
    renderers,
)
from .view_commands import register_view_commands


def _diagram_configuration(
    value: str | None, *, create: bool = False
) -> DiagramConfiguration:
    path = Path(value).expanduser().resolve() if value is not None else None
    return DiagramConfiguration.load(path, create=create)


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


def _diagram_evidence(args: argparse.Namespace) -> ChatlasEvidence:
    chatlas_root = getattr(args, "chatlas_root", None)
    root = (
        Path(chatlas_root).expanduser().resolve() if chatlas_root is not None else None
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
            "command": "tarav diagram namespace create",
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
            "command": "tarav diagram namespace mount",
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
            "command": "tarav diagram namespace list",
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
            "command": "tarav diagram project set-main-model",
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


def _read_diagram_model(args: argparse.Namespace):
    diagram = _diagram_configuration(args.diagram_config).diagram()
    if args.model_ship:
        return diagram, diagram.model(args.model_ship)
    project = require_agentos_project(project=args.project)
    return diagram, diagram.project_model(project.root)


def _read_model(args: argparse.Namespace):
    return _read_diagram_model(args)[1]


def _model_payload(model, *, diagram=None) -> dict[str, object]:
    projection = model.project()
    object_types = model.namespace.object_types()
    object_types_payload = object_types.to_dict()
    if diagram is not None:
        object_types_payload["findings"] = [
            item.to_dict()
            for item in diagram.object_type_definition_findings(object_types)
        ]
    return {
        "ship": model.ship,
        "namespace_id": model.namespace.id,
        "namespace_name": model.namespace.name,
        "current_edition_id": model.current_edition_id,
        "object_types": object_types_payload,
        "projection": projection.to_dict(),
        "ships": [_ship_payload(ship) for ship in model.ships()],
        "annotations": [
            _annotation_payload(annotation) for annotation in model.annotations()
        ],
    }


def _cmd_diagram_model_show(args: argparse.Namespace) -> int:
    try:
        diagram, model = _read_diagram_model(args)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram model show",
            "model": _model_payload(model, diagram=diagram),
        },
        (
            f"model: {model.ship}",
            f"namespace: {model.namespace.name}",
            f"ships: {len(model.ships())}",
            f"annotations: {len(model.annotations())}",
        ),
    )


def _cmd_diagram_model_list(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        models = diagram.models(namespace=args.namespace)
    except (DiagramError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = [_model_payload(model, diagram=diagram) for model in models]
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram model list",
            "models": payload,
        },
        tuple(
            f"{model.ship}  {model.namespace.name}  {len(model.ships())} ships"
            for model in models
        ),
    )


def _object_annotations(
    item: DiagramBlock | DiagramLineShip,
) -> tuple[object, ...]:
    annotations = (
        (
            *item.annotations,
            *(annotation for line in item.lines for annotation in line.annotations),
        )
        if isinstance(item, DiagramBlock)
        else item.annotations
    )
    return tuple({annotation.id: annotation for annotation in annotations}.values())


def _object_payload(
    item: DiagramBlock | DiagramLineShip, *, namespace
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    annotations = _object_annotations(item)
    engine = namespace.assertion_engine(evidence=None)
    assessments = tuple(
        engine.assess(annotation) for annotation in annotations
    )
    assertion_scores = tuple(
        assessment.score_vector.get(assertion_type)
        for assessment in assessments
        for assertion_type in assessment.assertion_types
    )
    lines = item.lines if isinstance(item, DiagramBlock) else (item,)
    reviews = tuple(
        namespace.line_review(line.ship, evidence=None) for line in lines
    )
    findings = (
        *item.findings,
        *(
            tuple(finding for line in item.lines for finding in line.findings)
            if isinstance(item, DiagramBlock)
            else ()
        ),
        *(
            finding
            for annotation in annotations
            for finding in namespace.findings(
                annotation.annotation,
                path=f"annotation.{annotation.id}",
                evidence=None,
            )
        ),
        *(finding for review in reviews for finding in review.findings),
    )
    unique_findings = tuple(
        {
            (finding.code, finding.path, finding.message): finding
            for finding in findings
        }.values()
    )
    current_edition = item.current_edition
    payload: dict[str, object] = {
        "kind": "block" if isinstance(item, DiagramBlock) else "line",
        "ship": item.ship,
        "object_type": item.object_type,
        "current_edition_id": (
            current_edition.id
            if isinstance(item, DiagramBlock) and current_edition is not None
            else (
                current_edition.annotation.id if current_edition is not None else None
            )
        ),
        "standing": {
            "assertions": len(assertion_scores),
            "asserted": sum(score is not None for score in assertion_scores),
            "unasserted": sum(score is None for score in assertion_scores),
            "reviewed_lines": sum(
                review.standing == "Reviewed" for review in reviews
            ),
            "unreviewed_lines": sum(
                review.standing != "Reviewed" for review in reviews
            ),
            "findings": len(unique_findings),
        },
    }
    if isinstance(item, DiagramBlock):
        payload.update(
            {
                "labels": list(item.labels),
                "current_label": item.current_label,
                "line_count": len(item.lines),
            }
        )
    else:
        payload["block_ship"] = item.block_ship
    return payload, tuple(finding.to_dict() for finding in unique_findings)


def _cmd_diagram_object_list(args: argparse.Namespace) -> int:
    try:
        _diagram, model = _read_diagram_model(args)
        projection = model.project()
        objects = projection.objects(
            kind=args.kind,
            object_type=args.object_type,
            label=args.label,
        )
        results = tuple(
            _object_payload(item, namespace=model.namespace) for item in objects
        )
        object_payloads = tuple(payload for payload, _findings in results)
        findings = tuple(
            finding
            for _payload, object_findings in results
            for finding in object_findings
        )
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "poi" if findings else "ok",
            "command": "tarav diagram object list",
            "model": {
                "ship": model.ship,
                "namespace_id": model.namespace.id,
                "current_edition_id": model.current_edition_id,
            },
            "filters": {
                "kind": args.kind,
                "object_type": args.object_type,
                "label": args.label,
            },
            "objects": list(object_payloads),
            "findings": list(findings),
        },
        tuple(
            "  ".join(
                (
                    str(payload["kind"]),
                    str(payload["object_type"] or "-"),
                    str(payload.get("current_label") or "-"),
                    str(payload["ship"]),
                    (
                        f"{payload['standing']['asserted']}/"
                        f"{payload['standing']['assertions']} asserted"
                    ),
                )
            )
            for payload in object_payloads
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
            "command": "tarav diagram model create",
            "model": _model_payload(model, diagram=diagram),
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
        diagram, model = _read_diagram_model(args)
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
            "command": "tarav diagram capture context",
            "model": _model_payload(model, diagram=diagram),
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
            "command": "tarav diagram capture template",
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
        "command": "tarav diagram capture check",
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
        "command": "tarav diagram capture apply",
        "namespace_id": receipt.namespace_id,
        "manifest": str(path),
        "receipt": receipt.to_dict(),
    }
    return _emit(
        args,
        payload,
        (
            f"namespace: {receipt.namespace_id}",
            f"created ships: {len(receipt.created_ships)}",
            f"updated ships: {len(receipt.updated_ships)}",
            f"created editions: {len(receipt.created_editions)}",
            f"existing editions: {len(receipt.existing_editions)}",
            f"created annotations: {len(receipt.created_annotations)}",
            f"existing annotations: {len(receipt.existing_annotations)}",
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
        "standing": assessment.standing
        if assessment is not None
        else annotation.standing,
    }


def _ship_payload(ship) -> dict[str, object]:
    return {
        "id": ship.id,
        **ship.to_record(),
    }


def _cmd_diagram_ship_show(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        ship = diagram.ship(args.ship, namespace=args.namespace)
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram ship show",
            "namespace_id": ship.namespace.id,
            "ship": _ship_payload(ship),
        },
        (
            f"ship: {ship.id}",
            f"type: {ship.type}",
            f"editions: {len(ship.record.get('editions', []))}",
        ),
    )


def _cmd_diagram_annotation_show(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        annotation = diagram.annotation(args.annotation, namespace=args.namespace)
        assessment = diagram.assertion_engine(evidence=_diagram_evidence(args)).assess(
            annotation
        )
        payload = {
            "status": "ok",
            "command": "tarav diagram annotation show",
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


def _cmd_diagram_annotation_list(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        spaces = (
            (diagram.namespace(args.namespace),)
            if args.namespace
            else diagram.namespaces
        )
        annotations = tuple(
            annotation for space in spaces for annotation in space.annotations()
        )
        if args.argument:
            matching = {
                (annotation.namespace.id, annotation.id)
                for annotation in diagram.annotations_for_argument(
                    args.argument, namespace=args.namespace
                )
            }
            annotations = tuple(
                annotation
                for annotation in annotations
                if (annotation.namespace.id, annotation.id) in matching
            )
        if args.model_ship:
            selected = []
            for annotation in annotations:
                try:
                    location = annotation.specialize().model_location()
                except DiagramError:
                    location = None
                if location is not None and location[0] == args.model_ship:
                    selected.append(annotation)
            annotations = tuple(selected)
        if args.annotation_type:
            annotations = tuple(
                annotation
                for annotation in annotations
                if annotation.type == args.annotation_type
            )
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "command": "tarav diagram annotation list",
            "annotations": [
                {
                    "namespace_id": annotation.namespace.id,
                    **_annotation_payload(annotation),
                }
                for annotation in annotations
            ],
        },
        tuple(
            f"{annotation.id}  {annotation.type}  {annotation.namespace.name}"
            for annotation in annotations
        ),
    )


def _cmd_diagram_line_show(args: argparse.Namespace) -> int:
    try:
        diagram = _diagram_configuration(args.diagram_config).diagram()
        annotations = diagram.line(args.line_ship, namespace=args.namespace)
        assertions = diagram.assertion_engine(evidence=_diagram_evidence(args))
    except (DiagramError, DiagramModelError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    editions = tuple(item for item in annotations if item.type == LINE_EDITION_TYPE)
    claims = tuple(item for item in annotations if item.type != LINE_EDITION_TYPE)
    payload = {
        "status": "ok",
        "command": "tarav diagram line show",
        "line_ship": args.line_ship,
        "editions": [
            _annotation_payload(edition.annotation, assertions.assess(edition))
            for edition in editions
        ],
        "annotations": [
            _annotation_payload(annotation.annotation, assertions.assess(annotation))
            for annotation in claims
        ],
    }
    return _emit(
        args,
        payload,
        (
            f"line: {args.line_ship}",
            f"editions: {len(editions)}",
            f"annotations: {len(claims)}",
        ),
    )


def _cmd_diagram_renderer_list(args: argparse.Namespace) -> int:
    values = renderers(target_kind=args.target)
    payload = {
        "status": "ok",
        "command": "tarav diagram renderer list",
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
            "command": "tarav diagram renderer show",
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
        "command": "tarav diagram render",
        **result.to_dict(),
    }
    if args.json:
        _print_json(payload)
    else:
        print(result.content)
    return 0


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )


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


def register_diagram_commands(subparsers: argparse._SubParsersAction) -> None:
    diagram = subparsers.add_parser(
        "diagram",
        help="Maintain typed semantic Ships and grounded Annotations.",
    )
    diagram_commands = diagram.add_subparsers(
        dest="diagram_command",
        required=True,
    )

    namespace = diagram_commands.add_parser(
        "namespace", help="Create, mount, and inspect Diagram Namespaces."
    )
    namespace_commands = namespace.add_subparsers(
        dest="diagram_namespace_command", required=True
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
        dest="diagram_project_command", required=True
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
    model_commands = model.add_subparsers(dest="diagram_model_command", required=True)
    model_show = model_commands.add_parser(
        "show", help="Show one Model, its Ships, Annotations, and projection."
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
    model_create = model_commands.add_parser("create", help="Create one Model Ship.")
    model_create.add_argument(
        "--namespace", help="Namespace id or name; defaults to the configured default."
    )
    model_create.add_argument("--label", help="Optional human-facing Model label.")
    _add_diagram_config_option(model_create)
    _add_json_option(model_create)
    model_create.set_defaults(handler=_cmd_diagram_model_create)

    object_command = diagram_commands.add_parser(
        "object", help="Query projected Diagram Blocks and Lines."
    )
    object_commands = object_command.add_subparsers(
        dest="diagram_object_command", required=True
    )
    object_list = object_commands.add_parser(
        "list", help="List projected objects through exact composable filters."
    )
    _add_diagram_model_selector(object_list)
    object_list.add_argument("--kind", choices=("block", "line"))
    object_list.add_argument(
        "--object-type", help="Only objects with this exact current Object.Type."
    )
    object_list.add_argument(
        "--label", help="Only Blocks retaining this exact label in their history."
    )
    _add_diagram_config_option(object_list)
    _add_json_option(object_list)
    object_list.set_defaults(handler=_cmd_diagram_object_list)

    capture = diagram_commands.add_parser(
        "capture",
        help="Develop, check, and apply Capture.Manifests.",
    )
    capture_commands = capture.add_subparsers(
        dest="diagram_capture_command",
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
        help="Apply structurally representable Ships and Annotations; report POIs.",
    )
    capture_apply.add_argument("--manifest", required=True, help="Capture JSON path.")
    capture_apply.add_argument(
        "--no-commit",
        action="store_true",
        help="Write records without creating a Namespace Git commit.",
    )
    _add_diagram_config_option(capture_apply)
    _add_chatlas_root_option(capture_apply)
    _add_json_option(capture_apply)
    capture_apply.set_defaults(handler=_cmd_diagram_capture_apply)

    ship = diagram_commands.add_parser("ship", help="Inspect semantic Ships.")
    ship_commands = ship.add_subparsers(
        dest="diagram_ship_command",
        required=True,
    )
    ship_show = ship_commands.add_parser(
        "show", help="Show one typed Ship and its ordered editions."
    )
    ship_show.add_argument("--ship", required=True, help="Ship UUID.")
    ship_show.add_argument(
        "--namespace", help="Namespace id or name; otherwise use load order."
    )
    _add_diagram_config_option(ship_show)
    _add_json_option(ship_show)
    ship_show.set_defaults(handler=_cmd_diagram_ship_show)

    annotation = diagram_commands.add_parser(
        "annotation",
        help="Inspect Diagram Annotations.",
    )
    annotation_commands = annotation.add_subparsers(
        dest="diagram_annotation_command",
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
    annotation_list = annotation_commands.add_parser(
        "list",
        help="List Annotations, optionally selecting an argument or owning Model.",
    )
    annotation_list.add_argument(
        "--argument", help="Only Line.Annotations naming this Diagram UUID."
    )
    annotation_list.add_argument(
        "--model-ship", help="Only Annotations located in this Model."
    )
    annotation_list.add_argument(
        "--type", dest="annotation_type", help="Only this exact Annotation.Type."
    )
    annotation_list.add_argument(
        "--namespace", help="Namespace id or name; otherwise use load order."
    )
    _add_diagram_config_option(annotation_list)
    _add_json_option(annotation_list)
    annotation_list.set_defaults(handler=_cmd_diagram_annotation_list)

    line = diagram_commands.add_parser("line", help="Inspect one semantic Line ship.")
    line_commands = line.add_subparsers(
        dest="diagram_line_command",
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
        dest="diagram_renderer_command", required=True
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

    register_view_commands(diagram_commands)


__all__ = ["register_diagram_commands"]
