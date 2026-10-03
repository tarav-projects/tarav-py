"""Line-owned semantic assertions and their adaptation to ranking."""

import json

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l2.scoring.assertions import (
    Assertion, AssessmentCase, IncompleteCaseScope, ScoringDetails,
)
from tarav.l2.scoring.model import (
    DIAGRAM_LINE_EDITION_REFERENCE_TYPE, GROUNDING_POOL_TYPE,
    LineEditionReferenceInterface, ScoringError, record_reference,
)
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l1.lines.identity import LINES_WORKFLOW_SHIP


class LineGroundingCase(AssessmentCase):
    """Closed claim, Block context, and rendered Support.Set for grounding judgment."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('5cd3c02b-950e-4358-8d33-b3cb9cf0f902'),
            name='Index.Line.Grounding.AssessmentCase',
            workflow=LINES_WORKFLOW_SHIP,
        )

    class RecordInterface(AssessmentCase.RecordInterface):
        line_text: str
        block_label: str | None
        peer_lines: list[str]
        support: list[dict]

    @classmethod
    def record_example(cls):
        return cls(
            assertion_ref=LineGroundingAssertion.from_record(
                LineGroundingAssertion.record_example()).reference(),
            question='How well is this Line supported?',
            presentation='Line and declared Support.Set.',
            line_text='Example Line', block_label=None, peer_lines=[], support=[{'turns': []}],
        ).to_record()


class LineSupportInventoryCase(AssessmentCase):
    """Closed inventory of the exact Line edition's declared support."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('f4d8def1-1636-4b6c-bf60-e4319898d149'),
            name='Index.Line.SupportInventory.AssessmentCase',
            workflow=LINES_WORKFLOW_SHIP,
        )

    class RecordInterface(AssessmentCase.RecordInterface):
        edition_id: str
        support_entries: list[dict]

    @classmethod
    def record_example(cls):
        assertion = LineGroundingAssertion.from_record(LineGroundingAssertion.record_example())
        return cls(
            assertion_ref=assertion.reference(),
            question='What support is declared?', presentation='Support inventory.',
            edition_id=assertion.subject_ref['edition_id'], support_entries=[{'turns': []}],
        ).to_record()


