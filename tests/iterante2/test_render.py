"""Tests for call frame rendering."""

from tarav.iterante2.render import render_frame


class TestRenderFrame:
    def test_task_frame(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Fix the bug"},
            token="abcd123456",
            tick=1,
            mission_id="demo",
        )
        assert "## [demo] Turn 1" in frame
        assert "### Fix the bug" in frame
        assert "iterante2 submit --token abcd123456" in frame
        assert "When done:" in frame

    def test_task_with_body(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work", "body": "Details here"},
            token="abcd123456",
            tick=2,
        )
        assert "Details here" in frame

    def test_branch_shows_answers(self):
        frame = render_frame(
            call={"type": "branch", "id": "b1", "title": "Choose", "answers": ["left", "right"]},
            token="abcd123456",
            tick=1,
        )
        assert "**Choose one:**" in frame
        assert "- `left`" in frame
        assert "- `right`" in frame

    def test_poll_shows_question(self):
        frame = render_frame(
            call={"type": "poll", "id": "p1", "title": "Check", "question": {"text": "What happened?"}},
            token="abcd123456",
            tick=1,
        )
        assert "**Question:** What happened?" in frame

    def test_handoff_footer(self):
        frame = render_frame(
            call={"type": "handoff", "id": "handoff", "title": "Final report"},
            token="abcd123456",
            tick=3,
        )
        assert "Submit your report:" in frame

    def test_freeform(self):
        frame = render_frame(
            call={"type": "freeform", "id": "f1", "title": "Open ended"},
            token="abcd123456",
            tick=1,
        )
        assert "### Open ended" in frame
        assert "When done:" in frame

    def test_no_mission_id(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work"},
            token="abcd123456",
            tick=1,
        )
        assert "## [run] Turn 1" in frame

    def test_footer_contains_exact_token(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work"},
            token="abcd123456",
            tick=1,
        )
        assert "--token abcd123456" in frame

    def test_planted_path_in_body_is_redacted_surface_preserved(self):
        frame = render_frame(
            call={
                "type": "task",
                "id": "t1",
                "title": "Work",
                "body": "open /home/u/.tarav/missions/demo/runs/ab12cd/_mission-snap.py",
            },
            token="abcd123456",
            tick=1,
            mission_id="demo",
        )
        assert "‹run›" in frame
        assert ".tarav" not in frame
        # preserved surface survives redaction
        assert "## [demo] Turn 1" in frame
        assert "iterante2 submit --token abcd123456" in frame
