"""Trusted Python Program definitions; the shared runner owns execution mechanics."""

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.checks import CheckSuite

from .workflow import PROGRAMS_WORKFLOW_SHIP, ProgramsWorkflow
from .actions import ProgramAction, ProgramExecutionAction, NodeAction, EdgeAction, Transition
from .runs import ActiveAction, ProgramRun
from .runner import ProgramError, ProgramRunner


class TaravProgram(TaravEntity):
    """Define a graph in Python; specialize available() for conditional routes."""

    initial = (NodeAction,)
    terminal = ()
    graph: tuple[Transition, ...] = ()

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("7effdc1d-9f87-49d2-9842-15215c4a3356"),
            name="Tarav.Program",
            workflow=PROGRAMS_WORKFLOW_SHIP,
        )

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return cls(id=Ship("bbf8d724-f685-4919-99dd-e5cf11350e18")).records.to_record()

    def available(self, run, occurrence):
        """Return only declared outgoing connections; authors can filter this result."""
        return tuple(edge for edge in self.graph if entity(edge.source).id == occurrence.action)

    # tarav.breadcrumb 3f083c93b437
    def checks(self, run, occurrence, *, operation):
        """Select checks for enter/status/complete; their meaning belongs to this Program."""
        return CheckSuite((), name=f"{occurrence.action}: {operation}")

    @classmethod
    def runner(cls, *, project=None, registry=None):
        from .runner import ProgramRunner

        return ProgramRunner(cls, project=project, registry=registry)

    @classmethod
    def start(cls, *, project, data=None, registry=None):
        return cls.runner(project=project, registry=registry).start(data=data)

    @classmethod
    def step(cls, token, *, data=None, registry=None):
        return cls.runner(registry=registry).step(token, data=data)



PROGRAM_RECORD_TYPES = (ProgramRun,)
PROGRAM_ACTION_TYPES = (ProgramExecutionAction, ProgramAction, NodeAction, EdgeAction)

__all__ = ["ProgramsWorkflow", "TaravProgram", "ProgramAction", "NodeAction", "EdgeAction", "Transition",
           "ActiveAction", "ProgramRun", "ProgramRunner", "ProgramError", "ProgramExecutionAction",
           "PROGRAM_RECORD_TYPES", "PROGRAM_ACTION_TYPES"]
