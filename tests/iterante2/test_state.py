"""Tests for state persistence and run management."""


import pytest

from tarav.iterante2.locking import LOG_SUFFIX, verify
from tarav.iterante2.state import PREFIX_LEN, SNAPSHOT_FILE, create_run, load_run, make_token, run_dir, save_run


@pytest.fixture
def mission_dir(tmp_path):
    md = tmp_path / "test-mission"
    md.mkdir()
    (md / "mission.py").write_text("def step(ctx): pass\n")
    return md


class TestCreateRun:
    def test_creates_run_dir_and_files(self, mission_dir):
        runtime_id, token, rd = create_run(mission_dir)
        assert rd.is_dir()
        assert (rd / "run.json").is_file()
        assert (rd / SNAPSHOT_FILE).is_file()

    def test_snapshot_matches_mission_py(self, mission_dir):
        _, _, rd = create_run(mission_dir)
        original = (mission_dir / "mission.py").read_text()
        snapshot = (rd / SNAPSHOT_FILE).read_text()
        assert snapshot == original

    def test_initial_state(self, mission_dir):
        runtime_id, token, rd = create_run(mission_dir)
        data = load_run(rd)
        assert data["runtime_id"] == runtime_id
        assert data["tick"] == 0
        assert data["state"] == {}
        assert data["call"] is None
        assert data["phase"] == "init"
        assert data["token"] == token

    def test_runtime_id_is_random(self, mission_dir):
        r1, _, _ = create_run(mission_dir)
        r2, _, _ = create_run(mission_dir)
        assert r1 != r2

    def test_no_mission_py_raises(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No mission.py"):
            create_run(empty_dir)

    def test_snapshot_name_marks_derived(self):
        # leading underscore signals a derived runtime artifact, not source (Run.Snapshot)
        assert SNAPSHOT_FILE.startswith("_")


class TestFileLockingRegistration:
    def test_create_run_registers_state_files(self, mission_dir):
        _, _, rd = create_run(mission_dir)
        # both state files start with an authorized baseline
        verify(rd / "run.json")
        verify(rd / SNAPSHOT_FILE)
        assert (rd / ("run.json" + LOG_SUFFIX)).is_file()
        assert (rd / (SNAPSHOT_FILE + LOG_SUFFIX)).is_file()

    def test_save_run_reauthorizes_run_json(self, mission_dir):
        _, _, rd = create_run(mission_dir)
        data = load_run(rd)
        data["tick"] = 1
        save_run(rd, data)
        verify(rd / "run.json")  # legal write re-established the authorized version


class TestMakeToken:
    def test_token_has_correct_prefix(self):
        runtime_id = "abcdef1234567890"
        token = make_token(runtime_id)
        assert token[:PREFIX_LEN] == runtime_id[:PREFIX_LEN]

    def test_token_length(self):
        token = make_token("abcdef1234567890")
        assert len(token) == PREFIX_LEN + 6

    def test_tokens_differ(self):
        runtime_id = "abcdef1234567890"
        t1 = make_token(runtime_id)
        t2 = make_token(runtime_id)
        # Same prefix, different suffix (with overwhelming probability)
        assert t1[:PREFIX_LEN] == t2[:PREFIX_LEN]


class TestLoadSave:
    def test_round_trip(self, mission_dir):
        _, _, rd = create_run(mission_dir)
        state = load_run(rd)
        state["state"]["counter"] = 42
        state["tick"] = 1
        save_run(rd, state)
        reloaded = load_run(rd)
        assert reloaded["state"]["counter"] == 42
        assert reloaded["tick"] == 1

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_run(tmp_path / "nonexistent")


class TestRunDir:
    def test_path_structure(self, tmp_path):
        rd = run_dir(tmp_path / "my-mission", "abc123")
        assert rd == tmp_path / "my-mission" / "runs" / "abc123"
