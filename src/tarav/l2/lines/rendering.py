"""Named, read-only renderers for Lines projections and their assessments."""

from __future__ import annotations

# tarav.breadcrumb 8e914a507439

import tarav.l2.unsorted.pois as diagram_pois

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
from typing import Any

from tarav.l2.unsorted.assessment import AnnotationAssessment, AssertionEngine
from tarav.l2.lines.records import BlockEditionRecord, LineAnnotationRecord, LineEditionRecord, LineGateAnnotation
from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.storage import Diagram
from tarav.l2.unsorted.records import DiagramAnnotation, TypedAnnotation, UserTouchedAnnotation
from tarav.l2.lines.block import DiagramBlock, IssueBlock
from tarav.l2.lines.collection import DiagramCollection, ImplReqCollection
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.lines.line import DiagramLineShip
from tarav.l2.models import Model
from tarav.l2.unsorted.pois import DiagramPOI

JsonObject = dict[str, Any]
RenderHandler = Callable[
    ["DiagramRenderTarget", "DiagramRenderContext"],
    tuple[str, tuple[DiagramPOI, ...]],
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
            "collection": "ship",
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
        content, pois = self.handler(target, context)
        return DiagramRenderResult(self, target, content, pois)


@dataclass(frozen=True, slots=True)
class DiagramRenderResult:
    renderer: DiagramRenderer
    target: DiagramRenderTarget
    content: str
    pois: tuple[DiagramPOI, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "status": "poi" if self.pois else "ok",
            "renderer": self.renderer.name,
            "media_type": self.renderer.media_type,
            "target": self.target.to_dict(),
            "content": self.content,
            "pois": [item.records.to_record() for item in self.pois],
        }


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
    line = diagram.projected_line(line_ship, namespace=namespace)
    annotations = line.annotations
    namespace_ids = {item.annotation.namespace.id for item in annotations}
    return DiagramRenderTarget("line", line_ship, next(iter(namespace_ids)), line)


def block_render_target(
    diagram: Diagram, block_ship: str, *, namespace: str | None = None
) -> DiagramRenderTarget:
    block = diagram.projected_block(block_ship, namespace=namespace)
    namespace_ids = {item.annotation.namespace.id for item in block.annotations}
    if not namespace_ids:
        namespace_ids = {
            item.annotation.namespace.id
            for line in block.lines
            for item in line.annotations
        }
    return DiagramRenderTarget(
        "block",
        block_ship,
        next(iter(namespace_ids)),
        block,
    )


def model_render_target(model: Model) -> DiagramRenderTarget:
    return DiagramRenderTarget("model", model.ship, model.namespace.id, model)


def collection_render_target(
    diagram: Diagram, collection_ship: str, *, namespace: str | None = None
) -> DiagramRenderTarget:
    collection = diagram.projected_collection(collection_ship, namespace=namespace)
    current = collection.current_edition
    if current is None:
        raise DiagramRenderError("Diagram Collection has no current edition")
    return DiagramRenderTarget(
        "collection",
        collection.ship,
        current.annotation.namespace.id,
        collection,
    )


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
) -> tuple[str, tuple[DiagramPOI, ...]]:
    annotation = target.subject
    if not isinstance(annotation, DiagramAnnotation):
        raise DiagramRenderError("Debug Annotation renderer received another target")
    assessment = context.assertions.assess(annotation)
    return (
        json.dumps(
            _annotation_payload(annotation, assessment), indent=2, ensure_ascii=False
        ),
        assessment.pois,
    )


