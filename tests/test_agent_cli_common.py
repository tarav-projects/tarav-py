from __future__ import annotations

import pytest

from agentos._core.errors import CliError
from agentos.agent._cli_common import normalize_updated_since


def test_normalize_updated_since_uses_seconds_by_default(monkeypatch) -> None:
    monkeypatch.setattr("agentos.agent._cli_common.time.time", lambda: 1_000.0)

    assert normalize_updated_since("30") == 970.0


def test_normalize_updated_since_supports_duration_units(monkeypatch) -> None:
    monkeypatch.setattr("agentos.agent._cli_common.time.time", lambda: 10_000.0)

    assert normalize_updated_since("2h") == 2_800.0
    assert normalize_updated_since("3d") == -249_200.0


@pytest.mark.parametrize("value", ["", "0", "abc", "7x"])
def test_normalize_updated_since_rejects_invalid_values(value: str) -> None:
    with pytest.raises(CliError):
        normalize_updated_since(value)
