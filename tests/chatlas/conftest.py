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
