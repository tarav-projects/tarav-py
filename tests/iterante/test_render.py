"""Tests for call frame rendering."""

from agentos.iterante.render import render_frame


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
        assert "iterante submit --token abcd123456" in frame
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

    def test_completed_is_terminal_no_submit_no_report(self):
        frame = render_frame(
            call={"type": "completed", "id": "completed"},
            token="abcd123456",
            tick=3,
        )
        # runtime-owned terminal message; no submit footer, no report wording
        assert "complete" in frame.lower()
        assert "submit" not in frame.lower()
        assert "report" not in frame.lower()
        assert "When done:" not in frame

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

    def test_no_expects_keeps_generic_footer(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work"},
            token="abcd123456",
            tick=1,
        )
        assert "iterante submit --token abcd123456" in frame
        assert "--answer" not in frame
        assert "--data" not in frame

    def test_none_contract_renders_bare_submit(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work", "expects": None},
            token="abcd123456",
            tick=1,
        )
        assert "iterante submit --token abcd123456" in frame
        assert "--answer" not in frame
        assert "--data" not in frame

    def test_enum_contract_renders_answer_options(self):
        frame = render_frame(
            call={
                "type": "branch",
                "id": "b1",
                "title": "Choose",
                "answers": ["left", "right"],
                "expects": {"answer": ["left", "right"]},
            },
            token="abcd123456",
            tick=1,
        )
        assert "--answer <left|right>" in frame

    def test_str_contract_renders_text_answer(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work", "expects": {"answer": "str"}},
            token="abcd123456",
            tick=1,
        )
        assert '--answer "<text>"' in frame

    def test_bool_contract_renders_bool_answer(self):
        frame = render_frame(
            call={"type": "task", "id": "t1", "title": "Work", "expects": {"answer": "bool"}},
            token="abcd123456",
            tick=1,
        )
        assert "--answer <true|false>" in frame

    def test_data_contract_renders_data_flag_and_shape(self):
        frame = render_frame(
            call={
                "type": "task",
                "id": "t1",
                "title": "Work",
                "expects": {"data": {"name": "str", "count": "int"}},
            },
            token="abcd123456",
            tick=1,
        )
        assert "--data '<json>'" in frame
        assert '"name"' in frame
        assert '"count"' in frame

    def test_planted_path_in_body_is_redacted_surface_preserved(self):
        frame = render_frame(
            call={
                "type": "task",
                "id": "t1",
                "title": "Work",
                "body": "open /home/u/.agentos/missions/demo/runs/ab12cd/_mission-snap.py",
            },
            token="abcd123456",
            tick=1,
            mission_id="demo",
        )
        assert "‹run›" in frame
        assert ".agentos" not in frame
        # preserved surface survives redaction
        assert "## [demo] Turn 1" in frame
        assert "iterante submit --token abcd123456" in frame
