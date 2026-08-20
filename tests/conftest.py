from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_anchory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TARAV_ANCHORY_REGISTRY",
        str(tmp_path / ".tarav" / "anchory" / "registry.json"),
    )
    monkeypatch.setenv(
        "TARAV_ANCHORY_GLOBAL_DEPOT",
        str(tmp_path / ".tarav" / "anchory" / "depot"),
    )
    # The index depot defaults to a real public path holding the live corpus. A test that
    # forgets to configure a home would otherwise write into it — which happened once, and
    # was only recoverable because the depot is git-tracked. Isolation belongs here, beside
    # the anchory guard that exists for the same reason, rather than in each fixture.
    monkeypatch.setenv("TARAV_INDEX_HOME", str(tmp_path / ".tarav"))
