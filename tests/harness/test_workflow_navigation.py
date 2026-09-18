from tarav.harness import FileRecord
import pytest
from tarav.harness.workflows import WorkflowRegistry
from tarav.navigation import FilesystemProvider, Navigation, RecordProvider


def test_external_workflow_registers_and_navigates(tmp_path):
    code = tmp_path / "plugin.py"
    code.write_text("""from tarav.harness import FileRecord
from tarav.harness.workflows import Workflow
class Example(Workflow):
    name = "example"
    record_types = (FileRecord,)
def register(registry):
    registry.register(Example())
""")
    registry = WorkflowRegistry()
    registry.load(code)
    data = tmp_path / "data"
    data.mkdir()
    (data / "one.json").write_text('{"type":"Tarav.FileRecord","content":"hello"}')
    nav = Navigation()
    nav.mount("example", FilesystemProvider(data, registry.records))
    assert nav.list().value[0].name == "example"
    assert nav.list("/example").value[0].name == "one.json"
    assert isinstance(nav.load("/example/one.json").value, FileRecord)
    assert not nav.load("/example/../plugin.py").ok


def test_provider_failure_is_inspectable_and_does_not_block_other_provider():
    class Broken(RecordProvider):
        def list(self, address=""):
            raise RuntimeError("offline")

    nav = Navigation()
    nav.mount("broken", Broken())
    result = nav.list("/broken")
    assert not result.ok
    assert result.findings[0].operands["message"] == "offline"
    assert nav.list().ok


def test_failed_external_registration_does_not_leak_types_or_workflows(tmp_path):
    code = tmp_path / "broken.py"
    code.write_text("""from tarav.harness import FileRecord
from tarav.harness.workflows import Workflow
class Example(Workflow):
    name = "example"
    record_types = (FileRecord,)
def register(registry):
    registry.register(Example())
    raise ValueError("incomplete registration")
""")
    registry = WorkflowRegistry()
    records = registry.records
    with pytest.raises(ValueError, match="incomplete registration"):
        registry.load(code)
    assert registry.records is records
    assert records.record_types == ()
    assert registry.workflows == {}


def test_invalid_provider_response_is_a_poi():
    class Invalid(RecordProvider):
        def load(self, address):
            return {"type": "uninterpreted"}

    nav = Navigation()
    nav.mount("invalid", Invalid())
    result = nav.load("/invalid/record")
    assert not result.ok
    assert result.findings[0].operands["error"] == "TypeError"
