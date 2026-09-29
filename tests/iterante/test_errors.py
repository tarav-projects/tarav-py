"""Tests for the controlled error surface (Mechanism 1)."""

from tarav.l1.iterante.errors import ERROR_LOG_NAME, FATAL_MESSAGE, record_fatal

LEAKY = "No mission-snapshot.py in /secret/.tarav/missions/demo/runs/abc123"


def _boom(msg):
    try:
        raise RuntimeError(msg)
    except RuntimeError as e:
        return e


class TestRecordFatal:
    def test_returns_generic_message_with_no_mechanics(self, tmp_path):
        msg = record_fatal(_boom(LEAKY), log_dir=tmp_path)
        assert msg == FATAL_MESSAGE
        for leak in ("mission-snapshot.py", "/secret", ".tarav", "runs", "abc123"):
            assert leak not in msg

    def test_logs_full_detail(self, tmp_path):
        record_fatal(_boom(LEAKY), log_dir=tmp_path)
        log = (tmp_path / ERROR_LOG_NAME).read_text()
        assert "mission-snapshot.py" in log
        assert "/secret/.tarav" in log
        assert "RuntimeError" in log

    def test_verbose_returns_full_traceback(self, tmp_path):
        msg = record_fatal(_boom("kaboom"), log_dir=tmp_path, verbose=True)
        assert "Traceback" in msg
        assert "kaboom" in msg

    def test_log_dir_none_does_not_raise(self):
        assert record_fatal(_boom("x"), log_dir=None) == FATAL_MESSAGE

    def test_unwritable_log_dir_does_not_raise(self, tmp_path):
        a_file = tmp_path / "afile"
        a_file.write_text("x")
        # parent is a file → mkdir must fail internally, but record_fatal swallows it
        assert record_fatal(_boom("x"), log_dir=a_file / "sub") == FATAL_MESSAGE
