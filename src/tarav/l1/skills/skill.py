"""The base Skill type."""

from __future__ import annotations

from pathlib import Path

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip

from .catalog import SKILL_MARKER_FILENAME, parse_skill_frontmatter
from .marker import SkillMarker
from .workflow import SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb 50bc3738bfe0
class TaravSkill(TaravObject):
    """A skill: a folder an agent harness loads through its `SKILL.md`.

    Abstract: every kind of skill subtypes this class and supplies `root`, the
    skill folder; the primitives below read only what that folder holds. A
    subtype adds how the skill is modelled and developed. `SkwSkill`, an SKW
    skill package with its blocks, reading relationships and checks, is the
    kind other workflows commonly use.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e0cc9227-e7a4-4b55-ab62-282f3269af55"),
            name="Tarav.Skills.Skill",
            workflow=SKILLS_WORKFLOW_SHIP,
        )

    @property
    def root(self) -> Path:
        """The skill folder."""
        raise NotImplementedError(f"{type(self).__name__} does not locate its folder")

    @property
    def skill_id(self):
        """The UUID in the skill's `.tarav/skill.json`."""
        return SkillMarker.of(self.root).id

    @property
    def entrypoint(self) -> Path:
        """The file a harness reads first."""
        return self.root / SKILL_MARKER_FILENAME

    def frontmatter(self) -> dict[str, str]:
        """The entrypoint's frontmatter fields; empty when it has none."""
        return parse_skill_frontmatter(self.root)

    @property
    def skill_name(self) -> str:
        """The name a harness lists: the frontmatter's, else the folder's."""
        return self.frontmatter().get("name") or self.root.name

    @property
    def description(self) -> str | None:
        """What a harness shows to decide when to load the skill."""
        return self.frontmatter().get("description")
