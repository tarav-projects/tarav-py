"""Typed `.skw` depot records.

The depot is a normal directory Record.  Its concrete type decides which
operations and schema apply; this base deliberately adds no manifest policy.
"""

from pathlib import Path

from tarav.kernel import TaravClass
from tarav.kernel import DirectoryRecord, TypeShip
from tarav.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


class SkwDepot(DirectoryRecord):
    """A `.skw` directory selected through the trusted Record registry."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ea063ac9-d2a7-4927-a490-8877e61983dd'),
            name='Tarav.Skillware.Depot',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    @property
    def depot(self) -> Path:
        """The retained `.skw` directory."""

        return self.directory.resolve()

    @property
    def root(self) -> Path:
        """The project directory containing this depot."""

        return self.depot.parent
