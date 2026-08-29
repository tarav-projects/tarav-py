"""Named, read-only renderers for Tarav2 Diagram projections."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
from typing import Any

from .diagram import (
    BLOCK_ANNOTATION_TYPE,
    LINE_ANNOTATION_TYPE,
    LINE_GATE_ANNOTATION_TYPE,
    AnnotationAssessment,
    AssertionEngine,
    BlockAnnotation,
    ChatlasEvidence,
    Diagram,
    DiagramAnnotation,
    DiagramError,
    DiagramModel,
    Finding,
    LineAnnotation,
    LineGateAnnotation,
    TypedAnnotation,
    UserTouchedAnnotation,
)

JsonObject = dict[str, Any]
RenderHandler = Callable[
    ["DiagramRenderTarget", "DiagramRenderContext"],
    tuple[str, tuple[Finding, ...]],
]


class DiagramRenderError(DiagramError):
    pass


@dataclass(frozen=True, slots=True)
class DiagramRenderContext:
    evidence: ChatlasEvidence | None
    assertions: AssertionEngine


@dataclass(frozen=True, slots=True)
class DiagramRenderTarget:
    kind: str
    identity: str
    namespace_id: str
    subject: object

    def to_dict(self) -> JsonObject:
        key = {
            "annotation": "id",
            "line": "ship",
            "block": "ship",
            "model": "ship",
        }.get(self.kind, "identity")
        return {
            "kind": self.kind.capitalize(),
            key: self.identity,
            "namespace_id": self.namespace_id,
        }


@dataclass(frozen=True, slots=True)
class DiagramRenderer:
    name: str
    target_kind: str
    media_type: str
    description: str
    handler: RenderHandler

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "target_kind": self.target_kind,
            "media_type": self.media_type,
            "description": self.description,
        }

    def render(
        self,
        target: DiagramRenderTarget,
        *,
        evidence: ChatlasEvidence | None = None,
        assertion_engine: AssertionEngine | None = None,
    ) -> DiagramRenderResult:
        if target.kind != self.target_kind:
            raise DiagramRenderError(
                f"Renderer {self.name} accepts {self.target_kind} targets, "
                f"not {target.kind}"
            )
        context = DiagramRenderContext(
            evidence,
            assertion_engine or AssertionEngine(evidence=evidence),
        )
        content, findings = self.handler(target, context)
        return DiagramRenderResult(self, target, content, findings)


@dataclass(frozen=True, slots=True)
class DiagramRenderResult:
    renderer: DiagramRenderer
    target: DiagramRenderTarget
    content: str
    findings: tuple[Finding, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "status": "poi" if self.findings else "ok",
            "renderer": self.renderer.name,
            "media_type": self.renderer.media_type,
            "target": self.target.to_dict(),
            "content": self.content,
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class BlockProjection:
    ship: str
    annotations: tuple[DiagramAnnotation, ...]


def annotation_render_target(
    diagram: Diagram, annotation_id: str, *, namespace: str | None = None
) -> DiagramRenderTarget:
    annotation = diagram.annotation(annotation_id, namespace=namespace)
    return DiagramRenderTarget(
        "annotation", annotation.id, annotation.namespace.id, annotation
    )


def line_render_target(
    diagram: Diagram, line_ship: str, *, namespace: str | None = None
) -> DiagramRenderTarget:
    annotations = diagram.line(line_ship, namespace=namespace)
    if not annotations:
        raise DiagramRenderError(f"Diagram Line not found: {line_ship}")
    namespace_ids = {item.annotation.namespace.id for item in annotations}
    if len(namespace_ids) != 1:
        raise DiagramRenderError(
            f"Diagram Line does not resolve to one Namespace: {line_ship}"
        )
    return DiagramRenderTarget(
        "line", line_ship, next(iter(namespace_ids)), annotations
    )


def block_render_target(
    diagram: Diagram, block_ship: str, *, namespace: str | None = None
) -> DiagramRenderTarget:
    annotations = diagram.block_annotations(block_ship, namespace=namespace)
    namespace_ids = {item.namespace.id for item in annotations}
    if len(namespace_ids) != 1:
        raise DiagramRenderError(f"Diagram Block does not resolve: {block_ship}")
    namespace_id = next(iter(namespace_ids))
    return DiagramRenderTarget(
        "block",
        block_ship,
        namespace_id,
        BlockProjection(block_ship, annotations),
    )


def model_render_target(model: DiagramModel) -> DiagramRenderTarget:
    return DiagramRenderTarget("model", model.ship, model.namespace.id, model)


def renderer(name: str) -> DiagramRenderer:
    try:
        return _RENDERERS[name]
    except KeyError as exc:
        raise DiagramRenderError(f"Diagram Renderer not found: {name}") from exc


def renderers(*, target_kind: str | None = None) -> tuple[DiagramRenderer, ...]:
    values = tuple(_RENDERERS.values())
    if target_kind is None:
        return values
    return tuple(item for item in values if item.target_kind == target_kind)


def _annotation_payload(
    annotation: DiagramAnnotation, assessment: AnnotationAssessment
) -> JsonObject:
    return {
        "id": annotation.id,
        "namespace_id": annotation.namespace.id,
        **annotation.to_record(),
        "assertions": list(annotation.assertions()),
        "score_vector": dict(assessment.score_vector),
        "standing": assessment.standing,
    }


def _debug_annotation(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    annotation = target.subject
    if not isinstance(annotation, DiagramAnnotation):
        raise DiagramRenderError("Debug Annotation renderer received another target")
    assessment = context.assertions.assess(annotation)
    return (
        json.dumps(
            _annotation_payload(annotation, assessment), indent=2, ensure_ascii=False
        ),
        assessment.findings,
    )


def _debug_line(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    annotations = _typed_annotations(target)
    assessments = {
        item.id: context.assertions.assess(item) for item in annotations
    }
    return json.dumps(
        {
            "line_ship": target.identity,
            "annotations": [
                _annotation_payload(item.annotation, assessments[item.id])
                for item in annotations
            ],
        },
        indent=2,
        ensure_ascii=False,
    ), tuple(
        finding
        for assessment in assessments.values()
        for finding in assessment.findings
    )


def _kernel_line(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    return _render_line(target, with_support=False, context=context)


def _kernel_line_with_support(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    if context.evidence is None:
        raise DiagramRenderError(
            "Kernel.Writing.Line.WithSupport requires Chatlas evidence"
        )
    return _render_line(target, with_support=True, context=context)


def _render_line(
    target: DiagramRenderTarget,
    *,
    with_support: bool,
    context: DiagramRenderContext,
) -> tuple[str, tuple[Finding, ...]]:
    wordings = [
        item for item in _typed_annotations(target) if isinstance(item, LineAnnotation)
    ]
    if not wordings:
        raise DiagramRenderError(f"Diagram Line has no wording: {target.identity}")
    findings: list[Finding] = []
    ambiguous = len(wordings) > 1
    if ambiguous:
        findings.append(
            Finding(
                "line-rendering-selection-ambiguous",
                "target.line",
                "Line has several wording Annotations and no selected edition; all variants were rendered.",
            )
        )
    sections: list[str] = []
    any_reviewed = False
    typed_annotations = _typed_annotations(target)
    for wording in _sort_typed(wordings):
        annotation_assessment = context.assertions.assess(wording)
        assessments = annotation_assessment.gate_assessments
        for gate_annotation in typed_annotations:
            if (
                isinstance(gate_annotation, LineGateAnnotation)
                and gate_annotation.target_annotation_id == wording.id
            ):
                assessments = (
                    *assessments,
                    *context.assertions.assess(gate_annotation).gate_assessments,
                )
        wording_reviewed = any(item.standing == "Passed" for item in assessments)
        any_reviewed = any_reviewed or wording_reviewed
        if wording_reviewed:
            review_standing = "Reviewed"
        elif assessments and context.evidence is None:
            review_standing = "Review.Unassessable"
        elif assessments:
            review_standing = "Review.POI"
        else:
            review_standing = "Unreviewed"
        marker = _annotation_marker(
            wording.annotation,
            assessment=annotation_assessment,
            ambiguous=ambiguous,
            review_standing=review_standing,
        )
        sections.append(f"- {wording.text} {marker}")
        findings.extend(
            finding for assessment in assessments for finding in assessment.findings
        )
        if with_support and context.evidence is not None:
            detail, support_findings = _support_details(
                wording,
                target.identity,
                context.evidence,
                annotation_assessment,
            )
            sections.append(detail)
            findings.extend(support_findings)
    if not any_reviewed:
        findings.append(
            Finding(
                "line-unreviewed",
                f"line.{target.identity}",
                "Line ship has no Annotation with a passing Verbatim.Gate.",
            )
        )
    return "\n\n".join(sections), tuple(findings)


def _kernel_block(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    return _render_block(target, with_support=False, context=context)


def _kernel_block_with_support(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    if context.evidence is None:
        raise DiagramRenderError(
            "Kernel.Writing.Block.WithSupport requires Chatlas evidence"
        )
    return _render_block(target, with_support=True, context=context)


def _render_block(
    target: DiagramRenderTarget,
    *,
    with_support: bool,
    context: DiagramRenderContext,
    heading_level: int = 2,
) -> tuple[str, tuple[Finding, ...]]:
    projection = target.subject
    if not isinstance(projection, BlockProjection):
        raise DiagramRenderError("Block renderer received another target")
    typed = _specialize_known(projection.annotations)
    blocks = [item for item in typed if isinstance(item, BlockAnnotation)]
    findings: list[Finding] = []
    if len(blocks) == 1:
        label = blocks[0].label
    else:
        label = f"Block.{projection.ship[:8]}"
        findings.append(
            Finding(
                "block-label-selection-unresolved",
                "target.block",
                "Block does not have exactly one label Annotation.",
            )
        )
    sections = [f"{'#' * heading_level} {label}"]
    groups = _line_groups(typed)
    if not groups:
        findings.append(
            Finding(
                "block-has-no-lines",
                "target.block",
                "Block contains no Line wording Annotations.",
            )
        )
    rendered_lines: list[str] = []
    for line_ship, line_annotations in groups:
        line_target = DiagramRenderTarget(
            "line", line_ship, target.namespace_id, line_annotations
        )
        content, line_findings = _render_line(
            line_target, with_support=with_support, context=context
        )
        rendered_lines.append(content)
        findings.extend(line_findings)
    if rendered_lines:
        sections.append(("\n\n" if with_support else "\n").join(rendered_lines))
    return "\n\n".join(sections), tuple(findings)


def _kernel_model(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[Finding, ...]]:
    model = target.subject
    if not isinstance(model, DiagramModel):
        raise DiagramRenderError("Model renderer received another target")
    root = model.namespace.annotation(model.root_annotation_id)
    data = root.record.get("data")
    label = data.get("label") if isinstance(data, dict) else None
    title = label if isinstance(label, str) and label else f"Model.{model.ship[:8]}"
    annotations = model.annotations()
    block_ships = []
    for item in _sort_annotations(annotations):
        if item.type != BLOCK_ANNOTATION_TYPE:
            continue
        location = item.record.get("location")
        ship = location.get("block_ship") if isinstance(location, dict) else None
        if isinstance(ship, str) and ship not in block_ships:
            block_ships.append(ship)
    sections = [f"# {title}"]
    findings: list[Finding] = []
    for block_ship in block_ships:
        block_annotations = model.namespace.block_annotations(block_ship)
        block_target = DiagramRenderTarget(
            "block",
            block_ship,
            target.namespace_id,
            BlockProjection(block_ship, block_annotations),
        )
        content, block_findings = _render_block(
            block_target, with_support=False, context=context, heading_level=2
        )
        sections.append(content)
        findings.extend(block_findings)
    if not block_ships:
        findings.append(
            Finding(
                "model-has-no-blocks",
                "target.model",
                "Model contains no Block Annotations.",
            )
        )
    return "\n\n".join(sections), tuple(findings)


def _typed_annotations(target: DiagramRenderTarget) -> tuple[TypedAnnotation, ...]:
    values = target.subject
    if not isinstance(values, tuple) or not all(
        isinstance(item, TypedAnnotation) for item in values
    ):
        raise DiagramRenderError(f"Renderer received an invalid {target.kind} target")
    return values


def _specialize_known(
    annotations: Iterable[DiagramAnnotation],
) -> tuple[TypedAnnotation, ...]:
    typed: list[TypedAnnotation] = []
    for annotation in annotations:
        if annotation.type in (
            BLOCK_ANNOTATION_TYPE,
            LINE_ANNOTATION_TYPE,
            LINE_GATE_ANNOTATION_TYPE,
        ):
            typed.append(annotation.specialize())
    return tuple(typed)


def _line_groups(
    annotations: Iterable[TypedAnnotation],
) -> tuple[tuple[str, tuple[TypedAnnotation, ...]], ...]:
    groups: dict[str, list[TypedAnnotation]] = {}
    ordered = _sort_typed(annotations)
    for item in ordered:
        if isinstance(item, LineAnnotation):
            groups.setdefault(item.location.line_ship, []).append(item)
    for item in ordered:
        if isinstance(item, LineGateAnnotation):
            ship = item.location.line_ship
            if ship in groups:
                groups[ship].append(item)
    return tuple((ship, tuple(items)) for ship, items in groups.items())


def _sort_annotations(
    annotations: Iterable[DiagramAnnotation],
) -> tuple[DiagramAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (str(item.record.get("recorded_at", "")), item.id),
        )
    )


def _sort_typed(
    annotations: Iterable[TypedAnnotation],
) -> tuple[TypedAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (
                str(item.record.get("recorded_at", "")),
                item.id,
            ),
        )
    )


def _annotation_marker(
    annotation: DiagramAnnotation,
    *,
    assessment: AnnotationAssessment,
    ambiguous: bool = False,
    review_standing: str | None = None,
) -> str:
    parts = [assessment.standing]
    if review_standing:
        parts.append(review_standing)
    if assessment.score_vector:
        parts.append(
            "scores="
            + json.dumps(
                assessment.score_vector, ensure_ascii=False, separators=(",", ":")
            )
        )
    if ambiguous:
        parts.append(f"annotation:{annotation.id[:8]}")
    return f"〔{' · '.join(parts)}〕"


def _support_details(
    annotation: UserTouchedAnnotation,
    ship: str,
    evidence: ChatlasEvidence,
    assessment: AnnotationAssessment,
) -> tuple[str, tuple[Finding, ...]]:
    try:
        members = annotation.render_support(evidence)
    except (DiagramError, ValueError) as exc:
        finding = Finding(
            "support-render-unavailable",
            f"annotation.{annotation.id}.support",
            str(exc),
        )
        return (
            "<details>\n"
            f"<summary>Support unavailable · {annotation.id[:8]}</summary>\n\n"
            f"{exc}\n\n"
            "</details>",
            (finding,),
        )
    turn_count = sum(len(member["turns"]) for member in members)
    sections = [
        "<details>",
        (
            f"<summary>Support · {len(members)} User.Touch"
            f"{'es' if len(members) != 1 else ''} · {turn_count} turns</summary>"
        ),
        "",
        f"**Semantic ship:** `{ship}`  ",
        f"**Annotation:** `{annotation.id}`",
    ]
    for index, member in enumerate(members, start=1):
        if len(members) > 1:
            sections.extend(("", f"### Support.Member {index}"))
        for turn in member["turns"]:
            reference = turn["reference"]
            role = str(turn.get("side", "unknown")).capitalize()
            qualifier = "User.Touch.Root" if turn.get("root") else "neighborhood"
            sections.extend(
                (
                    "",
                    f"**{role} · {qualifier}**",
                    (
                        "`chatlas:"
                        f"{reference['session_identity']}/"
                        f"{reference['turn_address']}@{reference['turn_hash']}`"
                    ),
                    "",
                    _markdown_quote(str(turn.get("text", ""))),
                )
            )
    sections.extend(("", "### Assertions", ""))
    scores = assessment.score_vector
    for assertion in annotation.annotation.assertions():
        assertion_type = assertion.get("type")
        if not isinstance(assertion_type, str):
            continue
        score = scores.get(assertion_type)
        rendered_score = (
            "unscored"
            if assertion_type not in scores
            else json.dumps(score, ensure_ascii=False, separators=(",", ":"))
        )
        sections.append(f"- `{assertion_type}` — {rendered_score}")
    sections.extend(("", "</details>"))
    return "\n".join(sections), ()


def _markdown_quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


_RENDERERS = {
    item.name: item
    for item in (
        DiagramRenderer(
            "Kernel.Writing.Line",
            "line",
            "text/markdown",
            "Compact Kernel.Writing projection of one Line lineage.",
            _kernel_line,
        ),
        DiagramRenderer(
            "Kernel.Writing.Line.WithSupport",
            "line",
            "text/markdown",
            "Kernel.Writing Line with exact rooted Chatlas support.",
            _kernel_line_with_support,
        ),
        DiagramRenderer(
            "Kernel.Writing.Block",
            "block",
            "text/markdown",
            "Kernel.Writing projection of one Block and its Lines.",
            _kernel_block,
        ),
        DiagramRenderer(
            "Kernel.Writing.Block.WithSupport",
            "block",
            "text/markdown",
            "Kernel.Writing Block with exact rooted Chatlas support.",
            _kernel_block_with_support,
        ),
        DiagramRenderer(
            "Kernel.Writing.Model",
            "model",
            "text/markdown",
            "Kernel.Writing projection of one Model's Blocks and Lines.",
            _kernel_model,
        ),
        DiagramRenderer(
            "Diagram.Debug.Annotation",
            "annotation",
            "application/json",
            "Complete debug projection of one Annotation.",
            _debug_annotation,
        ),
        DiagramRenderer(
            "Diagram.Debug.Line",
            "line",
            "application/json",
            "Complete debug projection of one Line lineage.",
            _debug_line,
        ),
    )
}


__all__ = [
    "BlockProjection",
    "DiagramRenderError",
    "DiagramRenderResult",
    "DiagramRenderTarget",
    "DiagramRenderer",
    "annotation_render_target",
    "block_render_target",
    "line_render_target",
    "model_render_target",
    "renderer",
    "renderers",
]
