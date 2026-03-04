"""Tests for post_bash_capture.py hook."""

import json
import os
import subprocess
import sys
from pathlib import Path


# Path to the hook script under test
HOOK_PATH = Path(__file__).resolve().parent.parent / "post_bash_capture.py"


def run_hook(stdin_data: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run the post_bash_capture hook with controlled stdin and cwd."""
    env = {}
    for key in ("PATH", "SYSTEMROOT", "PYTHONPATH", "HOME", "USERPROFILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    # Redirect _lib.py paths to tmp_path so hooks write to the temp dir
    if cwd:
        env["CLAUDE_PROJECT_ROOT"] = cwd
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=cwd,
    )


def build_stdin(
    command: str = "echo hello",
    exit_code: int | None = 0,
    stdout: str = "",
    stderr: str = "",
) -> str:
    """Build valid hook stdin JSON."""
    response: dict = {}
    if exit_code is not None:
        response["exitCode"] = exit_code
    if stdout:
        response["stdout"] = stdout
    if stderr:
        response["stderr"] = stderr
    return json.dumps({"tool_input": {"command": command}, "tool_response": response})


class TestHookExists:
    """# Tests R-P2-03"""

    def test_hook_file_exists(self) -> None:
        """# Tests R-P2-03 -- post_bash_capture.py exists on disk."""
        assert HOOK_PATH.exists(), f"Hook not found at {HOOK_PATH}"
        assert HOOK_PATH.name == "post_bash_capture.py"

    def test_hook_is_valid_python(self) -> None:
        """# Tests R-P2-03 -- hook is valid Python that compiles without errors."""
        source = HOOK_PATH.read_text(encoding="utf-8")
        code = compile(source, str(HOOK_PATH), "exec")
        code_type = type(code).__name__
        assert code_type == "code"


class TestErrorCapture:
    """# Tests R-P2-03"""

    def test_failed_command_creates_last_error_json(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- exit != 0 creates .claude/errors/last_error.json."""
        stdin = build_stdin(command="false", exit_code=1, stderr="command failed")
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

        last_error = tmp_path / ".claude" / "errors" / "last_error.json"
        assert last_error.exists(), "last_error.json not created"

    def test_error_has_timestamp_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains ISO timestamp."""
        stdin = build_stdin(command="broken", exit_code=2)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert "timestamp" in error
        assert "T" in error["timestamp"]  # ISO 8601 format check

    def test_error_has_exit_code_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains the correct exit_code."""
        stdin = build_stdin(command="fail", exit_code=127)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert error["exit_code"] == 127

    def test_error_has_command_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains the command that was run."""
        stdin = build_stdin(command="git push --force", exit_code=1)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert error["command"] == "git push --force"

    def test_error_has_stderr_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains stderr output."""
        stdin = build_stdin(command="bad", exit_code=1, stderr="permission denied")
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert error["stderr"] == "permission denied"

    def test_error_has_stdout_tail_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains last 500 chars of stdout."""
        stdin = build_stdin(command="bad", exit_code=1, stdout="some output here")
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert error["stdout_tail"] == "some output here"

    def test_error_has_cwd_field(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- error record contains the working directory."""
        stdin = build_stdin(command="bad", exit_code=1)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        cwd_val = error["cwd"]
        cwd_len = len(cwd_val)
        assert cwd_len >= 1

    def test_stderr_truncated_to_2000_chars(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- stderr is truncated to last 2000 characters."""
        long_stderr = "x" * 5000
        stdin = build_stdin(command="bad", exit_code=1, stderr=long_stderr)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert len(error["stderr"]) == 2000

    def test_stdout_tail_truncated_to_500_chars(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- stdout_tail is truncated to last 500 characters."""
        long_stdout = "y" * 2000
        stdin = build_stdin(command="bad", exit_code=1, stdout=long_stdout)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert len(error["stdout_tail"]) == 500

    def test_command_truncated_to_1000_chars(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- command field is truncated to 1000 characters."""
        long_cmd = "z" * 3000
        stdin = build_stdin(command=long_cmd, exit_code=1)
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert len(error["command"]) == 1000


class TestTestCommandDetection:
    """# Tests R-P2-03"""

    def test_pytest_exit_0_clears_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- pytest with exit 0 clears needs_verify in state."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 0,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="pytest tests/ -v", exit_code=0)
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is None, (
            "needs_verify should be cleared after test pass"
        )

    def test_python_m_pytest_exit_0_clears_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- 'python -m pytest' with exit 0 clears marker in state."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 0,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="python -m pytest -v", exit_code=0)
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is None

    def test_non_test_exit_0_does_not_clear_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- 'echo hello' exit 0 does NOT clear marker."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 0,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="echo hello", exit_code=0)
        run_hook(stdin, cwd=str(tmp_path))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] == "dirty", (
            "needs_verify should remain for non-test commands"
        )

    def test_test_command_exit_1_does_not_clear_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- pytest exit 1 (failed tests) does NOT clear marker."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 0,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="pytest tests/", exit_code=1, stderr="1 failed")
        run_hook(stdin, cwd=str(tmp_path))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] == "dirty", (
            "needs_verify should remain when tests fail"
        )


class TestMarkerClearing:
    """# Tests R-P2-03"""

    def test_needs_verify_cleared_on_test_pass(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- needs_verify cleared in state when test passes."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "modified file.py",
                    "stop_block_count": 0,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="pytest -v", exit_code=0)
        run_hook(stdin, cwd=str(tmp_path))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is None

    def test_stop_block_count_reset_on_test_pass(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- stop_block_count reset to 0 in state when test passes."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 2,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="pytest -v", exit_code=0)
        run_hook(stdin, cwd=str(tmp_path))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["stop_block_count"] == 0

    def test_both_markers_cleared_simultaneously(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- both needs_verify and stop_block_count cleared together in state."""
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "needs_verify": "dirty",
                    "stop_block_count": 3,
                    "prod_violations": None,
                }
            ),
            encoding="utf-8",
        )

        stdin = build_stdin(command="pytest", exit_code=0)
        run_hook(stdin, cwd=str(tmp_path))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is None
        assert state["stop_block_count"] == 0


class TestNoErrorHistory:
    """# Tests R-P1-04 -- error_history.jsonl is NOT created."""

    def test_no_error_history_on_failure(self, tmp_path: Path) -> None:
        """# Tests R-P1-04 -- error_history.jsonl is NOT created on error."""
        stdin = build_stdin(command="fail", exit_code=1, stderr="error")
        run_hook(stdin, cwd=str(tmp_path))

        history = tmp_path / ".claude" / "errors" / "error_history.jsonl"
        assert not history.exists(), "error_history.jsonl should not be created"

    def test_last_error_json_still_created(self, tmp_path: Path) -> None:
        """# Tests R-P1-04 -- last_error.json IS still created on error."""
        stdin = build_stdin(command="fail", exit_code=1, stderr="error")
        run_hook(stdin, cwd=str(tmp_path))

        last_error = tmp_path / ".claude" / "errors" / "last_error.json"
        assert last_error.exists(), "last_error.json should be created"


class TestEdgeCases:
    """# Tests R-P2-03"""

    def test_empty_stdin_exits_0(self) -> None:
        """# Tests R-P2-04 -- empty stdin returns {} from parse_hook_stdin."""
        # Note: empty string on non-TTY stdin returns {} from parse_hook_stdin,
        # which then proceeds normally. exitCode defaults to 0 => exit 0.
        result = run_hook("")
        assert result.returncode == 0

    def test_malformed_json_exits_0(self) -> None:
        """# Tests R-P2-04 -- malformed JSON stdin exits 0 (fail-open)."""
        result = run_hook("this is not json at all")
        assert result.returncode == 0

    def test_partial_json_exits_0(self) -> None:
        """# Tests R-P2-04 -- partial/truncated JSON exits 0 (fail-open)."""
        result = run_hook('{"tool_input": {"command": "test"')
        assert result.returncode == 0

    def test_missing_exit_code_defaults_to_0(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- missing exitCode in tool_response defaults to 0."""
        # No exitCode key at all => defaults to 0 => exit 0, no error file
        stdin = json.dumps(
            {"tool_input": {"command": "echo hello"}, "tool_response": {}}
        )
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

        last_error = tmp_path / ".claude" / "errors" / "last_error.json"
        assert not last_error.exists(), "No error file for exit code 0"

    def test_exit_0_non_test_does_not_create_error_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- exit 0 on non-test command creates no error file."""
        stdin = build_stdin(command="ls -la", exit_code=0)
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

        last_error = tmp_path / ".claude" / "errors" / "last_error.json"
        assert not last_error.exists()

    def test_missing_command_uses_unknown(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- missing command in tool_input defaults to 'unknown'."""
        stdin = json.dumps(
            {"tool_input": {}, "tool_response": {"exitCode": 1, "stderr": "err"}}
        )
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        assert error["command"] == "unknown"

    def test_empty_stderr_stored_as_empty_string(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- empty stderr is stored as empty string, not None."""
        stdin = build_stdin(command="fail", exit_code=1, stderr="")
        run_hook(stdin, cwd=str(tmp_path))

        error = json.loads(
            (tmp_path / ".claude" / "errors" / "last_error.json").read_text()
        )
        stderr_val = error["stderr"]
        assert stderr_val == ""


class TestExitCodes:
    """# Tests R-P2-03"""

    def test_exits_0_on_successful_command(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- hook exits 0 when command succeeded (exit 0)."""
        stdin = build_stdin(command="echo ok", exit_code=0)
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_failed_command(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- hook exits 0 even when command failed (error captured, not blocked)."""
        stdin = build_stdin(command="bad", exit_code=1, stderr="fail")
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_high_exit_code(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- hook exits 0 even for high exit codes like 137 (killed)."""
        stdin = build_stdin(command="killed", exit_code=137, stderr="OOM killed")
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_test_pass(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- hook exits 0 when test command passes."""
        stdin = build_stdin(command="pytest -v", exit_code=0)
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_test_fail(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- hook exits 0 even when test command fails."""
        stdin = build_stdin(command="pytest -v", exit_code=1, stderr="FAILED")
        result = run_hook(stdin, cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_invalid_json(self) -> None:
        """# Tests R-P2-04 -- invalid JSON exits 0 (fail-open); all valid input also exits 0."""
        valid = run_hook(build_stdin(command="x", exit_code=255))
        invalid = run_hook("{bad json")
        assert valid.returncode == 0
        assert invalid.returncode == 0
