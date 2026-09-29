"""Program family bootstrap; lifecycle and execution semantics remain open."""

from tarav.l0.kernel import TaravClass, TaravEntity, TypeShip

from .workflow import PROGRAMS_WORKFLOW_SHIP, ProgramsWorkflow


class TaravProgram(TaravEntity):
    """Identified Program with only the inherited Entity contract."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("7effdc1d-9f87-49d2-9842-15215c4a3356"),
            name="Tarav.Program",
            workflow=PROGRAMS_WORKFLOW_SHIP,
        )


__all__ = ["ProgramsWorkflow", "TaravProgram"]
