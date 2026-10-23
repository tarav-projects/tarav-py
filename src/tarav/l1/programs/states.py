"""States own conditions; StateActions reuse them when establishing an arrival."""

from dataclasses import dataclass

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions import Action, ActionError, Closing, Exit, LOOP
from tarav.l1.checks import CheckProvider, CheckSuite

from .workflow import PROGRAMS_WORKFLOW_SHIP


# tarav.breadcrumb c55dc47abfd0
class State(CheckProvider):
    """A State bound to one ProgramRun; specialize Checks to describe its conditions."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("0d15cd69-b30b-4968-bc2d-1aac54218460"),
                          name="Tarav.Programs.State", workflow=PROGRAMS_WORKFLOW_SHIP)

    def __init__(self, run):
        self.run = run

    class Checks(CheckProvider.Checks):
        def suite(self):
            return CheckSuite([], name="Program State")


class StateReached(Closing):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("7ca5fea9-d8d6-49e4-9a01-bfb4a2e09faf"),
                          name="Tarav.Programs.StateReached", workflow=PROGRAMS_WORKFLOW_SHIP)

    class RecordInterface(Closing.RecordInterface):
        program_run: str
        state: str
        arrival: int

    class Records(Closing.Records):
        def record_example(self):
            return {**super().record_example(), "program_run": "4a9af366-b093-4ba0-aedd-6d71a3f2bbd0",
                    "state": "0d15cd69-b30b-4968-bc2d-1aac54218460", "arrival": 1}


# tarav.breadcrumb d868900a63ae
class StateAction(Action):
    """Program-managed work to reach State. Operator StepRunner cannot close it."""

    State = State
    prompt = "Establish the destination State's conditions."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("eec90d17-06cb-46b3-8cf5-83dd8c2c437a"),
                          name="Tarav.Programs.StateAction", workflow=PROGRAMS_WORKFLOW_SHIP)

    def prerequisites(self, run):
        return ()

    def checks(self, run, *, destination=None):
        return CheckSuite([*self.prerequisites(run), self.State(destination or run).checks.suite()],
                          name="StateAction completion")

    @classmethod
    def exit_named(cls, name):
        if name != "reached":
            raise ActionError("A StateAction closes only by reaching its State")
        return Exit("reached", by=(LOOP,), closing=StateReached)

    def output(self, name, run, context=None):
        return {}


class ProgramExecutionAction(Action):
    """The overall Program execution, visible alongside its child StateActions."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("f4c8fcd0-49a6-481c-8c3b-d239a77018dd"),
                          name="Tarav.Programs.Execution", workflow=PROGRAMS_WORKFLOW_SHIP)

    @classmethod
    def exit_named(cls, name):
        if name != "finished":
            raise ActionError("A Program execution closes at a terminal State")
        return Exit("finished", by=(LOOP,))

    def output(self, name, run, context=None):
        return {}


@dataclass(frozen=True)
class Transition:
    source: type[State]
    action: type[StateAction]

    def __post_init__(self):
        if not isinstance(self.source, type) or not issubclass(self.source, State):
            raise TypeError("A transition source must be a State class")
        if not isinstance(self.action, type) or not issubclass(self.action, StateAction):
            raise TypeError("A transition action must be a StateAction class")
        if not isinstance(self.action.State, type) or not issubclass(self.action.State, State):
            raise TypeError("A StateAction must name a destination State class")
