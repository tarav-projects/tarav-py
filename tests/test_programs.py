"""The Programs bootstrap adds classification, not execution policy."""

import pytest

from tarav.l0.kernel import Ship, TaravWorkflow, entity
from tarav.l1.programs import ProgramsWorkflow, TaravProgram
from tarav.l2.project.programs import ProjectProgram
from tarav.l3.runtime import create_runtime


def test_programs_workflow_and_specialization():
    runtime = create_runtime()
    assert runtime.workflows.get("programs") is ProgramsWorkflow
    assert ProgramsWorkflow() is ProgramsWorkflow()
    assert ProgramsWorkflow().workflow is TaravWorkflow()
    assert issubclass(ProjectProgram, TaravProgram)
    assert entity(ProgramsWorkflow).id != ProgramsWorkflow().id
    for cls in (TaravProgram, ProjectProgram):
        assert entity(cls).workflow_ship == ProgramsWorkflow().id
        assert runtime.records.resolve_ship(entity(cls).id) is cls


@pytest.mark.parametrize("cls", [TaravProgram, ProjectProgram])
def test_program_placeholder_record_roundtrip(cls, tmp_path):
    import json

    program = cls(id=Ship("bbf8d724-f685-4919-99dd-e5cf11350e18"))
    record = program.to_record()
    assert record == {"type": entity(cls).name, "id": str(program.id)}
    assert cls.from_record(record).id == program.id
    path = tmp_path / "program.json"
    path.write_text(json.dumps(record))
    loaded = create_runtime().records.load(path)
    assert type(loaded) is cls
    assert loaded.id == program.id
