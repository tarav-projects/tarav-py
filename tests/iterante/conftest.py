"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_state_home(tmp_path_factory, monkeypatch):
    """Redirect iterante run state to a tmp dir so tests never write into the
    real ~/.tarav. Hygiene (keeps the dev's home clean, scans tight), not a
    correctness gate — run resolution matches full token/id regardless.

    Subprocess CLI tests inherit this because `run_cli` forwards os.environ.
    """
    home = tmp_path_factory.mktemp("iterante-state-home")
    monkeypatch.setenv("ITERANTE_STATE_HOME", str(home))
