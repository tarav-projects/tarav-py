"""Program Actions have graph roles; their Program selects the checks."""

from dataclasses import dataclass

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions import Action, ActionError, Exit, LOOP

from .workflow import PROGRAMS_WORKFLOW_SHIP


# tarav.breadcrumb ed82f157433f
class ProgramAction(Action):
    """An occurrence managed by the Program runner, outside operator StepRunner."""

    prompt = "Carry out this Program Action."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4ec785a5-aed0-4795-81a6-1dca573b07ac"),
                          name="Tarav.Programs.Action", workflow=PROGRAMS_WORKFLOW_SHIP)

    @classmethod
    def exit_named(cls, name):
        if name != "completed":
            raise ActionError("A Program Action closes through checked completion")
        return Exit("completed", by=(LOOP,))

    def output(self, name, run, context=None):
        return {}


class NodeAction(ProgramAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("ff16423a-0b82-4b8c-a086-1bb551cd3932"),
                          name="Tarav.Programs.NodeAction", workflow=PROGRAMS_WORKFLOW_SHIP)


class EdgeAction(ProgramAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8cf91949-f519-4939-bd03-8ccce5541d78"),
                          name="Tarav.Programs.EdgeAction", workflow=PROGRAMS_WORKFLOW_SHIP)


class ProgramExecutionAction(Action):
    """The overall execution, visible alongside its active Action occurrences."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("f4c8fcd0-49a6-481c-8c3b-d239a77018dd"),
                          name="Tarav.Programs.Execution", workflow=PROGRAMS_WORKFLOW_SHIP)

    @classmethod
    def exit_named(cls, name):
        if name != "finished":
            raise ActionError("A Program execution closes when no Action remains active")
        return Exit("finished", by=(LOOP,))

    def output(self, name, run, context=None):
        return {}


@dataclass(frozen=True)
class Transition:
    source: type[NodeAction]
    action: type[EdgeAction]
    target: type[NodeAction]

    def __post_init__(self):
        for value, base in ((self.source, NodeAction), (self.action, EdgeAction), (self.target, NodeAction)):
            if not isinstance(value, type) or not issubclass(value, base):
                raise TypeError(f"A Transition requires {base.__name__} classes in their graph roles")
