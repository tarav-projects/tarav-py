"""Enter Tarav explicitly for test collection and spawned test processes."""

# tarav.breadcrumb 65534b90ac10e26b17c8a1fd072ba890a365632d0afabfd403d7b21936ad5f61
import tarav_bypass  # noqa: F401

import os
import tempfile

# Code run by the suite, in process or in spawned commands, stays out of the
# machine's run registry.
os.environ["TARAV_RUN_REGISTRY"] = tempfile.mkdtemp(prefix="tarav-run-registry-")
os.environ["TARAV_CHECK_REPORTS"] = tempfile.mkdtemp(prefix="tarav-check-reports-")
