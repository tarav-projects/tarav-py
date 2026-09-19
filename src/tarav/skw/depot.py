"""Typed `.skw` depot records.

The depot is a normal directory Record.  Its concrete type decides which
operations and schema apply; this base deliberately adds no manifest policy.
"""

from pathlib import Path

from tarav.harness import DirectoryRecord, TypeShip


class SkwDepot(DirectoryRecord):
    """A `.skw` directory selected through the trusted Record registry."""

    type_name = "Tarav.Skillware.Depot"
    type_ship = TypeShip("ea063ac9-d2a7-4927-a490-8877e61983dd")

    @property
    def depot(self) -> Path:
        """The retained `.skw` directory."""

        return self.directory.resolve()

    @property
    def root(self) -> Path:
        """The project directory containing this depot."""

        return self.depot.parent
