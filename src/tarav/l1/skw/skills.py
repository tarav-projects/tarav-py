"""Typed components specific to deployable SKW skills."""

from __future__ import annotations

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.skw.document import SkwBlock
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb b7587610e2af5af9ea51dfbddae8571e0b452713dbb757dac8bf38698f7299f3
class SkillLink(SkwBlock):
    """One retained link output with one authoritative loading target."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1a03778c-c647-49b1-b121-0b7e4d464cf7'),
            name='Tarav.Skillware.SkillLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    class RecordInterface(SkwBlock.RecordInterface):
        target: str
        caption: str

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name,
                "id": "d9c4a653-d76a-4f44-b823-af7df64783b0", "label": "example",
                "target": "introduction", "caption": "Read more",
                "content": ["[Read more](SKILL.md)"]}

    def __init__(self, record):
        super().__init__(record)
        if not self['target'] or not self['caption']:
            raise ValueError('SkillLink requires a target and caption')

    def inline_only(self) -> bool:
        return True

    def produce(self, document) -> list[str]:
        loading = getattr(document, 'loading', None)
        if loading is None:
            raise ValueError('SkillLink production requires a Skill loading model')
        return [loading.link_output(self, document.target)]

    def output_findings(self, document, lock_entry: dict) -> list[dict]:
        if self.get('content') is None:
            return []
        try:
            expected = self.produce(document)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            return [{'kind': 'invalid-produced-output', 'block': self.label,
                     'detail': str(exc)}]
        if self.get('content') != expected:
            return [{'kind': 'stale-produced-output', 'block': self.label}]
        return []


SKILL_COMPONENT_TYPES = (SkillLink,)
