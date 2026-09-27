from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import stat

import pytest

from tarav.l0._core import operational_logging


@pytest.fixture
def restore_tarav_logger() -> object:
    logger = logging.getLogger(operational_logging.LOGGER_NAMESPACE)
    handlers = tuple(logger.handlers)
    level = logger.level
    propagate = logger.propagate
    yield
    for handler in tuple(logger.handlers):
        if handler not in handlers:
            logger.removeHandler(handler)
            handler.close()
    logger.setLevel(level)
    logger.propagate = propagate


def test_operational_logging_persists_debug_and_only_warns_on_console(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_tarav_logger: object,
) -> None:
    del restore_tarav_logger
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / ".tarav"))
    path = operational_logging.configure_operational_logging()
    logger = logging.getLogger("tarav.example")

    logger.debug(
        "quiet lifecycle",
        extra=operational_logging.event_extra("example.quiet", item=Path("item")),
    )
    logger.warning(
        "operator signal",
        extra=operational_logging.event_extra("example.warning", attempt=2),
    )

    stderr = capsys.readouterr().err
    assert "operator signal" in stderr
    assert "quiet lifecycle" not in stderr
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == [
        "example.quiet",
        "example.warning",
    ]
    assert records[0]["context"] == {"item": "item"}
    assert records[1]["context"] == {"attempt": 2}
    assert records[1]["class"] == operational_logging.OPERATIONAL_LOG_CLASS
    assert records[1]["logger"] == "tarav.example"
    assert records[1]["pid"] > 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_operational_logging_configuration_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_tarav_logger: object,
) -> None:
    del restore_tarav_logger
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / ".tarav"))
    operational_logging.configure_operational_logging()
    path = operational_logging.configure_operational_logging()

    logging.getLogger("tarav.example").warning("once")

    assert capsys.readouterr().err.count("once") == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_operational_logging_prunes_only_expired_daily_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restore_tarav_logger: object,
) -> None:
    del restore_tarav_logger
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / ".tarav"))
    log_dir = operational_logging.operational_log_dir()
    log_dir.mkdir(parents=True)
    expired = log_dir / "20000101.jsonl"
    current = log_dir / f"{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    unrelated = log_dir / "notes.jsonl"
    for path in (expired, current, unrelated):
        path.write_text("retained?\n", encoding="utf-8")

    operational_logging.configure_operational_logging(retention_days=30)

    assert not expired.exists()
    assert current.exists()
    assert unrelated.exists()


def test_operational_logging_filesystem_failure_is_non_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_tarav_logger: object,
) -> None:
    del restore_tarav_logger
    blocked_home = tmp_path / "not-a-directory"
    blocked_home.write_text("blocked", encoding="utf-8")
    monkeypatch.setenv("TARAV_HOME", str(blocked_home))

    operational_logging.configure_operational_logging()
    logging.getLogger("tarav.example").warning("still visible")

    assert "still visible" in capsys.readouterr().err
