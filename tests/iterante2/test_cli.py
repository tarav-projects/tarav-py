"""End-to-end CLI tests."""

import json
import os
import re
import subprocess

import pytest

from agentos.iterante2.state import SNAPSHOT_FILE


@pytest.fixture
def project_dir(tmp_path):
    """Create a project dir with a mission."""
    missions = tmp_path / ".agentos" / "missions" / "demo"
    missions.mkdir(parents=True)
    (missions / "mission.py").write_text("""
from agentos import iterante2

def setup(ctx):
    ctx.state["step_count"] = 0

def step(ctx):
    ctx.state["step_count"] = ctx.state.get("step_count", 0) + 1
    count = ctx.state["step_count"]
    if count >= 3:
        ctx.call = iterante2.calls.handoff(title="Done", body="All steps complete")
    else:
        ctx.call = iterante2.calls.task(id=f"step-{count}", title=f"Step {count}")
""")
    return tmp_path


def run_cli(*args, cwd=None, env_extra=None):
    result = subprocess.run(
        ["uv", "run", "iterante2", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "VIRTUAL_ENV": "", **(env_extra or {})},
    )
    return result


def extract_token(stdout):
    """Extract the unified token from the footer command hint."""
    m = re.search(r"--token (\w+)", stdout)
    if m:
        return m.group(1)
    raise ValueError(f"No token found in output:\n{stdout}")


def extract_runtime_id(stdout):
    for line in stdout.splitlines():
        if line.startswith("Run created:"):
            return line.split(":")[1].strip()
    raise ValueError("No runtime id found in output")