class LineGroundingAssertion(Assertion):
    """The Line edition's full claim is supported by its declared Support.Set."""

    pool_types = (GROUNDING_POOL_TYPE,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('d3ae6fb4-89b6-4e08-8c1a-fc29dd3fd48c'),
                          name='Index.Line.Grounding.Assertion', workflow=LINES_WORKFLOW_SHIP)

    @classmethod
    def validate_subject(cls, subject):
        value = super().validate_subject(subject)
        LineEditionReferenceInterface.model_validate(value, strict=True)
        for key in ('namespace_id', 'line_ship', 'edition_id'):
            Ship(value[key])
        return value

    @classmethod
    def supports_pool(cls, pool_type):
        if pool_type not in cls.pool_types:
            raise ScoringError(f'Line grounding does not support {pool_type}')

    @classmethod
    def create_pool(cls, *, name, pool_type, pool_registry):
        cls.supports_pool(pool_type)
        return pool_registry.resolve(pool_type).create(name=name)

    @classmethod
    def from_line(cls, *, line_ship, namespace_id, projection):
        if projection.namespace_id != namespace_id:
            raise ScoringError('Projection belongs to another Namespace')
        try:
            line = projection.line(line_ship)
        except DiagramError as exc:
            raise ScoringError(f'Line {line_ship} does not belong to the current Diagram Model') from exc
        edition = line.current_edition
        if edition is None:
            raise ScoringError(f'Line has no current edition: {line_ship}')
        return cls({'type': DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
                    'namespace_id': namespace_id, 'line_ship': line.ship,
                    'edition_id': edition.annotation.id})

    def resolve_subject(self, *, projection):
        """Select the retained edition, never silently switch to the latest one."""
        if projection.namespace_id != self.subject_ref['namespace_id']:
            raise ScoringError('Projection belongs to another Namespace')
        line_ship = self.subject_ref['line_ship']
        edition_id = self.subject_ref['edition_id']
        try:
            line = projection.line(line_ship)
            block = projection.block(line.block_ship)
        except DiagramError as exc:
            raise ScoringError(f'Line {line_ship} does not belong to the current Diagram Model') from exc
        editions = tuple(e for e in line.editions if e.annotation.id == edition_id)
        if len(editions) != 1:
            raise ScoringError(f'Line Edition does not resolve: {edition_id}')
        return line, block, editions[0]

    def evidence(self, *, projection, evidence):
        _, _, edition = self.resolve_subject(projection=projection)
        support = edition.annotation.render_support(evidence)
        if not support:
            raise ScoringError(f"Line has no declared Support.Set: {self.subject_ref['line_ship']}")
        return support

    @classmethod
    def assessment_case_types(cls):
        # tarav.breadcrumb 69595ba12bd1b514fb8c74d10be475f0f194ee8751724df9f79deac07bc818ce
        return (LineGroundingCase, LineSupportInventoryCase)

    def _build_assessment_case(self, case_type, *, projection=None, evidence=None):
        if projection is None or evidence is None:
            raise IncompleteCaseScope('Line assessment needs a projection and resolved evidence')
        line, block, edition = self.resolve_subject(projection=projection)
        support = edition.annotation.render_support(evidence)
        if not support:
            raise IncompleteCaseScope('Line assessment needs its declared Support.Set')
        peers = [
            peer.current_edition.text for peer in block.lines
            if peer.ship != line.ship and peer.current_edition is not None
        ]
        if case_type is LineGroundingCase:
            return LineGroundingCase(
                assertion_ref=self.reference(),
                question='How completely does the declared Support.Set support this Line claim?',
                presentation=_render_candidate(
                    line_text=edition.text, block_label=block.current_label,
                    peer_lines=peers, support=support,
                ),
                line_text=edition.text,
                block_label=block.current_label,
                peer_lines=peers,
                support=support,
            )
        if case_type is LineSupportInventoryCase:
            return LineSupportInventoryCase(
                assertion_ref=self.reference(),
                question='What support is declared for this exact Line edition?',
                presentation=json.dumps(
                    {'line': edition.text, 'support': support},
                    sort_keys=True, ensure_ascii=False,
                ),
                edition_id=str(edition.annotation.id),
                support_entries=support,
            )
        raise AssertionError('Declared case Type has no producer')

    def candidate(self, *, enrollment, pool_type, projection, evidence):
        self.supports_pool(pool_type)
        if enrollment.get('assertion_ref') != self.reference():
            raise ScoringError('Enrollment belongs to another Assertion')
        line, block, edition = self.resolve_subject(projection=projection)
        support = self.evidence(projection=projection, evidence=evidence)
        peer_lines = [p.current_edition.text for p in block.lines
                      if p.ship != line.ship and p.current_edition is not None]
        return {'id': edition.annotation.id, 'enrollment_ref': record_reference(enrollment),
                'presentation': _render_candidate(line_text=edition.text,
                                                  block_label=block.current_label,
                                                  peer_lines=peer_lines, support=support),
                'appendix': []}

    def ships(self):
        return (*super().ships(), *(Ship(self.subject_ref[key])
                                   for key in ('namespace_id', 'line_ship', 'edition_id')))

    def obj_context(self, builder):
        super().obj_context(builder)
        builder.add('evidence', opener=lambda: ScoringDetails.from_record({
            'type': 'Tarav.Scoring.Details',
            'reference': self.subject_ref,
            'relation': 'declared Support.Set of this exact Line edition',
        }))

    @classmethod
    def record_example(cls):
        return cls({'type': DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
                    'namespace_id': '00000000-0000-4000-8000-000000000001',
                    'line_ship': '00000000-0000-4000-8000-000000000002',
                    'edition_id': '00000000-0000-4000-8000-000000000003'}).to_record()


def _render_candidate(*, line_text, block_label, peer_lines, support):
    sections = [f"Block: {block_label or '(unlabeled Block)'}", '', 'Line claim:', line_text]
    if peer_lines:
        sections.extend(('', 'Peer Lines establishing Block context:'))
        sections.extend(f'- {text}' for text in peer_lines)
    sections.extend(('', 'Declared Support.Set:'))
    for member_index, member in enumerate(support, start=1):
        sections.append(f'\nSupport member {member_index}:')
        turns = member.get('turns', [])
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            side = turn.get('side', 'unknown')
            role = 'root' if turn.get('root') else 'context'
            sections.extend((f'[{role}; {side}]', str(turn.get('text', ''))))
    return '\n'.join(sections)
