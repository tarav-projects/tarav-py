"""Space for Project-specific Program semantics, not yet prescribed."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.programs import TaravProgram
from tarav.l1.programs.workflow import PROGRAMS_WORKFLOW_SHIP


class ProjectProgram(TaravProgram):
    """Project-oriented specialization; attachment mechanics remain undefined."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("e8f21343-b1fb-4831-9fdb-20dd221ab15d"),
            name="Tarav.Project.Program",
            workflow=PROGRAMS_WORKFLOW_SHIP,
        )


__all__ = ["ProjectProgram"]
