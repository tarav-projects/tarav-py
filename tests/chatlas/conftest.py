from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_anchory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTOS_ANCHORY_REGISTRY",
        str(tmp_path / ".agentos" / "anchory" / "registry.json"),
    )
    monkeypatch.setenv(
        "AGENTOS_ANCHORY_GLOBAL_DEPOT",
        str(tmp_path / ".agentos" / "anchory" / "depot"),
    )
