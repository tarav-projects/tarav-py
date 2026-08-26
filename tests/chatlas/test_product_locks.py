from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
from typing import Iterator

import pytest

from tarav.chatlas import products


@contextmanager
def _capture_lock_records() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger = products.LOGGER
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def test_product_lock_logs_lifecycle_and_releases_after_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _capture_lock_records() as records:
        with pytest.raises(RuntimeError):
            with products.product_materialization_lock(
                product="summary",
                identity_hash="a" * 64,
                chatlas_root=tmp_path,
            ):
                raise RuntimeError("failure")

    assert capsys.readouterr().err == ""
    assert [record.event for record in records] == [
        "chatlas.product.lock.acquiring",
        "chatlas.product.lock.acquired",
        "chatlas.product.lock.released",
    ]
    assert all(record.context["product"] == "summary" for record in records)
