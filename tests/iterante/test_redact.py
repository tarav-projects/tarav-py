"""Tests for the output-sensor primitive (Mechanism 2)."""

import re

from tarav.l1.iterante import redact as redact_mod
from tarav.l1.iterante.redact import Sensor, redact


class TestSeedSensors:
    def test_run_path(self):
        out = redact("opened /home/u/.tarav/missions/demo/runs/ab12cd/_mission-snap.py ok")
        assert "‹run›" in out
        assert ".tarav" not in out
        assert "_mission-snap.py" not in out

    def test_mission_path(self):
        out = redact("see /home/u/.tarav/missions/demo/mission.py")
        assert "‹mission›" in out
        assert ".tarav" not in out

    def test_install_path(self):
        out = redact("/home/u/.local/share/uv/tools/iterante/lib/site-packages/iterante/cli.py")
        assert "‹iterante-internal›" in out
        assert "uv/tools" not in out
        assert "site-packages" not in out

    def test_abs_path_catchall(self):
        out = redact("wrote /private/var/folders/xy/T/scratch.txt")
        assert "‹path›" in out
        assert "/private" not in out

    def test_clean_text_untouched(self):
        text = "Step 1 — compare lines 1-60 against library/foo/foo.md"
        assert redact(text) == text


class TestPipelineBehaviour:
    def test_preserved_surface(self):
        frame = (
            "## [demo] Turn 1\n\n### Fix the bug\n\n---\n"
            "When done: `iterante submit --token abcd123456`\n"
        )
        assert redact(frame) == frame

    def test_bypass_returns_verbatim(self, monkeypatch):
        monkeypatch.setenv("ITERANTE_NO_REDACT", "1")
        leaky = "/home/u/.tarav/missions/demo/runs/ab12cd/_mission-snap.py"
        assert redact(leaky) == leaky

    def test_fail_open_skips_raising_sensor(self, monkeypatch):
        def boom(_m):
            raise RuntimeError("sensor blew up")

        bad = Sensor(name="bad", pattern=re.compile(r"X"), replacement=boom)
        monkeypatch.setattr(redact_mod, "SENSORS", (bad, *redact_mod.SENSORS))
        out = redact("X marks /home/u/.tarav/missions/demo/runs/ab12cd/_mission-snap.py")
        # did not crash, and the good sensors still ran
        assert "‹run›" in out
