import pytest
import subprocess
import sys

from tarav.l0.kernel import entity
from tarav.l3.runtime import create_runtime
from tarav.l2.lines.records import LineShipRecord, LineAnnotationRecord
from tarav.l2.unsorted.capture import CaptureManifest
from tarav.l2.unsorted.drafts import DiagramDraft
from tarav.l2.unsorted.views import DiagramViewManifest
from tarav.l2.unsorted.retired import DIAGRAM_WORKFLOW_SHIP
from tarav.l2.lines.workflow import LinesWorkflow
from tarav.l2.unsorted.workflow import UnsortedWorkflow


def test_ownership_split_does_not_redirect_retired_identity():
    runtime = create_runtime()
    assert runtime.workflows.get("lines") is LinesWorkflow
    assert runtime.workflows.get("unsorted") is UnsortedWorkflow
    for identity in ("diagram", DIAGRAM_WORKFLOW_SHIP):
        with pytest.raises(KeyError):
            runtime.workflows.get(identity)
    assert len({DIAGRAM_WORKFLOW_SHIP, LinesWorkflow().id, UnsortedWorkflow().id}) == 3
    for cls in (LineShipRecord, LineAnnotationRecord):
        assert entity(cls).workflow is LinesWorkflow()
    for cls in (CaptureManifest, DiagramDraft, DiagramViewManifest):
        assert entity(cls).workflow is UnsortedWorkflow()
    assert str(entity(LineShipRecord).id) == "18dd06c0-bdcb-48ac-b5a6-3388a601084c"


@pytest.mark.parametrize("first", [
    "tarav.l2.lines.records", "tarav.l2.models", "tarav.l2.lines.rendering",
    "tarav.l2.unsorted.storage", "tarav.l2.unsorted.capture", "tarav.l2.unsorted.views",
])
def test_extracted_modules_import_independently(first):
    result = subprocess.run(
        [sys.executable, "-c",
         f"import {first}; from tarav.l3.runtime import create_runtime; create_runtime()"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_diagram_package_has_no_domain_compatibility_exports():
    assert LineShipRecord.__module__ == "tarav.l2.lines.records"
    assert CaptureManifest.__module__ == "tarav.l2.unsorted.capture"
