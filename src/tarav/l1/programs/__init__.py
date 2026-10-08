"""Program family bootstrap; lifecycle and execution semantics remain open."""

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip

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

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return cls(id=Ship("bbf8d724-f685-4919-99dd-e5cf11350e18")).records.to_record()



__all__ = ["ProgramsWorkflow", "TaravProgram"]