def _kernel_line_annotation(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    annotation = target.subject
    if not isinstance(annotation, DiagramAnnotation):
        raise DiagramRenderError("Line.Annotation renderer received another target")
    typed = annotation.specialize()
    if not isinstance(typed, LineAnnotationRecord):
        raise DiagramRenderError(
            f"Annotation is not a Line.Annotation: {annotation.type}"
        )
    assessment = context.assertions.assess(typed)
    gate_assessments = assessment.gate_assessments
    if any(item.standing == "Passed" for item in gate_assessments):
        review_standing = "Reviewed"
    elif gate_assessments and context.evidence is None:
        review_standing = "Review.Unassessable"
    elif gate_assessments:
        review_standing = "Review.POI"
    else:
        review_standing = None
    marker = _annotation_marker(
        annotation,
        assessment=assessment,
        review_standing=review_standing,
    )
    sections = [
        f"- {typed.text} {marker}",
        "",
        f"**Line.Annotation:** `{annotation.id}`  ",
        f"**Edition:** `{typed.current_edition_id}`",
        "",
        "**Arguments:**",
        *(f"- `{item.namespace_id}:{item.kind}:{item.id}`" for item in typed.arguments),
    ]
    return "\n".join(sections), assessment.pois


def _debug_line(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    annotations = _typed_annotations(target)
    assessments = {item.id: context.assertions.assess(item) for item in annotations}
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
        poi
        for assessment in assessments.values()
        for poi in assessment.pois
    )


def _kernel_line(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    return _render_line(target, with_support=False, context=context)


def _kernel_line_with_support(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
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
) -> tuple[str, tuple[DiagramPOI, ...]]:
    line = target.subject
    if not isinstance(line, DiagramLineShip):
        raise DiagramRenderError("Line renderer received another target")
    wordings = [
        item for item in line.annotations if isinstance(item, LineEditionRecord)
    ]
    if not wordings:
        raise DiagramRenderError(f"Diagram Line has no wording: {target.identity}")
    pois: list[DiagramPOI] = list(line.pois)
    current_wording = _sort_typed(wordings)[-1]
    sections: list[str] = []
    any_reviewed = False
    typed_annotations = line.annotations
    for wording in (current_wording,):
        annotation_assessment = context.assertions.assess(wording)
        assessments = annotation_assessment.gate_assessments
        for gate_annotation in typed_annotations:
            if (
                isinstance(gate_annotation, LineGateAnnotation)
                and gate_annotation.target_edition_id == wording.id
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
            ambiguous=False,
            review_standing=review_standing,
        )
        line_type = next(
            (
                edition.object_type
                for edition in line.editions
                if edition.annotation.id == wording.id
            ),
            None,
        )
        prefix = (
            f"[{line_type.short_code}] " if line_type and line_type.short_code else ""
        )
        sections.append(f"- {prefix}{wording.text} {marker}")
        pois.extend(
            poi for assessment in assessments for poi in assessment.pois
        )
        if with_support and context.evidence is not None:
            detail, support_pois = _support_details(
                wording,
                target.identity,
                context.evidence,
                annotation_assessment,
            )
            sections.append(detail)
            pois.extend(support_pois)
    if not any_reviewed:
        pois.append(
            diagram_pois.LineUnreviewed(path=f'line.{target.identity}', message='Line ship has no Annotation with a passing Verbatim.Gate.')
        )
    return "\n\n".join(sections), _dedupe_pois(pois)


def _kernel_block(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    return _render_block(target, with_support=False, context=context)


def _kernel_block_with_support(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
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
) -> tuple[str, tuple[DiagramPOI, ...]]:
    projection = target.subject
    if not isinstance(projection, DiagramBlock):
        raise DiagramRenderError("Block renderer received another target")
    blocks = [
        item for item in projection.annotations if isinstance(item, BlockEditionRecord)
    ]
    pois: list[DiagramPOI] = list(projection.pois)
    if blocks:
        label = _sort_typed(blocks)[-1].label
    else:
        label = f"Block.{projection.ship[:8]}"
        pois.append(
            diagram_pois.BlockLabelSelectionUnresolved(path='target.block', message='Block has no label edition.')
        )
    sections = [f"{'#' * heading_level} {label}"]
    if isinstance(projection, IssueBlock):
        issue = projection.assess(context.assertions)
        sections.append(f"**Issue.State:** `{issue.state}`")
        pois.extend(issue.pois)
    if not projection.lines:
        pois.append(
            diagram_pois.BlockHasNoLines(path='target.block', message='Block contains no Line editions.')
        )
    rendered_lines: list[str] = []
    for line in projection.lines:
        line_target = DiagramRenderTarget("line", line.ship, target.namespace_id, line)
        content, line_pois = _render_line(
            line_target, with_support=with_support, context=context
        )
        rendered_lines.append(content)
        pois.extend(line_pois)
    if rendered_lines:
        sections.append(("\n\n" if with_support else "\n").join(rendered_lines))
    return "\n\n".join(sections), _dedupe_pois(pois)


def _kernel_model(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    model = target.subject
    if not isinstance(model, Model):
        raise DiagramRenderError("Model renderer received another target")
    root = model.namespace.edition(model.current_edition_id)
    data = root.record.get("data")
    label = data.get("label") if isinstance(data, dict) else None
    title = label if isinstance(label, str) and label else f"Model.{model.ship[:8]}"
    projection = model.project()
    sections = [f"# {title}"]
    pois: list[DiagramPOI] = list(projection.pois)
    for block in projection.blocks:
        block_target = DiagramRenderTarget(
            "block",
            block.ship,
            target.namespace_id,
            block,
        )
        content, block_pois = _render_block(
            block_target, with_support=False, context=context, heading_level=2
        )
        sections.append(content)
        pois.extend(block_pois)
    if projection.collections:
        sections.extend(
            (
                "## Collections",
                *(_collection_summary(item) for item in projection.collections),
            )
        )
    if not projection.blocks:
        pois.append(
            diagram_pois.ModelHasNoBlocks(path='target.model', message='Model contains no Block Ships.')
        )
    return "\n\n".join(sections), _dedupe_pois(pois)


def _collection_summary(collection: DiagramCollection) -> str:
    label = collection.current_label or f"Collection.{collection.ship[:8]}"
    state = (
        f"; state: {collection.state}"
        if isinstance(collection, ImplReqCollection)
        else ""
    )
    return (
        f"- **{label}** — `{collection.object_type}`; "
        f"ship: `{collection.ship}`; hosted editions: "
        f"{len(collection.hosted_editions)}{state}"
    )


def _kernel_collection(
    target: DiagramRenderTarget, context: DiagramRenderContext
) -> tuple[str, tuple[DiagramPOI, ...]]:
    collection = target.subject
    if not isinstance(collection, DiagramCollection):
        raise DiagramRenderError("Collection renderer received another target")
    title = collection.current_label or f"Collection.{collection.ship[:8]}"
    sections = [
        f"# {title}",
        f"**Collection:** `{collection.ship}`  ",
        f"**Type:** `{collection.object_type}`",
    ]
    if isinstance(collection, ImplReqCollection):
        sections.append(f"**State:** `{collection.state}`")
    if collection.host is not None:
        sections.append(f"**Host:** `{collection.host.kind}:{collection.host.id}`")
    if collection.hosted_editions:
        sections.extend(
            (
                "",
                "## Hosted editions",
                *(
                    f"- `{item.kind}:{item.ship}@{item.edition}`"
                    for item in collection.hosted_editions
                ),
            )
        )
    if collection.references:
        sections.extend(
            (
                "",
                "## References",
                *(
                    f"- `{item.namespace_id}:{item.kind}:{item.id}`"
                    for item in collection.references
                ),
            )
        )
    return "\n".join(sections), collection.pois


def _typed_annotations(target: DiagramRenderTarget) -> tuple[TypedAnnotation, ...]:
    values = target.subject
    if isinstance(values, DiagramLineShip):
        return values.annotations
    if not isinstance(values, tuple) or not all(
        isinstance(item, TypedAnnotation) for item in values
    ):
        raise DiagramRenderError(f"Renderer received an invalid {target.kind} target")
    return values


def _sort_typed(
    annotations: Iterable[TypedAnnotation],
) -> tuple[TypedAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (
                str(item.records.to_record().get("recorded_at", "")),
                item.id,
            ),
        )
    )


def _dedupe_pois(pois: Iterable[DiagramPOI]) -> tuple[DiagramPOI, ...]:
    return tuple(
        {item.identity: item for item in pois}.values()
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
) -> tuple[str, tuple[DiagramPOI, ...]]:
    try:
        members = annotation.render_support(evidence)
    except (DiagramError, ValueError) as exc:
        poi = diagram_pois.SupportRenderUnavailable(path=f'annotation.{annotation.id}.support', message=str(exc), evidence={"error": str(exc)})
        return (
            "<details>\n"
            f"<summary>Support unavailable · {annotation.id[:8]}</summary>\n\n"
            f"{exc}\n\n"
            "</details>",
            (poi,),
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
            "Kernel.Writing.Collection",
            "collection",
            "text/markdown",
            "Kernel.Writing projection of one Collection and its hosted editions.",
            _kernel_collection,
        ),
        DiagramRenderer(
            "Kernel.Writing.Line.Annotation",
            "annotation",
            "text/markdown",
            "Compact Kernel.Writing projection of one free-standing Line.Annotation.",
            _kernel_line_annotation,
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
    "DiagramRenderError",
    "DiagramRenderResult",
    "DiagramRenderTarget",
    "DiagramRenderer",
    "annotation_render_target",
    "block_render_target",
    "collection_render_target",
    "line_render_target",
    "model_render_target",
    "renderer",
    "renderers",
]