class TestInitRequestSubmit:
    def test_full_lifecycle(self, project_dir):
        # Init
        r = run_cli("init", "--mission", "demo", cwd=project_dir)
        assert r.returncode == 0, r.stderr
        assert "Run created:" in r.stdout
        t1 = extract_token(r.stdout)

        # Request — re-show current call (same token, repeatable)
        r = run_cli("request", "--token", t1, cwd=project_dir)
        assert r.returncode == 0, r.stderr
        assert "Step 1" in r.stdout

        # Submit — advance to step 2
        r = run_cli("submit", "--token", t1, "--answer", "done", cwd=project_dir)
        assert r.returncode == 0, r.stderr
        assert "Step 2" in r.stdout
        t2 = extract_token(r.stdout)
        assert t2 != t1  # token rotated
        assert t2[:4] == t1[:4]  # same prefix

        # Submit — advance to handoff
        r = run_cli("submit", "--token", t2, "--answer", "done", cwd=project_dir)
        assert r.returncode == 0, r.stderr
        assert "Done" in r.stdout
        assert "Submit your report:" in r.stdout

    def test_wrong_token_rejected(self, project_dir):
        run_cli("init", "--mission", "demo", cwd=project_dir)

        r = run_cli("submit", "--token", "wrongtoken", "--answer", "done", cwd=project_dir)
        assert r.returncode != 0

    def test_request_repeatable_with_same_token(self, project_dir):
        r = run_cli("init", "--mission", "demo", cwd=project_dir)
        t1 = extract_token(r.stdout)

        r1 = run_cli("request", "--token", t1, cwd=project_dir)
        assert r1.returncode == 0
        r2 = run_cli("request", "--token", t1, cwd=project_dir)
        assert r2.returncode == 0

    def test_init_resume(self, project_dir):
        r = run_cli("init", "--mission", "demo", cwd=project_dir)
        assert r.returncode == 0
        runtime_id = extract_runtime_id(r.stdout)

        r = run_cli("init", "--resume", runtime_id, cwd=project_dir)
        assert r.returncode == 0
        assert f"Resumed run: {runtime_id}" in r.stdout
        assert "Token:" in r.stdout

    def test_init_args_are_persisted_and_available_on_env(self, tmp_path):
        missions = tmp_path / ".agentos" / "missions" / "args-demo"
        missions.mkdir(parents=True)
        (missions / "mission.py").write_text("""
from agentos import iterante2

def setup(ctx):
    ctx.state["project"] = ctx.env.args["project"]

def step(ctx):
    title = f"{ctx.env.args['project']} / {ctx.env.args['mode']}"
    ctx.call = iterante2.calls.task(id="args", title=title)
""")

        r = run_cli(
            "init",
            "--mission",
            "args-demo",
            "--args",
            '{"project":"demo","mode":"scan"}',
            cwd=tmp_path,
        )
        assert r.returncode == 0, r.stderr
        assert "demo / scan" in r.stdout

        runtime_id = extract_runtime_id(r.stdout)
        run_json = missions / "runs" / runtime_id / "run.json"
        data = json.loads(run_json.read_text())
        assert data["args"] == {"project": "demo", "mode": "scan"}

        token = extract_token(r.stdout)
        r = run_cli("submit", "--token", token, "--answer", "done", cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "demo / scan" in r.stdout

    def test_init_args_must_be_json_object(self, project_dir):
        r = run_cli("init", "--mission", "demo", "--args", '["not", "object"]', cwd=project_dir)
        assert r.returncode != 0
        assert "--args must be a JSON object" in r.stderr


class TestErrorBoundary:
    """Mechanism 1 — machinery errors are generic + logged; agent-workflow
    errors are surfaced; no path/filename/traceback ever reaches the agent."""

    def _leak_free(self, text):
        for leak in (".agentos", SNAPSHOT_FILE, "run.json", "Traceback", "/private/", "looked in"):
            assert leak not in text, f"leak {leak!r} in:\n{text}"

    def test_machinery_error_is_generic_and_logged(self, project_dir):
        r = run_cli("init", "--mission", "demo", cwd=project_dir)
        runtime_id = extract_runtime_id(r.stdout)
        token = extract_token(r.stdout)

        # Corrupt machinery: remove the run's snapshot → HarnessError in the runner.
        run_dir = project_dir / ".agentos" / "missions" / "demo" / "runs" / runtime_id
        (run_dir / SNAPSHOT_FILE).unlink()

        r = run_cli("submit", "--token", token, "--answer", "x", cwd=project_dir)
        assert r.returncode != 0
        assert "fatal error" in (r.stdout + r.stderr)
        self._leak_free(r.stdout + r.stderr)

        # Full detail recoverable from the mission-folder log.
        log = (run_dir / "errors.log").read_text()
        assert SNAPSHOT_FILE in log
        assert "HarnessError" in log

    def test_mission_not_found_has_no_paths(self, project_dir):
        r = run_cli("init", "--mission", "nope", cwd=project_dir)
        assert r.returncode != 0
        assert "Mission not found: nope" in r.stderr
        self._leak_free(r.stdout + r.stderr)

    def test_bad_token_is_surfaced_to_agent(self, project_dir):
        run_cli("init", "--mission", "demo", cwd=project_dir)
        r = run_cli("submit", "--token", "wrongtoken", "--answer", "x", cwd=project_dir)
        assert r.returncode != 0
        # Agent-workflow error: an actionable, leak-free message reaches the
        # agent (resolved at the launcher before the harness token check)...
        assert "No run found for token" in r.stderr
        # ...not a generic fatal, and leaking nothing.
        assert "fatal error" not in r.stderr
        self._leak_free(r.stdout + r.stderr)


class TestOutputSensors:
    """Mechanism 2 — the mission's own output is scrubbed before the agent sees it."""

    def test_forwarded_mission_print_is_redacted(self, tmp_path):
        missions = tmp_path / ".agentos" / "missions" / "printer"
        missions.mkdir(parents=True)
        (missions / "mission.py").write_text("""
from agentos import iterante2

def step(ctx):
    print("mission says: /etc/secret/data.txt")
    ctx.call = iterante2.calls.task(id="t1", title="Work")
""")
        r = run_cli("init", "--mission", "printer", cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "‹path›" in r.stdout
        assert "/etc/secret" not in r.stdout


class TestBypass:
    """Index E — the dev bypass disables sensors and makes errors verbose,
    propagating to the `_runner` subprocess."""

    def test_raw_flag_disables_sensors(self, tmp_path):
        missions = tmp_path / ".agentos" / "missions" / "printer"
        missions.mkdir(parents=True)
        (missions / "mission.py").write_text("""
from agentos import iterante2

def step(ctx):
    print("mission says: /etc/secret/data.txt")
    ctx.call = iterante2.calls.task(id="t1", title="Work")
""")
        r = run_cli("--raw", "init", "--mission", "printer", cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "/etc/secret/data.txt" in r.stdout
        assert "‹path›" not in r.stdout

    def test_bypass_env_surfaces_real_error_through_subprocess(self, project_dir):
        r = run_cli("init", "--mission", "demo", cwd=project_dir)
        runtime_id = extract_runtime_id(r.stdout)
        token = extract_token(r.stdout)
        run_dir = project_dir / ".agentos" / "missions" / "demo" / "runs" / runtime_id
        (run_dir / SNAPSHOT_FILE).unlink()

        r = run_cli(
            "submit", "--token", token, "--answer", "x",
            cwd=project_dir, env_extra={"ITERANTE_NO_REDACT": "1"},
        )
        assert r.returncode != 0
        combined = r.stdout + r.stderr
        # bypass on → the real detail surfaces (no generic fatal)
        assert "fatal error" not in combined
        assert SNAPSHOT_FILE in combined


class TestDevStep:
    def test_dev_step_no_persist(self, project_dir):
        r = run_cli("dev", "step", "--mission", "demo", cwd=project_dir)
        assert r.returncode == 0, r.stderr
        assert "[dev step" in r.stdout
        assert "Step 1" in r.stdout
        assert "State after step:" in r.stdout
