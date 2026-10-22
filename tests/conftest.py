"""Enter Tarav explicitly for test collection and spawned test processes."""

# tarav.breadcrumb 65534b90ac10
import tarav_bypass  # noqa: F401

import os
import tempfile

# Code run by the suite, in process or in spawned commands, stays out of the
# machine's run registry.
os.environ["TARAV_RUN_REGISTRY"] = tempfile.mkdtemp(prefix="tarav-run-registry-")
os.environ["TARAV_RECORDS"] = tempfile.mkdtemp(prefix="tarav-records-")
# Hooks the suite installs run gitleaks; their reports stay out of the machine's depot.
os.environ["TARAV_GITLEAKS_ROOT"] = tempfile.mkdtemp(prefix="tarav-gitleaks-")
# Notebook capture now commits through repository-keyed witnesses too.
os.environ["TARAV_GIT_CHANGES_ROOT"] = tempfile.mkdtemp(prefix="tarav-git-changes-")


import json
import pytest


@pytest.fixture(autouse=True)
def notebook_repository_owner(tmp_path_factory, monkeypatch):
    """Capture's default action owner is isolated from the real System Project."""
    # tarav.breadcrumb 573f5f3fa4a2
    from tarav.l2 import notebook_capture

    data = tmp_path_factory.mktemp("notebook-owner")
    owner = data / "system/.tarav"
    owner.mkdir(parents=True)
    (owner / "project.json").write_text(json.dumps({
        "project_id": "c85b1c1c-cecf-4d2d-b5ba-f93040cc8ac4",
        "name": "Test System", "type": "Tarav.Project",
    }))
    monkeypatch.setattr(notebook_capture, "default_tarav_data_root", lambda: data)
