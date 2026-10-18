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
